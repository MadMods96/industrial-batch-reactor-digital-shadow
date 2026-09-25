# 02 - Architecture

## 1. Stack decisions, and why

| Layer | Choice | Reason |
|---|---|---|
| Ingestion | Python, `httpx` + `selectolax` | Panel is server-rendered HTML with no API. `selectolax` is much faster than BeautifulSoup for repeated table parsing. |
| Storage | DuckDB file + Parquet | Single-file, zero-ops, SQL over Parquet, trivially reproducible, commits nothing large. A Postgres server buys nothing at this scale. |
| Modelling | numpy, scipy, pandas, scikit-learn, statsmodels | Reviewers know these. `scipy.optimize` for parameter identification, `scipy.integrate.solve_ivp` for the ODE. |
| Backend | FastAPI + uvicorn | Async, typed, generates OpenAPI which the frontend consumes for types. WebSocket support is built in. |
| Frontend | Next.js App Router + TypeScript | Maddy's existing stack. |
| 3D | React Three Fiber + drei + three.js | The only sane way to drive a three.js scene from React state. |
| 3D asset | Blender to glTF 2.0 (.glb) | Decided. Bound by the node contract in doc 09. |
| Client state | Zustand | Telemetry ticks must update the 3D scene without re-rendering the React tree. Zustand's transient subscriptions do exactly this. Context or Redux would cause frame drops. |
| Charts | Recharts | Sufficient, and not three.js. |
| Scheduling | APScheduler in the API process | One less moving part than Celery. Ingestion is a 30-second job every few minutes. |
| Packaging | `uv` for Python, `pnpm` for Node | Fast, lockfile-accurate. |

### Rejected, with reasons

- **Postgres / TimescaleDB.** About 50k rows total. DuckDB is faster to query and needs no server.
- **Celery / Redis.** No distributed work exists here.
- **Kafka or any stream broker.** Data arrives every four minutes.
- **Deep learning frameworks.** ~100 batches. Would be indefensible in review.
- **Unity or Unreal for 3D.** Enormous overhead, no web deploy story, and the whole app is already React.
- **Three.js without R3F.** Manual imperative sync between React state and scene graph is exactly the bug factory to avoid.
- **Server-side rendering of the 3D scene.** Client-only. Load the scene with `next/dynamic` and `ssr: false`.

## 2. Repository layout

