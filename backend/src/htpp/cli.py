"""Command line. `python -m htpp.cli <command>`."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from htpp.store.db import connect, migrate


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(prog="htpp")
    parser.add_argument("command", choices=[
        "init-db", "seed", "backfill", "ingest", "excel", "build", "fit",
        "coverage", "reproduce", "reparse", "api",
    ])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    commands[args.command](args)


def _init_db(_args) -> None:
    migrate(connect()).close()
    print("database ready")


def _seed(args) -> None:
    from htpp.ingest.seed_fixture import seed
    from htpp.batches.assemble import assemble
    n = seed(force=args.force)
    stats = assemble()
    print(json.dumps({"seeded_rows": n, **stats}))


def _backfill(_args) -> None:
    from htpp.ingest.backfill import backfill
    failures = asyncio.run(backfill())
    if failures:
        print(f"backfill finished with {failures} failed chunks")
        sys.exit(1)
    print("backfill complete")


def _ingest(_args) -> None:
    from htpp.ingest.incremental import incremental_tick
    print(asyncio.run(incremental_tick()))


def _excel(_args) -> None:
    from pathlib import Path
    from htpp.config import settings
    from htpp.ingest.excel_log import ExcelMapError, parse_workbook, resolve_batch_numbers
    from htpp.store.writes import upsert_batch_log
    from htpp.batches.assemble import assemble
    con = migrate(connect())
    total = 0
    unmatched_all: list[dict] = []
    for path in Path(settings.excel_dir).glob("*.xlsx"):
        try:
            entries = parse_workbook(path)
        except ExcelMapError as exc:
            print(f"{path.name}: skipped ({exc})")
            continue
        matched, unmatched = resolve_batch_numbers(con, entries)
        unmatched_all.extend(unmatched)
        inserted, updated = upsert_batch_log(con, matched)
        total += inserted + updated
        print(f"{path.name}: matched={len(matched)} unmatched={len(unmatched)} inserted={inserted} updated={updated}")
    con.close()
    print(json.dumps({"rows_written": total, "unmatched": unmatched_all, "build": assemble()}))


def _reparse(_args) -> None:
    from htpp.batches.assemble import assemble
    from htpp.ingest.reparse import reparse

    n = reparse()
    print(json.dumps({"reparsed_rows": n, **assemble()}))


def _build(_args) -> None:
    from htpp.batches.assemble import assemble
    print(json.dumps(assemble()))


def _fit(_args) -> None:
    from htpp.models.registry import fit_models
    print(fit_models())


def _coverage(_args) -> None:
    from htpp.store.queries import daily_coverage, gaps, machine_summaries
    con = migrate(connect())
    print(machine_summaries(con).to_string(index=False))
    print(daily_coverage(con).to_string(index=False))
    print("gaps")
    print(gaps(con).head(20).to_string(index=False))
    con.close()


def _reproduce(_args) -> None:
    from htpp.batches.assemble import assemble
    from htpp.models.registry import fit_models
    from htpp.report.figures import write_figures
    from htpp.report.validation import write_report
    print(assemble())
    path = fit_models()
    write_figures(path)
    write_report(path)
    print(path)


def _api(_args) -> None:
    import os

    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("htpp.api.main:app", host=host, port=port, reload=False)


commands = {
    "init-db": _init_db,
    "seed": _seed,
    "backfill": _backfill,
    "ingest": _ingest,
    "excel": _excel,
    "build": _build,
    "fit": _fit,
    "coverage": _coverage,
    "reproduce": _reproduce,
    "reparse": _reparse,
    "api": _api,
}


if __name__ == "__main__":
    main()
