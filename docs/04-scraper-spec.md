# 04 - Panel Ingestion Spec

## 0. Before writing a single line

The Cloud HTPP panel is **Plant Operator's production operations system.**
It is not ours. Three rules, non-negotiable, enforced in code:

1. **Read-only.** A hardcoded allowlist of GET paths. Any request to a path not on
   the list raises. The panel exposes `config.php`, `configstatus.php`,
   `changeBatch.php`, `changeBatchTiming.php`, `addMobile.php` and a hooter
   trigger. Touching any of them could change plant behaviour or set off an audible
   alarm in an industrial facility. **Never request them.**
2. **Rate limited.** One request every `HTPP_REQUEST_MIN_INTERVAL_S` (default 2.0)
   seconds, globally across all machines, enforced by a single shared limiter.
3. **Identified.** Set a descriptive `User-Agent` naming the project and Maddy's
   email. If the panel operator sees the traffic, they should be able to tell
   immediately who it is and why.

The write-path allowlist, to be implemented literally:

```python
ALLOWED_PATHS = frozenset({
    "/graph.php",
    "/dashboard.php",
    "/alltsgraph3.php",
    "/currentDataView.php",
    "/currentDataView2.php",
    "/downloaddata.php",
})
FORBIDDEN_PATHS = frozenset({
    "/config.php", "/configstatus.php", "/changeBatch.php",
    "/changeBatchTiming.php", "/addMobile.php", "/logout.php",
})
```

`logout.php` is forbidden because hitting it would kill the session, possibly the
plant's own session if the cookie is shared.

---

## 1. What the panel actually exposes, verified 2026-09-19

There is **no JSON API.** Everything is server-rendered PHP. Confirmed by
inspecting network traffic: zero XHR or fetch calls on any page. Data is embedded
directly into Chart.js 2.7.2 configs and a DataTables table.

| Path | Contents | Use it? |
|---|---|---|
| `graph.php?machineid=N` | **Full time series table** with all 13 columns, plus temperature and pressure charts. Accepts an arbitrary date-time range by GET params | **Yes, this is the sole ingestion endpoint** |
| `dashboard.php?machineid=N` | Current values, batch phase timeline with durations, plant temp, firmware, chip id, recharge days, emergency field | Yes, for live current-state polling and phase-timeline cross-checks |
| `alltsgraph3.php` | Separator temp only, all three machines, last 24 h, ~4 min cadence | Only to discover machine ids. Redundant otherwise |
| `currentDataView.php` | Multi-machine current view | Optional cross-check |
| `currentDataView2.php` | Current board view | Optional cross-check |
| `downloaddata.php` | Batch-wise **maximum** values only: SN, Machine Name, Batch No, ROH, Ts, Tr, Ps, Pr | **Useless for modelling.** No time series. But it is the one place that maps machine **names** to ids, which the Excel join needs. Fetch once |

### The ingestion endpoint

```
GET https://panel.htpp.in/graph.php
    ?date={from_date}      # YYYY-MM-DD
    &date1={to_date}       # YYYY-MM-DD
    &time={from_time}      # HH:MM
    &time1={to_time}       # HH:MM
    &machineid={id}        # 1093 | 1094 | 1146
    &submit=Submit         # required, the PHP branches on it
```

All six params are required. Omitting `submit=Submit` returns the default
last-24-hours view and silently ignores the date range, which would produce a
backfill that looks successful while fetching the same day over and over. Assert
that the returned date range matches what was requested.

Verified behaviour:

| Request | Result |
|---|---|
| `date=2026-09-15&date1=2026-09-17&time=00:00&time1=23:59&machineid=1093` | 995 rows, 2026-09-15 00:03:43 to 2026-09-17 23:57:36 |
| `date=2026-08-15&date1=2026-08-17&...` | 712 rows |
| `date=2026-08-01&date1=2026-08-03&...` | 0 rows, renders "No data available in table" |
| `date=2026-07-10&date1=2026-07-12&...` | 0 rows |

Zero rows is a **valid** response meaning either the reactor was off or the data
has been trimmed. It is not an error. Record it in `ingest_runs` with
`rows_fetched = 0` so the coverage report can distinguish it from a fetch failure.

