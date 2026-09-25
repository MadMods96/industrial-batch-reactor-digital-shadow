# Deploy (Vercel frontend + Render API)

Split hosting is required: Next.js on **Vercel**, FastAPI + WebSocket + DuckDB on **Render**.

## 1. Backend on Render

1. Open [Render Blueprints](https://dashboard.render.com/blueprints) → **New Blueprint Instance**.
2. Select `MadMods96/industrial-batch-reactor-digital-shadow` and apply `render.yaml`.
3. When prompted, set at least:

| Key | Value |
|-----|--------|
| `HTPP_API_CORS_ORIGINS` | `https://YOUR-APP.vercel.app` (update after step 2) |
| Panel / Anthropic keys | Optional; leave blank for seeded demo |

4. Deploy. Note the API URL, e.g. `https://htpp-digital-shadow-api.onrender.com`.
5. Confirm `GET /health` returns `{"status":"ok"}`.

Free tier sleeps after idle; the first request after sleep can take ~30–60s. For a supervisor demo, open the API URL once before the meeting.

To enable live panel pulls later: set panel credentials and `HTPP_DISABLE_SCHEDULER=0`.

## 2. Frontend on Vercel

1. [vercel.com/new](https://vercel.com/new) → import the same GitHub repo.
2. **Root Directory:** `frontend` (important).
3. Framework: Next.js (auto).
4. Environment variables:

| Key | Value |
|-----|--------|
| `NEXT_PUBLIC_API_BASE_URL` | `https://htpp-digital-shadow-api.onrender.com` |
| `NEXT_PUBLIC_WS_URL` | `wss://htpp-digital-shadow-api.onrender.com/ws/live` |

5. Deploy. Copy the `*.vercel.app` URL into Render’s `HTPP_API_CORS_ORIGINS`, then **Manual Deploy** the API once so CORS updates.

## 3. Smoke check

- Floor loads 3 reactors
- Browser Network: `/api/...` → 200 from Render
- WebSocket `/ws/live` connects (may lag on cold start)
- What-if runs for R1/R2/R3

## Security note

v1 has no end-user login. Do not put real plant credentials on a fully public demo without IP allowlist / auth in front of the API.
