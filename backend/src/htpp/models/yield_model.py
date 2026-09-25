"""Yield models. Ridge is the headline. Steel is the negative control."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.preprocessing import StandardScaler

TARGETS = ("oil_yield_pct", "carbon_yield_pct", "steel_yield_pct")
BLOCK_A = ("feed_mass_kg", "moisture_pct")
BLOCK_B = (
    "peak_tr_c", "time_above_350c_min", "time_above_400c_min", "time_above_450c_min",
    "severity_index_c_min", "mean_roh_heating_c_per_min", "max_roh_c_per_min",
    "heating_duration_min", "gas_duration_min", "mean_amb_temp_c",
)
THERMAL = BLOCK_B + ("tau_cool_min", "q_in_heating_w", "alpha_final")


def time_split(frame: pd.DataFrame) -> dict[str, list[str]]:
    ordered = frame.sort_values("started_at")
    n = len(ordered)
    n_train = max(1, int(n * 0.70))
    n_val = max(1, int(n * 0.15))
    keys = ordered["batch_key"].tolist()
    return {
        "train": keys[:n_train],
        "val": keys[n_train:n_train + n_val],
        "test": keys[n_train + n_val:],
    }


def _matrix(frame: pd.DataFrame, columns: list[str], levels: list[str]) -> np.ndarray:
    data = frame.copy()
    numeric = data[columns].apply(pd.to_numeric, errors="coerce")
    numeric = numeric.fillna(numeric.median(numeric_only=True)).fillna(0.0)
    dummies = []
    series = data["feedstock_type"].fillna("unknown").astype(str)
    for level in levels:
        dummies.append((series == level).astype(float).to_numpy())
    extra = np.column_stack(dummies) if dummies else np.zeros((len(data), 0))
    return np.hstack([numeric.to_numpy(dtype=float), extra])


def _metrics(y: np.ndarray, pred: np.ndarray) -> dict:
    err = pred - y
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err**2)))
    denom = np.sum((y - np.mean(y)) ** 2)
    r2 = float(1 - np.sum(err**2) / denom) if denom else None
    mape = float(np.mean(np.abs(err) / np.clip(np.abs(y), 1e-6, None)) * 100)
    return {"mae": mae, "rmse": rmse, "r2": r2, "mape": mape, "n": int(len(y))}


def fit_targets(frame: pd.DataFrame) -> dict:
    usable = frame[frame["usable_for_training"] == True].dropna(subset=["oil_yield_pct"])  # noqa: E712
    if len(usable) < 8:
        return {"status": "insufficient_rows", "n": int(len(usable))}
    splits = time_split(usable)
    train = usable[usable["batch_key"].isin(splits["train"])]
    test = usable[usable["batch_key"].isin(splits["test"])]
    val = usable[usable["batch_key"].isin(splits["val"])]
    levels = sorted(usable["feedstock_type"].fillna("unknown").astype(str).unique())
    columns = list(BLOCK_A + BLOCK_B + ("tau_cool_min", "alpha_final"))
    report: dict = {"splits": {k: len(v) for k, v in splits.items()}, "targets": {}, "split_keys": splits}
    models = {}
    for target in TARGETS:
        y_train = train[target].to_numpy(dtype=float)
        x_train = _matrix(train, columns, levels)
        x_test = _matrix(test, columns, levels) if len(test) else np.zeros((0, len(columns) + len(levels)))
        scaler = StandardScaler()
        x_train_s = scaler.fit_transform(x_train)
        model = Ridge(alpha=1.0)
        model.fit(x_train_s, y_train)
        pred_test = model.predict(scaler.transform(x_test)) if len(test) else np.array([])
        y_test = test[target].to_numpy(dtype=float) if len(test) else np.array([])
        b0 = np.full_like(y_test, float(np.mean(y_train)))
        b1_model = LinearRegression().fit(train[["feed_mass_kg"]].fillna(0), y_train)
        b1 = b1_model.predict(test[["feed_mass_kg"]].fillna(0)) if len(test) else np.array([])
        a_cols = list(BLOCK_A)
        b2_x = _matrix(train, a_cols, levels)
        b2_scaler = StandardScaler().fit(b2_x)
        b2_model = Ridge(alpha=1.0).fit(b2_scaler.transform(b2_x), y_train)
        b2 = b2_model.predict(b2_scaler.transform(_matrix(test, a_cols, levels))) if len(test) else np.array([])
        # Conformal interval from validation residuals.
        if len(val):
            val_pred = model.predict(scaler.transform(_matrix(val, columns, levels)))
            resid = np.abs(val[target].to_numpy(dtype=float) - val_pred)
            half = float(np.quantile(resid, 0.8)) if len(resid) else 0.0
        else:
            half = float(np.std(y_train))
        names = columns + [f"feed_{level}" for level in levels]
        coefs = {name: float(value) for name, value in zip(names, model.coef_[: len(names)])}
        thermal_abs = float(np.mean([abs(coefs.get(name, 0.0)) for name in THERMAL]))
        feed_abs = float(np.mean([abs(v) for k, v in coefs.items() if k.startswith("feed_")])) if any(k.startswith("feed_") for k in coefs) else 0.0
        report["targets"][target] = {
            "held_out": _metrics(y_test, pred_test) if len(y_test) else None,
            "baseline_b0": _metrics(y_test, b0) if len(y_test) else None,
            "baseline_b1": _metrics(y_test, b1) if len(y_test) else None,
            "baseline_b2": _metrics(y_test, b2) if len(y_test) else None,
            "interval_halfwidth_pct": half,
            "coefficients": coefs,
            "steel_control" if target == "steel_yield_pct" else "note": {
                "mean_abs_thermal_coef": thermal_abs,
                "mean_abs_feedstock_coef": feed_abs,
                "passes": thermal_abs <= feed_abs + 1e-6,
            } if target == "steel_yield_pct" else "primary ridge model",
        }
        models[target] = {"model": model, "scaler": scaler, "columns": columns, "half": half, "feedstock_levels": sorted(train["feedstock_type"].dropna().unique())}
    report["status"] = "ok"
    report["models"] = models
    return report
