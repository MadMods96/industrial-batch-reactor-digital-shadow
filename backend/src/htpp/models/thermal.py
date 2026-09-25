"""Lumped-capacitance identification. Cooling is fitted before heating."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

from htpp.constants import CP_CHARGE_J_PER_KG_K


@dataclass
class CoolingFit:
    tau_cool_min: float | None
    tr0_c: float | None
    r_squared: float | None
    rmse_c: float | None
    n_points: int
    converged: bool


def fit_cooling_tau(t_s: np.ndarray, tr_c: np.ndarray, amb_c: np.ndarray) -> CoolingFit:
    """Nonlinear least squares for tau_cool (minutes) and Tr_0 (degC).

    t_s is seconds from the cooling-phase start, built from actual timestamps.
    """
    mask = ~np.isnan(tr_c) & ~np.isnan(t_s)
    t_s, tr_c = t_s[mask], tr_c[mask]
    n = int(len(tr_c))
    if n < 8:
        return CoolingFit(None, None, None, None, n, False)
    amb = float(np.nanmean(amb_c)) if np.isfinite(np.nanmean(amb_c)) else 28.0
    if np.nanmax(amb_c) - np.nanmin(amb_c) > 3:
        amb = float(np.nanmean(amb_c))
    excess = np.clip(tr_c - amb, 1e-3, None)
    slope = np.polyfit(t_s, np.log(excess), 1)[0]
    tau0 = 1.0 / max(-slope, 1e-6)
    tau0 = float(np.clip(tau0, 60.0, 2000.0 * 60.0))

    def model(t, tau_s, tr0):
        return amb + (tr0 - amb) * np.exp(-t / tau_s)

    try:
        popt, _ = curve_fit(
            model,
            t_s,
            tr_c,
            p0=[tau0, float(tr_c[0])],
            bounds=([60.0, 0.0], [2000.0 * 60.0, 900.0]),
            maxfev=4000,
        )
    except (RuntimeError, ValueError):
        return CoolingFit(None, None, None, None, n, False)
    pred = model(t_s, *popt)
    resid = tr_c - pred
    ss_res = float(np.sum(resid**2))
    ss_tot = float(np.sum((tr_c - np.mean(tr_c)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    rmse = float(np.sqrt(np.mean(resid**2)))
    converged = bool(r2 >= 0.9)
    return CoolingFit(
        tau_cool_min=float(popt[0] / 60.0) if converged else None,
        tr0_c=float(popt[1]) if converged else None,
        r_squared=r2,
        rmse_c=rmse,
        n_points=n,
        converged=converged,
    )


def separate_ua(tau_min: np.ndarray, feed_kg: np.ndarray) -> dict:
    """Linear regression of tau_cool against feed mass.

    tau = C_shell/UA + feed_mass * cp / UA. cp is the cited literature value.
    """
    mask = ~np.isnan(tau_min) & ~np.isnan(feed_kg)
    if mask.sum() < 4:
        return {"ua_eff_w_per_k": None, "c_shell_j_per_k": None, "r_squared": None, "n": int(mask.sum())}
    x = feed_kg[mask]
    y = tau_min[mask] * 60.0
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot else 0.0
    ua = CP_CHARGE_J_PER_KG_K / slope if slope > 0 else None
    c_shell = intercept * ua if ua else None
    return {
        "ua_eff_w_per_k": None if ua is None else float(ua),
        "c_shell_j_per_k": None if c_shell is None else float(c_shell),
        "r_squared": float(r2),
        "n": int(mask.sum()),
        "cp_charge_j_per_kg_k": CP_CHARGE_J_PER_KG_K,
    }


def fit_heating(t_s: np.ndarray, tr_c: np.ndarray, amb: float, tau_cool_s: float, ua: float) -> dict:
    """Fit constant Q_H and tau_h. tau_h is bounded to a factor of three of tau_cool."""
    if len(tr_c) < 6 or not np.isfinite(ua) or ua <= 0:
        return {"q_in_heating_w": None, "tau_h_min": None, "converged": False}

    lo = tau_cool_s / 3.0
    hi = tau_cool_s * 3.0

    def model(t, q_h, tau):
        return amb + (q_h / ua) * (1 - np.exp(-t / tau)) + (tr_c[0] - amb) * np.exp(-t / tau)

    try:
        popt, _ = curve_fit(
            model,
            t_s,
            tr_c,
            p0=[ua * max(tr_c[-1] - amb, 1.0), tau_cool_s],
            bounds=([0.0, lo], [5e6, hi]),
            maxfev=4000,
        )
    except (RuntimeError, ValueError):
        return {"q_in_heating_w": None, "tau_h_min": None, "converged": False}
    return {
        "q_in_heating_w": float(popt[0]),
        "tau_h_min": float(popt[1] / 60.0),
        "converged": True,
    }
