"""Boot the API on Render: seed demo data if empty, then serve."""

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
        print("no database yet — seeding demo fixture + fitting models")
        run("seed")
        run("fit")
    elif not (artifacts / "LATEST").exists():
        print("database present but no model artefacts — fitting")
        run("fit")

    run("api")


if __name__ == "__main__":
    main()