---

## 2. Authentication

Standard PHP session cookie. The panel has a login form; the session persists in
the cookie jar.

```python
# panel_client.py, outline
class PanelClient:
    def __init__(self, settings: Settings):
        self._client = httpx.AsyncClient(
            base_url=settings.panel_base_url,
            timeout=settings.request_timeout_s,
            follow_redirects=True,
            headers={"User-Agent": (
                "HTPP-DigitalShadow/1.0 research crawler; 1 req/2s read-only"
            )},
        )
        self._limiter = AsyncRateLimiter(settings.request_min_interval_s)

    async def login(self) -> None:
        """POST credentials to the login form. Idempotent, no-op if session live."""

    async def is_authenticated(self) -> bool:
        """GET an allowlisted page, check it is not the login page."""

    async def get(self, path: str, params: dict) -> str:
        if path not in ALLOWED_PATHS:
            raise ForbiddenPathError(path)
        async with self._limiter:
            r = await self._client.get(path, params=params)
        if self._looks_like_login_page(r.text):
            await self.login()
            async with self._limiter:
                r = await self._client.get(path, params=params)
        r.raise_for_status()
        return r.text
```

Requirements:

- Credentials from `.env` only. Cursor must never write them into a file, a test,
  a fixture, a log line or a commit. If a login form field name is needed, discover
  it by parsing the login page, do not guess.
- **Session expiry looks like a successful 200 with login HTML.** Detect it by
  content, not status code. Re-login once, then retry once. Never loop.
- Persist the cookie jar to disk so restarts do not re-login unnecessarily.
- Never log cookie values or request bodies containing credentials.

**If login automation proves fragile,** the fallback is for Maddy to export the
session cookie from his browser into `.env` as `HTPP_SESSION_COOKIE`. Support both
paths. Do not spend more than an hour fighting the login form; the cookie fallback
is strictly better than a half-working login loop.

---

## 3. Parser

`panel_parser.py`, pure functions, no I/O. This makes it trivially testable
against saved HTML.

```python
def parse_telemetry_table(html: str, machine_id: int, source_url: str)
    -> list[TelemetrySample]
```

Algorithm:

1. Locate the table containing a `thead` whose cell texts include `Batch No`,
   `Tr` and `Date Time`. Do **not** select by index or CSS position; the panel has
   several tables and the layout will change.
2. Build `header -> column_index` from the `thead`, normalising each header by
   stripping whitespace and trailing periods. `Amb. Temp.` and `ROH Cal.` both
   carry periods.
3. Assert every required header is present. On failure raise
   `SchemaDriftError` listing the headers found. **Fail the run.** A silently
   mis-indexed parse would poison the database with columns swapped, and that is
   far worse than a failed run.
4. For each `tbody` row, read by name, coerce via helpers that return `None` on
   empty or non-numeric.
5. Parse `Date Time` as naive `%Y-%m-%d %H:%M:%S`, localise to Asia/Kolkata,
   convert to UTC.
6. Map `Process` through `process_map.yaml` to `process_state` and `fault_state`.
   Apply carry-previous forward-fill for fault rows **within the batch** only.
7. Drop `SN`.
8. Return sorted ascending by `sampled_at`.

Empty-result detection: if the table body contains `No data available in table`,
return `[]`. Not an error.

### Contract test, mandatory

Save the real `graph.php` response for machine 1093 over a known range as
`backend/tests/fixtures/graph_1093.html`. Assert:

- Exactly the expected row count parses.
- The first and last `sampled_at` match the known values.
- `tr_c`, `ts_c`, `pr_bar`, `ps_bar` for a chosen row match hand-verified values.
- Every `process_raw` in the fixture maps to a non-`unknown` `process_state` or
  `fault_state`.

This test is the early-warning system for panel HTML changes. Without it a layout
change corrupts data silently for days.

### Chart data, do not use for ingestion

The page also embeds Chart.js configs (`myChart` with Ts, Tr, Ambient; `myChart2`
with Ps, Pr). It is tempting to scrape those instead of the table, but they carry
fewer fields and no process label. Use the table. The charts are useful only as a
cross-check: parse both once and assert the Tr series agrees, to prove the table
parse is right.

