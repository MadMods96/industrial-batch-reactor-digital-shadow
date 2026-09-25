# Deploy on Vercel only (no Render)

This app can run **entirely on Vercel**: Next.js UI + `/api/*` demo routes + Claude.

## 1. Import repo

- [vercel.com/new](https://vercel.com/new) → this GitHub repo
- **Root Directory:** `frontend`
- Framework: Next.js

## 2. Environment variables (Vercel)

| Name | Required | Notes |
|------|----------|--------|
| `HTPP_ANTHROPIC_API_KEY` | for Ask | server-only, never `NEXT_PUBLIC_` |
| `HTPP_ANTHROPIC_WORKSPACE_ID` | for Ask | `wrkspc_…` |
| `HTPP_ANTHROPIC_MODEL` | optional | default `claude-sonnet-4-5` |
| `NEXT_PUBLIC_API_BASE_URL` | optional | leave **empty** or set to `same` |
| `NEXT_PUBLIC_WS_URL` | optional | leave **empty** or `poll` (HTTP snapshot) |

Do **not** set API/WS to `localhost`. Do **not** point them at the Vercel URL with a missing backend — same-origin `/api` is automatic on `*.vercel.app`.

## 3. Redeploy

After saving env vars: **Deployments → Redeploy**.

## What works on Vercel-only

- Floor (demo reactors via `/api/live/snapshot` poll)
- Insights + Ask (Claude if keys set)
- Batches / What-if (demo estimates)

Live PLC ingest + DuckDB fitted models still need a Python host later if you want production plant data.
