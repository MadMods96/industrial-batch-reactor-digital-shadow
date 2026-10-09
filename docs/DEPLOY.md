# Deploy — pure digital shadow (no AI)

## Architecture

- **Frontend:** Next.js on Vercel (or local `npm run dev`)
- **Backend:** FastAPI + DuckDB + WebSocket + panel ingest on a long-running host

There are **no** Next.js mock `/api` routes. The UI talks only to FastAPI.

## Backend

1. Deploy this repo’s Python app (Render / Railway / Fly / VM).
2. Set panel secrets: `HTPP_PANEL_*`, machine ids/labels.
3. Do **not** set `HTPP_DISABLE_SCHEDULER=1` if you want live pulls.
4. Confirm `GET /health` → `{"status":"ok"}` and WebSocket `/ws/live`.

Start command example:

```bash
pip install -e ./backend
python -m htpp.cli init-db
python -m htpp.cli ingest
python scripts/render_start.py
# or: PYTHONPATH=backend/src python -m htpp.cli api
```

## Frontend (Vercel)

Root Directory: `frontend`

| Env | Example |
|-----|---------|
| `NEXT_PUBLIC_API_BASE_URL` | `https://your-api.onrender.com` |
| `NEXT_PUBLIC_WS_URL` | `wss://your-api.onrender.com/ws/live` |

Also set API `HTPP_API_CORS_ORIGINS` to your `*.vercel.app` URL.

## Local

```powershell
# terminal 1
$env:PYTHONPATH = "backend/src"
python -m htpp.cli api

# terminal 2
cd frontend
npm run dev
```
