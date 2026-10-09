# HTPP Digital Shadow

Live **digital shadow** of industrial batch reactors: sparse PLC/panel telemetry → reduced-order models → 3D floor view and data quality.

This is **not** a digital twin. Data flows one way (plant → software). The system never writes setpoints or actuates equipment. No LLM / Ask / What-if in this build.

| Floor (live) | Insights | Data quality |
|---|---|---|
| ![Floor](docs/screenshots/01-floor-live.png) | ![Insights](docs/screenshots/02-insights-modal.png) | ![Data](docs/screenshots/05-data-coverage.png) |

---

## Research framing

- **Class:** digital *shadow* (Kritzinger et al., 2018) — automatic one-way coupling
- **Constraint:** ~4-minute industrial telemetry (not lab-dense signals)
- **Method:** reduced-order thermal / phase models + yield features from logs
- **Ops layer:** live 3D scene, rule-based insights, coverage/gap audit

---

## What you get

| Area | Description |
|------|-------------|
| **Floor** | Live 3D reactors from panel WebSocket ticks |
| **Insights** | Rule-based alerts (gaps, yields, faults) — no AI |
| **Batches / Data** | History and telemetry coverage |

---

## Telemetry from the panel (PLC / sensors)

Samples arrive roughly every **4 minutes**. Field meanings:

| Field | Unit | Meaning |
|-------|------|---------|
| `tr_c` | °C | Reactor temperature |
| `ts_c` | °C | Separator temperature |
| `pr_bar` | bar | Reactor pressure |
| `ps_bar` | bar | Separator pressure |
| `roh_c_per_min` | °C/min | Rate of heating |
| `amb_temp_c` | °C | Ambient temperature |
| `process_raw` | text | Panel process label (e.g. heating, cooling, door open) |
| `fault_raw` | text | Panel fault label when present |
| `sampled_at` | timestamp | Sample time (stored UTC; UI shows IST) |
| `machine_id` | int | Reactor id (configured in `.env`) |
| `batch_no` | int | Panel batch number when known |

See [docs/TELEMETRY.md](docs/TELEMETRY.md) for formats and Excel mass-log columns.

---

## Quick start (local live)

```powershell
cd htpp-digital-twin
python -m pip install -e "./backend[dev]"
copy .env.example .env
# fill panel credentials — never commit .env

cd frontend
npm install
cd ..

$env:PYTHONPATH = "backend/src"
python -m htpp.cli init-db
python -m htpp.cli ingest
python -m htpp.cli excel
python -m htpp.cli build
python -m htpp.cli fit
python -m htpp.cli api
```

Second terminal:

```powershell
cd frontend
npm run dev
```

Open http://localhost:3000 — Floor should show `live` and real Tr/Pr from the panel.

Optional seed (offline fixture only): `python -m htpp.cli seed` — do **not** use for plant demos.

---

## Configuration

All secrets and site labels live in **`.env`** (see `.env.example`):

- Panel username / password / base URL
- Machine ids and **display labels** (`HTPP_MACHINE_LABELS`)
- Excel reactor-name aliases (`HTPP_MACHINE_ALIASES`)
- `NEXT_PUBLIC_API_BASE_URL` / `NEXT_PUBLIC_WS_URL` → FastAPI host
- `HTPP_API_CORS_ORIGINS` → frontend origin

Customer or site names must **not** be hardcoded in source.

---

## Deploy

| Piece | Where |
|-------|--------|
| **Frontend** (Next.js) | Vercel — Root Directory `frontend`; set `NEXT_PUBLIC_*` to your API |
| **Backend** (FastAPI + DuckDB + WebSocket + ingest) | Render / Railway / Fly / VM with disk |

Vercel alone cannot run live panel ingest + WebSockets. Point the frontend at a long-running API.

See [docs/DEPLOY.md](docs/DEPLOY.md).

---

## Repo hygiene

- `.env` is gitignored — rotate any key that was ever pasted into chat
- Plant Excel files stay out of git (`*.xlsx` ignored except test fixtures)
- Specs under `docs/`; start with this README + `TELEMETRY.md`
- See [docs/SECURITY.md](docs/SECURITY.md) before any public push

---

## License / data use

Panel credentials belong to the plant operator. Use read-only access, respect rate limits, and obtain written data-use consent before publication or wide sharing.
