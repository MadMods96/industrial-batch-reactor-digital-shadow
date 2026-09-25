"""Paper figures. Greyscale-legible: bars use hatching, lines use different styles."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def write_figures(artifact_dir: Path) -> None:
    metrics = json.loads((artifact_dir / "metrics.json").read_text(encoding="utf-8"))
    out = artifact_dir / "figures"
    out.mkdir(exist_ok=True)
    _tau(metrics, out / "F5_tau_cool.svg")
    _yields(metrics, out / "F10_yield_mae.svg")
    print(f"figures in {out}")


def _tau(metrics: dict, path: Path) -> None:
    labels, values = [], []
    for machine, payload in metrics.get("per_machine", {}).items():
        labels.append(machine)
        values.append(payload.get("tau_median_min") or 0)
    fig, ax = plt.subplots(figsize=(4.5, 3))
    ax.bar(labels, values, color="#4c566a", hatch="//", edgecolor="black")
    ax.set_xlabel("machine_id")
    ax.set_ylabel("tau_cool_min")
    ax.set_title(f"RQ1 cooling time constant (n per machine in metrics.json)")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _yields(metrics: dict, path: Path) -> None:
    targets = metrics.get("yield", {}).get("targets", {})
    names = list(targets)
    if not names:
        return
    fig, ax = plt.subplots(figsize=(5, 3))
    held = [((targets[n].get("held_out") or {}).get("mae") or 0) for n in names]
    base = [((targets[n].get("baseline_b2") or {}).get("mae") or 0) for n in names]
    import numpy as np
    x = np.arange(len(names))
    ax.bar(x - 0.15, held, width=0.3, label="ridge", hatch="..", edgecolor="black", color="#d8dee9")
    ax.bar(x + 0.15, base, width=0.3, label="B2 feedstock", hatch="xx", edgecolor="black", color="#4c566a")
    ax.set_xticks(x, names, rotation=15)
    ax.set_ylabel("held-out MAE, yield %")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