```
htpp-digital-twin/
├── .cursorrules
├── .env.example
├── Makefile
├── README.md
├── docs/                          # these specs, source of truth
│
├── backend/
│   ├── pyproject.toml
│   ├── src/htpp/
│   │   ├── config.py              # pydantic-settings, reads .env
│   │   ├── schemas.py             # pydantic models, mirrors doc 03 exactly
│   │   │
│   │   ├── ingest/
│   │   │   ├── panel_client.py    # auth + HTTP, rate limited
│   │   │   ├── panel_parser.py    # HTML -> rows, header-name driven
│   │   │   ├── backfill.py        # historical sweep with date chunking
│   │   │   ├── incremental.py     # scheduled tail fetch
│   │   │   ├── excel_log.py       # batch log parser, config-mapped
│   │   │   └── column_map.yaml    # Excel column mapping, edit not code
│   │   │
│   │   ├── store/
│   │   │   ├── db.py              # DuckDB connection, migrations
│   │   │   ├── writes.py          # idempotent upserts
│   │   │   └── queries.py         # all SQL lives here, nowhere else
│   │   │
│   │   ├── batches/
│   │   │   ├── segment.py         # telemetry -> batches -> phases
│   │   │   ├── features.py        # thermal severity and friends
│   │   │   └── quality.py         # flags, mass balance closure
│   │   │
│   │   ├── models/
│   │   │   ├── thermal.py         # lumped capacitance, tau identification
│   │   │   ├── kinetics.py        # single-step Arrhenius conversion
│   │   │   ├── yield_model.py     # Ridge / ElasticNet / GBM + intervals
│   │   │   ├── faults.py          # residual detector, EWMA + CUSUM
│   │   │   ├── interpolate.py     # model-based upsampling for the 3D scene
│   │   │   ├── simulate.py        # forward rollout, what-if, live projection
│   │   │   └── registry.py        # fit, version, save, load artefacts
│   │   │
│   │   ├── api/
│   │   │   ├── main.py            # app factory, CORS, scheduler startup
│   │   │   ├── routes_data.py
│   │   │   ├── routes_models.py
│   │   │   ├── routes_simulate.py
│   │   │   └── ws_live.py         # WebSocket live channel
│   │   │
│   │   └── report/
│   │       ├── validation.py      # regenerates every metric
│   │       └── figures.py         # regenerates every paper figure
│   │
│   ├── tests/
│   │   └── fixtures/
│   │       ├── graph_1093.html    # saved real page, contract test
│   │       └── batch_log.xlsx     # synthetic Excel matching doc 03
│   └── artifacts/                 # fitted models, gitignored
│
├── frontend/
│   ├── package.json
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx               # 3D plant overview, the landing page
│   │   ├── machines/[id]/page.tsx
│   │   ├── batches/page.tsx
│   │   ├── batches/[key]/page.tsx # replay
│   │   ├── simulate/page.tsx
│   │   ├── model/page.tsx
│   │   └── data/page.tsx
│   ├── components/
│   │   ├── scene/                 # all R3F, see doc 08
│   │   │   ├── PlantScene.tsx
│   │   │   ├── Reactor.tsx
│   │   │   ├── ReactorPlaceholder.tsx
│   │   │   ├── stateMapping.ts    # process label -> visual params
│   │   │   ├── tempRamp.ts
│   │   │   ├── effects/
│   │   │   └── Hud.tsx
│   │   ├── charts/
│   │   └── ui/
│   ├── lib/
│   │   ├── api.ts                 # typed client from OpenAPI
│   │   ├── store.ts               # zustand, transient telemetry channel
│   │   └── ws.ts                  # WebSocket client with reconnect
│   └── public/models/
│       └── reactor.glb            # the Blender export, doc 09 contract
│
├── data/
│   ├── raw/                       # gitignored
│   ├── htpp.duckdb                # gitignored
│   └── excel_drop/                # plant Excel files land here
│
└── notebooks/                     # exploration only, never imported by src
```

### Rules about this layout

- **All SQL lives in `store/queries.py`.** No inline SQL anywhere else.
- **`schemas.py` mirrors doc 03 field for field.** If they disagree, doc 03 wins
  and `schemas.py` is wrong.
- **`notebooks/` is never imported by `src/`.** Notebooks may import from `src/`.
  One-way dependency.
- **`report/` must regenerate everything.** No figure or number in the paper may
  exist only in a notebook.
- **Frontend never computes physics.** All modelling is backend. The frontend
  interpolates visually between backend-supplied model states, nothing more.

## 3. Data flow

```
  Cloud HTPP panel (panel.htpp.in)
         │ HTML, ~4 min cadence, 3 machines
         │ rate limited, read only
         ▼
  panel_client + panel_parser
         │ typed TelemetrySample rows
         ▼
  DuckDB  telemetry_raw ◄──────── excel_log parser ◄── data/excel_drop/*.xlsx
         │                              │  BatchLogEntry rows
         │                              ▼
         │                        DuckDB  batch_log
         ▼
  segment.py ──► DuckDB  batches, phases
         │
         ▼
  features.py ──► DuckDB  batch_features   (joins batch_log on machine_id+batch_no)
         │
         ▼
  thermal.py ─┬─► artifacts/thermal_vN.joblib
  kinetics.py ┤
  yield.py   ─┤
  faults.py  ─┘
         │
         ▼
  FastAPI ──► REST for history, batches, metrics, what-if simulate
         └──► WebSocket /ws/live for the 3D scene
                     │
                     ▼
            Next.js  zustand store
                     │ transient subscription, no React re-render
                     ▼
            R3F PlantScene ──► 3 x Reactor (glTF or placeholder)
                     │
                     └──► interpolate.py output consumed at 60 fps
```

