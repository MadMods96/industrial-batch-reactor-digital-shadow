"""Single-step global conversion. k0 and Ea are fit on the training split only."""

from __future__ import annotations

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import differential_evolution

from htpp.constants import EA_MAX_J_PER_MOL, EA_MIN_J_PER_MOL, R_J_PER_MOL_K


def alpha_final(tr_c: np.ndarray, t_s: np.ndarray, k0: float, ea: float, n: float = 1.0) -> float:
    order = np.argsort(t_s)
    t = t_s[order]
    tr = tr_c[order]
    if len(t) < 2:
        return 0.0

    def ode(_t, y):
        temp = np.interp(_t, t, tr) + 273.15
        rate = k0 * np.exp(-ea / (R_J_PER_MOL_K * temp)) * max(1.0 - y[0], 0.0) ** n
        if not np.isfinite(rate) or rate > 10.0:
            return [0.0]
        return [rate]

    try:
        sol = solve_ivp(ode, (t[0], t[-1]), [0.0], method="Radau", rtol=1e-3, atol=1e-4)
    except Exception:
        return 0.0
    if not sol.success:
        return 0.0
    return float(np.clip(sol.y[0, -1], 0.0, 1.0))


def fit_kinetics(histories: list[tuple[np.ndarray, np.ndarray]], yields: np.ndarray) -> dict:
    """Minimise the residual of a linear fit of volatile yield against alpha_final."""
    if len(histories) < 6:
        return {"k0": None, "ea_j_per_mol": None, "n": 1.0, "train_correlation": None, "n_batches": len(histories)}

    def objective(params: np.ndarray) -> float:
        k0, ea = params
        alphas = np.array([alpha_final(tr, t, k0, ea) for t, tr in histories])
        if np.std(alphas) < 1e-6:
            return 1.0
        slope, intercept = np.polyfit(alphas, yields, 1)
        pred = slope * alphas + intercept
        ss_res = np.sum((yields - pred) ** 2)
        ss_tot = np.sum((yields - np.mean(yields)) ** 2)
        return float(ss_res / ss_tot) if ss_tot else 1.0

    result = differential_evolution(
        objective,
        bounds=[(1e-3, 1e6), (EA_MIN_J_PER_MOL, EA_MAX_J_PER_MOL)],
        maxiter=12,
        popsize=6,
        seed=7,
        workers=1,
        polish=False,
    )
    k0, ea = (float(result.x[0]), float(result.x[1]))
    alphas = np.array([alpha_final(tr, t, k0, ea) for t, tr in histories])
    corr = float(np.corrcoef(alphas, yields)[0, 1]) if np.std(alphas) > 0 else 0.0
    return {
        "k0": k0,
        "ea_j_per_mol": ea,
        "n": 1.0,
        "train_correlation": corr,
        "n_batches": len(histories),
    }
