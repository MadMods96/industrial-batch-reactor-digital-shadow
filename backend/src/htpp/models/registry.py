"""Assemble batches, features and versioned model artefacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from htpp.config import settings
from htpp.constants import CP_CHARGE_CITATION, EA_CITATION
from htpp.models.interpolate import dense_trajectory
from htpp.models.thermal import fit_cooling_tau, fit_heating, separate_ua
from htpp.models.yield_model import fit_targets
from htpp.store.db import connect, migrate
from htpp.store.queries import load_features, load_phases, load_telemetry
from htpp.store.writes import replace_features


def fit_models() -> Path:
    con = migrate(connect())
    features = load_features(con)
    telemetry = load_telemetry(con)
    phases = load_phases(con)
    if features.empty:
        con.close()
        raise RuntimeError("No features to fit. Run build first.")

    fits = []
    for batch in features.itertuples(index=False):
        phase = phases[(phases["batch_key"] == batch.batch_key) & (phases["process_state"] == "cooling")]
        if phase.empty or int(phase.iloc[0]["n_samples"]) < 2:
            continue
        samples = _batch_samples(telemetry, int(batch.machine_id), int(str(batch.batch_key).split("-")[1]))
        start = pd.Timestamp(phase.iloc[0]["started_at"])
        end = pd.Timestamp(phase.iloc[0]["ended_at"])
        window = samples[(samples["sampled_at"] >= start) & (samples["sampled_at"] <= end)]
        if len(window) < 8:
            continue
        t0 = window["sampled_at"].iloc[0]
        t_s = (window["sampled_at"] - t0).dt.total_seconds().to_numpy()
        fit = fit_cooling_tau(t_s, window["tr_c"].to_numpy(dtype=float), window["amb_temp_c"].to_numpy(dtype=float))
        fits.append({"batch_key": batch.batch_key, "machine_id": int(batch.machine_id), **fit.__dict__})
        if fit.converged and fit.tau_cool_min:
            features.loc[features["batch_key"] == batch.batch_key, "tau_cool_min"] = fit.tau_cool_min

    per_machine = {}
    for machine_id, group in features.groupby("machine_id"):
        sep = separate_ua(group["tau_cool_min"].to_numpy(dtype=float), group["feed_mass_kg"].to_numpy(dtype=float))
        taus = group["tau_cool_min"].dropna()
        cv = float(taus.std() / taus.mean()) if len(taus) > 1 and taus.mean() else None
        per_machine[str(int(machine_id))] = {
            **sep,
            "n_tau": int(taus.shape[0]),
            "tau_median_min": None if taus.empty else float(taus.median()),
            "tau_iqr_min": None if len(taus) < 2 else float(taus.quantile(0.75) - taus.quantile(0.25)),
            "tau_cv": cv,
            "q_h_w": _median_heating(telemetry, phases, features, int(machine_id), sep.get("ua_eff_w_per_k")),
        }
        ua = sep.get("ua_eff_w_per_k")
        c_shell = sep.get("c_shell_j_per_k") or 0.0
        if ua:
            features.loc[features["machine_id"] == machine_id, "ua_eff_w_per_k"] = ua
            mass = features.loc[features["machine_id"] == machine_id, "feed_mass_kg"]
            features.loc[features["machine_id"] == machine_id, "c_eff_j_per_k"] = c_shell + mass * 1900.0
            features.loc[features["machine_id"] == machine_id, "q_in_heating_w"] = per_machine[str(int(machine_id))]["q_h_w"]

    yield_report = fit_targets(features)
    models = yield_report.pop("models", {})
    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = settings.artifacts / version
    out.mkdir(parents=True, exist_ok=True)
    ranges = {
        "feed_mass_kg": _range(features, "feed_mass_kg"),
        "moisture_pct": _range(features, "moisture_pct"),
        "target_peak_tr_c": _range(features, "peak_tr_c"),
    }
    payload = {
        "version": version,
        "cp_charge_citation": CP_CHARGE_CITATION,
        "ea_citation": EA_CITATION,
        "per_machine": per_machine,
        "cooling_fits": fits,
        "yield": {k: v for k, v in yield_report.items() if k != "split_keys"},
        "train_ranges": ranges,
        "data_note": (
            "Yield targets come from the configured batch log. If that file is the "
            "synthetic fixture, these numbers are not plant findings."
        ),
        "interpolation_mode": "model" if any(item.get("ua_eff_w_per_k") for item in per_machine.values()) else "linear_fallback",
    }
    (out / "metrics.json").write_text(json.dumps(_jsonable(payload), indent=2), encoding="utf-8")
    (out / "split_manifest.json").write_text(
        json.dumps(yield_report.get("split_keys", {}), indent=2),
        encoding="utf-8",
    )
    (out / "thermal_per_machine.json").write_text(json.dumps(_jsonable(per_machine), indent=2), encoding="utf-8")
    if models:
        joblib.dump(models, out / "yield_models.joblib")
    latest = settings.artifacts / "LATEST"
    latest.write_text(version, encoding="utf-8")
    replace_features(con, features)
    con.close()
    return out


def load_latest() -> dict:
    latest = settings.artifacts / "LATEST"
    if not latest.exists():
        return {}
    version = latest.read_text(encoding="utf-8").strip()
    path = settings.artifacts / version / "metrics.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    data["model_version"] = version
    return data


def machine_params(machine_id: int) -> dict:
    data = load_latest()
    return data.get("per_machine", {}).get(str(machine_id), {})


def project_machine(row: pd.Series) -> dict:
    params = machine_params(int(row["machine_id"]))
    tr = 30.0 if pd.isna(row.get("tr_c")) else float(row["tr_c"])
    if not np.isfinite(tr):
        tr = 30.0
    traj = dense_trajectory(
        tr_c=tr,
        ts_c=None if pd.isna(row.get("ts_c")) else float(row["ts_c"]),
        pr_bar=None if pd.isna(row.get("pr_bar")) else float(row["pr_bar"]),
        ps_bar=None if pd.isna(row.get("ps_bar")) else float(row["ps_bar"]),
        amb_temp_c=None if pd.isna(row.get("amb_temp_c")) else float(row["amb_temp_c"]),
        process_state=str(row.get("process_state") or "unknown"),
        tau_cool_min=params.get("tau_median_min"),
        q_in_w=params.get("q_h_w"),
        ua_w_per_k=params.get("ua_eff_w_per_k"),
    )
    return {
        "interpolation_mode": traj.interpolation_mode,
        "dense": {
            "step_s": traj.step_s,
            "horizon_s": traj.horizon_s,
            "tr_c": _finite_list(traj.tr_c),
            "ts_c": _finite_list(traj.ts_c),
            "pr_bar": _finite_list(traj.pr_bar),
            "ps_bar": _finite_list(traj.ps_bar),
            "process_state": traj.process_state,
        },
    }


def _finite_list(values: list[float]) -> list[float | None]:
    out: list[float | None] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            out.append(None)
            continue
        out.append(None if not np.isfinite(number) else number)
    return out


def _batch_samples(telemetry: pd.DataFrame, machine_id: int, batch_no: int) -> pd.DataFrame:
    frame = telemetry.copy()
    frame["sampled_at"] = pd.to_datetime(frame["sampled_at"], utc=True)
    return frame[(frame["machine_id"] == machine_id) & (frame["batch_no"] == batch_no)].sort_values("sampled_at")


def _median_heating(telemetry, phases, features, machine_id, ua) -> float | None:
    if not ua:
        return None
    values = []
    subset = features[features["machine_id"] == machine_id]
    for batch in subset.itertuples(index=False):
        if not batch.tau_cool_min or pd.isna(batch.tau_cool_min):
            continue
        phase = phases[(phases["batch_key"] == batch.batch_key) & (phases["process_state"] == "heating")]
        if phase.empty:
            continue
        samples = _batch_samples(telemetry, machine_id, int(str(batch.batch_key).split("-")[1]))
        start = pd.Timestamp(phase.iloc[0]["started_at"])
        end = pd.Timestamp(phase.iloc[0]["ended_at"])
        window = samples[(samples["sampled_at"] >= start) & (samples["sampled_at"] <= end)]
        if len(window) < 6:
            continue
        t0 = window["sampled_at"].iloc[0]
        t_s = (window["sampled_at"] - t0).dt.total_seconds().to_numpy()
        amb = float(window["amb_temp_c"].mean())
        fit = fit_heating(t_s, window["tr_c"].to_numpy(dtype=float), amb, float(batch.tau_cool_min) * 60.0, float(ua))
        if fit["converged"] and fit["q_in_heating_w"]:
            values.append(fit["q_in_heating_w"])
    return float(np.median(values)) if values else None


def _range(frame: pd.DataFrame, column: str) -> list[float] | None:
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return None
    return [float(values.min()), float(values.max())]


def _jsonable(value):
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    return value
