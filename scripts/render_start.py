"""Boot the API: prefer live DB; seed only if HTPP_ALLOW_SEED=1."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "backend" / "src")}
    subprocess.check_call([sys.executable, "-m", "htpp.cli", *args], cwd=ROOT, env=env)


def main() -> None:
    os.chdir(ROOT)
    os.environ.setdefault("PYTHONPATH", str(ROOT / "backend" / "src"))

    db = ROOT / "data" / "htpp.duckdb"
    artifacts = ROOT / "backend" / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (ROOT / "data").mkdir(parents=True, exist_ok=True)

    if not db.exists():
        if os.environ.get("HTPP_ALLOW_SEED") == "1":
            print("no database — seeding fixture (HTPP_ALLOW_SEED=1)")
            run("seed")
            run("fit")
        else:
            print("no database — init-db only (set HTPP_ALLOW_SEED=1 for offline fixture)")
            run("init-db")

    run("api")


if __name__ == "__main__":
    main()
