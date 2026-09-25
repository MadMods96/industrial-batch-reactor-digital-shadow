"""Plant display labels — never put customer names in source.

Configure via env:

  HTPP_PLANT_LABEL=Plant Floor
  HTPP_MACHINE_LABELS=1093:R1 Unit 1,1094:R2 Unit 2,1146:R3 Unit 3
  HTPP_MACHINE_ALIASES=Unit 1:1093,R1:1093,Unit 2:1094,R2:1094,Unit 3:1146,R3:1146
"""

from __future__ import annotations

from htpp.config import settings


def plant_label() -> str:
    return (settings.plant_label or "Plant Floor").strip()


def machine_label(machine_id: int) -> str:
    labels = settings.machine_label_map()
    if machine_id in labels:
        return labels[machine_id]
    slots = {mid: idx for idx, mid in enumerate(settings.machine_ids)}
    if machine_id in slots:
        return f"R{slots[machine_id] + 1}"
    return f"Reactor {machine_id}"


def machine_short(machine_id: int) -> str:
    text = machine_label(machine_id)
    return text.split()[0] if text else f"M{machine_id}"
