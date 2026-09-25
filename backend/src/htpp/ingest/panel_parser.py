"""HTML table parser. Columns are located by header name, never by index."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from selectolax.parser import HTMLParser

from htpp.schemas import FaultState, ProcessState, TelemetrySample

log = logging.getLogger("htpp.parser")
KOLKATA = ZoneInfo("Asia/Kolkata")

REQUIRED_HEADERS = {
    "batch no": "batch_no",
    "ts": "ts_c",
    "tr": "tr_c",
    "ps": "ps_bar",
    "pr": "pr_bar",
    "process": "process_raw",
    "roh": "roh_c_per_min",
    "roh cal": "roh_cal_c_per_min",
    "amb. temp": "amb_temp_c",
    "date time": "sampled_at",
    "version": "panel_version",
    "panel chip id": "panel_chip_id",
}


class SchemaDriftError(RuntimeError):
    """Required table headers are missing. Fail the run rather than shift columns."""


def _norm_header(text: str) -> str:
    cleaned = " ".join(text.replace("\xa0", " ").split()).rstrip(".").lower()
    return cleaned


def _load_map() -> dict[str, tuple[str, str]]:
    path = Path(__file__).with_name("process_map.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    mapping: dict[str, tuple[str, str]] = {}
    for item in data["mappings"]:
        key = " ".join(str(item["raw"]).split()).lower()
        mapping[key] = (item["process_state"], item["fault_state"])
    return mapping


PROCESS_MAP = _load_map()


def _to_float(text: str) -> float | None:
    raw = text.strip()
    if not raw or raw.upper() == "OPEN":
        return None
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def _temperature(text: str) -> float | None:
    """Return a temperature in degC, or None.

    The panel writes the sentinel -1 for a missing reading. Values outside
    0 to 900 degC are not physical for these vessels (doc 05 clamps there)
    and are stored as NULL rather than as a number.
    """
    value = _to_float(text)
    if value is None or value < 0 or value > 900:
        return None
    return value


def remap_rows(rows: list[TelemetrySample]) -> list[TelemetrySample]:
    """Re-apply the process map across a whole machine, not one HTML chunk."""
    rows.sort(key=lambda row: (row.machine_id, row.sampled_at))
    grouped: dict[int, list[TelemetrySample]] = {}
    for row in rows:
        grouped.setdefault(row.machine_id, []).append(row)
    mapped: list[TelemetrySample] = []
    for chunk in grouped.values():
        _apply_process_map(chunk)
        mapped.extend(chunk)
    return mapped


def _to_int(text: str) -> int | None:
    raw = text.strip()
    if not raw:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def parse_telemetry_table(html: str, machine_id: int, source_url: str) -> list[TelemetrySample]:
    if "No data available in table" in html and "<tbody" in html.lower():
        # Still try the table; an empty body is a valid zero-row response.
        pass
    tree = HTMLParser(html)
    table = _find_table(tree)
    if table is None:
        if "No data available in table" in html:
            return []
        raise SchemaDriftError("No telemetry table found. Headers found: []")

    headers = [_norm_header(cell.text(strip=True)) for cell in table.css("thead th, thead td")]
    index = {name: i for i, name in enumerate(headers) if name}
    missing = [name for name in REQUIRED_HEADERS if name not in index]
    if missing:
        raise SchemaDriftError(f"Missing headers {missing}. Headers found: {headers}")

    rows: list[TelemetrySample] = []
    now = datetime.now(timezone.utc)
    for tr in table.css("tbody tr"):
        cells = [cell.text(strip=True) for cell in tr.css("td")]
        if not cells or "no data available" in " ".join(cells).lower():
            continue
        if len(cells) <= max(index.values()):
            continue

        def cell(key: str) -> str:
            return cells[index[key]]

        stamp = cell("date time")
        if not stamp:
            continue
        local = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KOLKATA)
        sampled_at = local.astimezone(timezone.utc)
        raw_process = cell("process")
        rows.append(
            TelemetrySample(
                machine_id=machine_id,
                sampled_at=sampled_at,
                batch_no=_to_int(cell("batch no")),
                ts_c=_temperature(cell("ts")),
                tr_c=_temperature(cell("tr")),
                ps_bar=_to_float(cell("ps")),
                pr_bar=_to_float(cell("pr")),
                process_raw=raw_process or None,
                roh_c_per_min=_to_float(cell("roh")),
                roh_cal_c_per_min=_to_float(cell("roh cal")),
                amb_temp_c=_temperature(cell("amb. temp")),
                panel_version=cell("version") or None,
                panel_chip_id=cell("panel chip id") or None,
                ingested_at=now,
                source_url=source_url,
            )
        )
    rows.sort(key=lambda row: row.sampled_at)
    _apply_process_map(rows)
    return rows


def _find_table(tree: HTMLParser):
    for table in tree.css("table"):
        headers = {_norm_header(cell.text(strip=True)) for cell in table.css("thead th, thead td")}
        if {"batch no", "tr", "date time"} <= headers:
            return table
    return None


def _apply_process_map(rows: list[TelemetrySample]) -> None:
    last_process: dict[int | None, ProcessState] = {}
    for row in rows:
        key = " ".join((row.process_raw or "").split()).lower()
        mapped = PROCESS_MAP.get(key)
        if mapped is None:
            row.process_state = ProcessState.UNKNOWN
            row.fault_state = FaultState.UNKNOWN_FAULT
            if row.process_raw:
                log.warning(
                    "unmapped process_raw machine=%s at=%s raw=%r",
                    row.machine_id,
                    row.sampled_at.isoformat(),
                    row.process_raw,
                )
            continue
        process_name, fault_name = mapped
        row.fault_state = FaultState(fault_name)
        if process_name == "carry_previous":
            carried = last_process.get(row.batch_no, ProcessState.UNKNOWN)
            row.process_state = carried
        else:
            row.process_state = ProcessState(process_name)
            last_process[row.batch_no] = row.process_state
