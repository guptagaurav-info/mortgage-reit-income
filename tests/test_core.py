import numpy as np, pandas as pd, sys
sys.path.insert(0, "src")
from mrc.core import par_bond_return, ols_hac, perf, vol_timing


def test_par_bond_unchanged_yield_earns_coupon():
    assert abs(par_bond_return(0.04, 0.04) - 0.04 / 52) < 1e-6


def test_par_bond_loses_when_yield_rises():
    assert par_bond_return(0.04, 0.05) < -0.03


def test_ols_recovers_known_coefficients():
    rng = np.random.default_rng(0); x = rng.normal(size=(2000, 2)); y = 0.5 + 2 * x[:, 0] - x[:, 1] + rng.normal(scale=0.1, size=2000)
    b, t, r2 = ols_hac(y, x); assert np.allclose(b, [0.5, 2, -1], atol=0.02) and r2 > 0.99


def test_perf_flat_series():
    p = perf(pd.Series([0.0] * 104)); assert p["cagr"] == 0 and p["maxdd"] == 0


def test_timing_uses_only_past_vol():
    """Changing this week's realised vol must not change this week's position (no look-ahead)."""
    idx = pd.date_range("2000-01-07", periods=400, freq="W-FRI"); rng = np.random.default_rng(1)
    W = pd.DataFrame({"mreit": rng.normal(0, .02, 400), "bill": 0.0005, "rvol": rng.uniform(.01, .03, 400)}, index=idx)
    _, d1 = vol_timing(W, test_start="2005-01-01"); W2 = W.copy(); W2.iloc[300, W2.columns.get_loc("rvol")] = 9.9
    _, d2 = vol_timing(W2, test_start="2005-01-01"); c = idx[300]; assert d1.on.loc[:c].equals(d2.on.loc[:c]) and not d1.on.loc[idx[301]:].equals(d2.on.loc[idx[301]:])
