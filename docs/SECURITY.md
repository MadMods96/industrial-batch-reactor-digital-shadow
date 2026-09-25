# Security notes

## Never commit secrets

Keep these **out of git** (already in `.gitignore`):

- `.env` / `.env.local`
- DuckDB databases (`*.duckdb`)
- Plant Excel exports (`*.xlsx` except test fixtures)
- `column_map.local.yaml`

Use `.env.example` as the template. Values there must stay empty placeholders.

## Rotate if exposed

If a panel password or Anthropic key was ever pasted into chat, screenshots, or a public repo, **rotate it immediately** in the provider console and update local `.env` only.

## What the UI may show

The Ask panel only mentions that the assistant is not configured — it does **not** display API keys, passwords, or workspace ids.

## Before a public GitHub push

1. Confirm `git status` does not list `.env`
2. Search the tree for `sk-ant`, `password=`, and email addresses
3. Prefer a **private** repo until auth is added in front of the live API