## 4. The interpolation boundary, read this carefully

This is the single most important architectural decision in the project, and the
easiest one to get wrong.

Telemetry arrives every ~4 minutes. The scene renders at 60 fps. That is a factor
of about 14,000. There are three ways to bridge it and only one is correct.

**Wrong: step on arrival.** Scene freezes for four minutes then jumps. Looks broken.

**Wrong: linear tween between the last two samples.** Smooth, but it is lying
about the physics, it lags by one full sample interval, and during the heating
ramp a straight line between two points four minutes apart visibly misses the
exponential curvature.

**Correct: model-based projection.** On each telemetry tick the backend runs the
fitted thermal and kinetic model forward from the measured state and returns a
dense trajectory covering the next interval, plus the residual against what it
predicted for the interval that just closed. The frontend plays that dense
trajectory at display rate. When the next real sample arrives, the frontend
blends from the projected value to the new measured value over about 400 ms so
there is no visible snap.

Consequences that the implementation must respect:

- `/ws/live` payload carries a **dense trajectory**, not a single point. See doc 06.
- The visible divergence between projection and the next real sample **is the
  fault signal**. It is not an artefact to hide. Surface it in the HUD as a
  residual gauge, and drive the fault alarm from it.
- The 3D scene is therefore not decoration. It is the model's output rendered,
  which is precisely the argument to make in the paper's discussion.

## 5. Configuration

Everything through `.env`, read by `backend/src/htpp/config.py` via
pydantic-settings. `.env.example` is committed, `.env` never is.

```ini
# .env.example
HTPP_PANEL_BASE_URL=https://panel.htpp.in
HTPP_PANEL_USERNAME=
HTPP_PANEL_PASSWORD=
HTPP_MACHINE_IDS=1093,1094,1146
HTPP_REQUEST_MIN_INTERVAL_S=2.0
HTPP_REQUEST_TIMEOUT_S=30
HTPP_BACKFILL_CHUNK_DAYS=3
HTPP_HISTORY_FLOOR_DATE=2026-08-01
HTPP_DB_PATH=data/htpp.duckdb
HTPP_EXCEL_DROP_DIR=data/excel_drop
HTPP_ARTIFACT_DIR=backend/artifacts
HTPP_INCREMENTAL_CRON_MINUTES=4
HTPP_API_CORS_ORIGINS=http://localhost:3000
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws/live
```

`HTPP_BACKFILL_CHUNK_DAYS=3` is deliberate. A three-day window returned 995 rows
in testing, which renders fine. Larger windows risk server-side timeouts on a
panel that builds the whole table server-side.

## 6. Makefile targets

Cursor must create these and keep them working.

```make
make setup        # uv sync, pnpm install
make backfill     # full historical ingestion, all machines. RUN THIS FIRST
make ingest       # one incremental tick
make excel        # parse everything in data/excel_drop
make build        # segment + features
make fit          # fit and version all models
make reproduce    # backfill-free: build, fit, validation report, all figures
make api          # uvicorn with reload
make web          # next dev
make dev          # api + web together
make types        # regenerate frontend TS types from the FastAPI OpenAPI schema
make validate-3d  # assert reactor.glb satisfies the doc 09 node contract
make test         # pytest + vitest + validate-3d
make coverage     # ingestion coverage report
```

`make types` must be re-run whenever a response model changes, and `make test`
should fail if generated types are stale, so the frontend can never drift from doc 03.

`make validate-3d` runs `frontend/scripts/validate-gltf.ts` against
`public/models/reactor.glb` when present, and against the placeholder's node graph
otherwise, so the contract is checked even before the Blender asset exists.

`make reproduce` must run end to end from a populated database with no manual
steps and no notebook execution. That is the reproducibility claim.
