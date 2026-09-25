# Connect HTPP Digital Shadow to Claude Desktop (MCP)

The public Vercel site **does not** call the Anthropic API anymore (no credit burn, no leaked billing errors).

For plant Q&A, run this repo’s **MCP server** locally and attach it to **Claude Desktop**. Claude then calls read-only tools over the Excel-seeded batch history and can cite `batch_key` values.

## What you get

| Tool | Purpose |
|------|---------|
| `list_batches` | Filter R1/R2/R3 history |
| `get_batch` | One row by `R1-2026-08-01` style key |
| `summarize_yields` | Per-reactor averages |
| `data_notes` | Provenance (estimated carbon, duration rules, etc.) |

## 1. Install once

```powershell
cd htpp-digital-twin\mcp
npm install
```

Confirm:

```powershell
node src/index.js
```

(It waits on stdio — that’s correct. Stop with Ctrl+C.)

## 2. Claude Desktop config

Edit Claude’s config file:

- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

Add (adjust the path to your machine):

```json
{
  "mcpServers": {
    "htpp-digital-shadow": {
      "command": "node",
      "args": [
        "C:\\Users\\cto\\Desktop\\GA\\fly\\htpp-digital-twin\\mcp\\src\\index.js"
      ]
    }
  }
}
```

Use your real absolute path. Forward slashes also work on Windows:

`"C:/Users/cto/Desktop/GA/fly/htpp-digital-twin/mcp/src/index.js"`

## 3. Restart Claude Desktop

Fully quit Claude Desktop and reopen. You should see the MCP tools under the HTPP server.

## 4. Example prompts

- “Using HTPP tools, summarize oil yield for R1 vs R2. Cite batch keys.”
- “Get batch R1-2026-09-20 and explain its quality flags.”
- “What does `carbon_imputed` mean in this dataset?”

## Rules Claude should follow

- Read-only digital **shadow** — never claim it can change setpoints.
- Cite `batch_key` when stating yields.
- Say carbon is a **plant estimate**.
- Say water recovered is an **output**, not feed moisture.
- Do not invent panel temperatures; this seed has no live PLC series.

## Optional: Cursor

You can also register the same server in Cursor MCP settings with the same `command` / `args`.

## Security

- Do not point a public website at your Anthropic key.
- This MCP reads only the anonymized JSON seed in-repo (`frontend/lib/demo/plant_batches.json`).
- Keep Vercel Deployment Protection on until written plant consent exists (Fix Brief 003 P0-1).
