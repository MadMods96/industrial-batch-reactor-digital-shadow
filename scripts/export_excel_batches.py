"""One-shot: plant Excel → anonymized batch JSON for Vercel history seed."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

SRC = Path(r"c:\Users\cto\Desktop\GA\fly\sagar_bhai_wagholi-plant.xlsx")
OUT = Path(__file__).resolve().parents[1] / "frontend" / "lib" / "demo" / "plant_batches.json"

ALIASES = {
    "r1": 1093,
    "reactor 1": 1093,
    "unit 1": 1093,
    "r2": 1094,
    "reactor 2": 1094,
    "unit 2": 1094,
    "r3": 1146,
    "reactor 3": 1146,
    "unit 3": 1146,
}


def main() -> None:
    wb = load_workbook(SRC, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    header_idx = None
    headers: list[str] = []
    for i, row in enumerate(rows[:5]):
        vals = [str(c).strip().lower() if c is not None else "" for c in row]
        if "date" in vals and "reactor" in vals:
            header_idx = i
            headers = vals
            break
    if header_idx is None:
        raise SystemExit("header not found")

    def col(*names: str) -> int | None:
        for name in names:
            if name in headers:
                return headers.index(name)
        return None

    i_date = col("date")
    i_reac = col("reactor")
    i_load = col("loading")
    i_moist = col("net moisture")
    i_oil = col("oil(kg)")
    i_carb = col("carbon(kg)")
    i_steel = col("steel(kg)")
    i_oilp = col("oil %")
    i_total_min = col("total in min")

    batches: list[dict] = []
    for row in rows[header_idx + 1 :]:
        if not row or row[i_date] is None or row[i_reac] is None:
            continue
        reac = str(row[i_reac]).strip().lower()
        mid = ALIASES.get(reac)
        if mid is None:
            for key, value in ALIASES.items():
                if key in reac:
                    mid = value
                    break
        if mid is None:
            continue

        d = row[i_date]
        day = d.date().isoformat() if isinstance(d, datetime) else str(d)[:10]

        def num(idx: int | None) -> float | None:
            if idx is None:
                return None
            value = row[idx]
            try:
                return float(value) if value is not None and str(value).strip() != "" else None
            except (TypeError, ValueError):
                return None

        feed = num(i_load)
        oil_kg = num(i_oil)
        oil_pct = num(i_oilp)
        if oil_pct is not None and oil_pct <= 1.5:
            oil_pct *= 100
        if oil_pct is None and feed and oil_kg is not None:
            oil_pct = 100.0 * oil_kg / feed

        carbon_kg = num(i_carb)
        steel_kg = num(i_steel)
        carbon_pct = (100.0 * carbon_kg / feed) if feed and carbon_kg is not None else None
        steel_pct = (100.0 * steel_kg / feed) if feed and steel_kg is not None else None

        duration = num(i_total_min)
        # Workbook "total in min" values are ~30–35 → actually hours; store minutes.
        duration_min = round(duration * 60, 1) if duration is not None and duration < 100 else duration

        batch_no = len([b for b in batches if b["machine_id"] == mid]) + 1
        batches.append(
            {
                "batch_key": f"{mid}-{day.replace('-', '')}-B{batch_no}",
                "machine_id": mid,
                "batch_no": batch_no,
                "log_date": day,
                "total_duration_min": duration_min,
                "peak_tr_c": None,
                "had_fault": False,
                "usable_for_training": True,
                "oil_yield_pct": round(oil_pct, 2) if oil_pct is not None else None,
                "carbon_yield_pct": round(carbon_pct, 2) if carbon_pct is not None else None,
                "steel_yield_pct": round(steel_pct, 2) if steel_pct is not None else None,
                "feed_mass_kg": feed,
                "moisture_pct": num(i_moist),
                "oil_mass_kg": oil_kg,
                "carbon_mass_kg": carbon_kg,
                "steel_mass_kg": steel_kg,
                "quality_flags": [],
                "source": "plant_excel_log",
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": "anonymized plant batch log (mass / yield / time)",
        "note": "Site/customer names removed. Seed history for Vercel Batches + pattern baselines.",
        "n_batches": len(batches),
        "batches": batches,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {len(batches)} batches -> {OUT}")


if __name__ == "__main__":
    main()