---

## 4. Backfill

**Run this first, on day one, before writing any model code.** History is being
trimmed. Every day of delay costs a day of training data permanently.

```python
async def backfill(machine_ids: list[int], floor_date: date, ceiling: date) -> None
```

Algorithm:

1. Discover the true history floor per machine by bisection, so nothing is
   assumed. Probe a one-day window at the configured floor. If empty, step
   forward; if populated, step back. Approximately eight requests per machine.
   Cache the result in `ingest_runs`.
2. From the discovered floor to today, iterate in `HTPP_BACKFILL_CHUNK_DAYS`
   windows (default 3, which returned 995 rows and rendered fine).
3. Per chunk: fetch with `time=00:00`, `time1=23:59`, parse, upsert, record a row
   in `ingest_runs`.
4. Upsert is `INSERT ... ON CONFLICT (machine_id, sampled_at) DO NOTHING`. Chunk
   boundaries overlap by design; duplicates must be harmless.
5. Retry per chunk: 3 attempts, exponential backoff 2 s, 8 s, 32 s. On final
   failure record the error and **continue to the next chunk.** One bad window
   must not abort a 40-day backfill.
6. At the end, print a coverage table: machine by date, rows per day, gaps marked.
7. Exit non-zero if any chunk permanently failed, so `make backfill` is honest
   about partial success.

Volume estimate: 3 machines, ~45 days, 3-day chunks is about 45 requests. At one
per two seconds that is roughly two minutes. Expect around 40,000 to 50,000 rows.

**Also: write raw HTML for every chunk to `data/raw/{machine_id}/{from}_{to}.html.gz`.**
Cheap, and it means a parser bug is fixable by re-parsing rather than re-fetching
data that may no longer exist on the panel. This is the single best insurance
policy in the project.

---

## 5. Incremental ingestion

APScheduler job, every `HTPP_INCREMENTAL_CRON_MINUTES` (default 4).

```python
async def incremental_tick(machine_ids: list[int]) -> IngestResult
```

1. Per machine, read `MAX(sampled_at)` from `telemetry_raw`.
2. Fetch from `max_sampled_at - 30 min` to now. The overlap covers late-arriving
   or clock-skewed rows; the upsert makes it free.
3. If the table is empty for a machine, fall back to the last 24 hours.
4. Upsert, record `ingest_runs`.
5. On new rows: recompute the affected batch's features, rerun the model
   projection, and push over `/ws/live`. See doc 06.
6. Errors are logged and swallowed. A failed tick must never crash the API
   process. Three consecutive failures raise a warning banner on `/data`.

Also poll `dashboard.php?machineid=N` on the same tick for fields the graph table
does not carry: plant temperature, recharge-due days, the `Emergency if Any`
field, and the phase timeline with panel-computed durations. Cross-check panel
phase durations against our segmenter's and surface disagreements on `/data`.
That cross-check is free validation of the segmentation logic.

---

## 6. Machine-name discovery

The Excel log will likely identify reactors by name, not by panel id. Machine 1093
is named `Plant Operator - 1` on its dashboard. The names for 1094 and 1146
are unknown and must be discovered.

Fetch `downloaddata.php` once with a wide date range and read its `Machine Name`
column, and read the name from each `dashboard.php?machineid=N` header. Write the
mapping into `column_map.yaml` under `machine_name_to_id`. Print it so Maddy can
confirm it against the Excel before the join is trusted.

An unresolvable machine name in the Excel is a **hard parse failure**, not a
silent skip. A wrong machine attribution would silently corrupt every
per-machine result in the paper.

---

## 7. Coverage report

`make coverage` prints, and `/api/data/coverage` serves:

- Rows per machine per day, with a calendar heatmap on the `/data` page
- Discovered history floor per machine
- Gaps over 30 minutes, listed with start, end and duration
- Median sampling interval per machine per day
- Batch count per machine, complete versus incomplete
- Batches missing an Excel log row
- Excel rows missing a matching panel batch, which usually means a batch-number
  mismatch and is worth chasing with the plant
- Count of distinct `process_raw` values, with any unmapped ones listed
- `ingest_runs` failures

This report is the first figure in the paper's data section. Build it properly.
