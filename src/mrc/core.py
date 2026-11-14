"""Weekly total returns for agency mortgage REITs, SPY, JNK and a 5-year par Treasury, plus rate factors.
Data: defeatbeta/yahoo-finance-data (Hugging Face, ODC-BY): split-adjusted daily closes, split-adjusted
dividends (ex-dates), and US Treasury par yields."""
import duckdb, numpy as np, pandas as pd

RAW = "data/raw/"
AGENCY = ["AGNC", "NLY", "ARR", "ORC", "DX", "TWO"]
OTHER = ["SPY", "JNK"]


def daily_tr(symbols):
    sy = ",".join(f"'{s}'" for s in symbols)
    px = duckdb.sql(f"select symbol s, cast(report_date as date) d, cast(close as double) c from '{RAW}stock_prices.parquet' where symbol in ({sy})").df()
    dv = duckdb.sql(f"select symbol s, cast(report_date as date) d, cast(amount as double) a from '{RAW}stock_dividend_events.parquet' where symbol in ({sy})").df()
    px["d"] = pd.to_datetime(px.d); dv["d"] = pd.to_datetime(dv.d)
    P = px.pivot_table(index="d", columns="s", values="c").sort_index()
    D = dv.groupby(["d", "s"]).a.sum().unstack().reindex(P.index).fillna(0.0)
    D = D.reindex(columns=P.columns, fill_value=0.0)
    tr = (P + D) / P.shift(1) - 1
    pr = P / P.shift(1) - 1
    return tr, pr, P, D


def yields():
    y = duckdb.sql(f"select cast(report_date as date) d, cast(bc_3month as double) m3, cast(bc_5year as double) y5, cast(bc_10year as double) y10 from '{RAW}daily_treasury_yield.parquet'").df()
    y["d"] = pd.to_datetime(y.d)
    return y.set_index("d").sort_index().dropna()


def par_bond_return(y0, y1, years=5.0, m=52):
    n = int(round((years - 1.0 / m) * 2)); c, r = y0 / 2, y1 / 2
    return c * (1 - (1 + r) ** -n) / r + (1 + r) ** -n - 1 + y0 / m


def weekly(start="2008-06-01", end=None):
    tr, pr, P, D = daily_tr(AGENCY + OTHER)
    y = yields()
    g = lambda r: (1 + r.fillna(0)).resample("W-FRI").prod() - 1
    W = g(tr)
    have = P.notna().resample("W-FRI").last() & P.shift(5).notna().resample("W-FRI").last()  # listed for the full week
    W = W.where(have)
    W.loc[:"2009-12-31", "ARR"] = np.nan        # ARR was a SPAC until its Nov 2009 merger into ARMOUR Residential REIT
    yw = y.resample("W-FRI").last()
    W["dy10"] = yw.y10.diff(); W["dy5"] = yw.y5.diff()
    W["bill"] = yw.m3.shift(1) / 52
    W["T5"] = pd.Series([par_bond_return(a, b) for a, b in zip(yw.y5.shift(1), yw.y5)], index=yw.index)
    dly = y.y10.diff()
    W["rvol"] = (dly ** 2).resample("W-FRI").sum() ** 0.5            # realised 10y yield vol within the week (decimal)
    W["mreit"] = W[AGENCY].mean(axis=1, skipna=True)                  # equal-weight, rebalanced weekly
    W = W.loc[start:end].dropna(subset=["SPY", "dy10", "bill", "T5"])
    return W, P, D


def ols_hac(y, X, lags=4):
    X = np.column_stack([np.ones(len(X)), X]); b = np.linalg.lstsq(X, y, rcond=None)[0]; e = y - X @ b
    XtXi = np.linalg.inv(X.T @ X); S = (X * e[:, None]).T @ (X * e[:, None])
    for l in range(1, lags + 1):
        w = 1 - l / (lags + 1); G = (X[l:] * e[l:, None]).T @ (X[:-l] * e[:-l, None]); S += w * (G + G.T)
    se = np.sqrt(np.diag(XtXi @ S @ XtXi)); r2 = 1 - e.var() / y.var()
    return b, b / se, r2


def convexity_reg(W, col):
    """r - bill = a + b_spy (SPY - bill) + b_dur dy + b_cvx dy^2, dy in percentage points. b_cvx < 0 = short options."""
    d = W[[col, "SPY", "bill", "dy10"]].dropna()
    y = (d[col] - d.bill).values; dy = d.dy10.values * 100
    b, t, r2 = ols_hac(y, np.column_stack([(d.SPY - d.bill).values, dy, dy ** 2]))
    return dict(n=len(d), alpha_wk=b[0], t_alpha=t[0], beta_spy=b[1], dur_per_100bp=b[2], cvx_per_100bp2=b[3], t_spy=t[1], t_dur=t[2], t_cvx=t[3], r2=r2)


def move_bins(W, col="mreit", edges=(-1, -0.25, -0.15, -0.05, 0.05, 0.15, 0.25, 1)):
    """Average weekly return after removing the SPY beta (full-sample), by size of the 10y yield move (pp)."""
    d = W[[col, "SPY", "bill", "dy10"]].dropna()
    y = d[col] - d.bill; x = d.SPY - d.bill; b = np.polyfit(x, y, 1)[0]
    res = y - b * x
    cut = pd.cut(d.dy10 * 100, list(edges))
    return pd.DataFrame({"weeks": res.groupby(cut, observed=False).size(), "avg_resid_pct": res.groupby(cut, observed=False).mean() * 100})


def perf(r, ppy=52):
    r = r.dropna(); n = len(r); cum = (1 + r).prod()
    cagr = cum ** (ppy / n) - 1; vol = r.std() * np.sqrt(ppy)
    w = (1 + r).cumprod(); mdd = (w / w.cummax() - 1).min()
    return dict(cagr=cagr, vol=vol, maxdd=mdd, years=n / ppy)


def income_table(W, P, D, start="2008-06-01", end=None):
    rows = []
    for s in AGENCY + OTHER:
        s0 = max(pd.Timestamp(start), W[s].first_valid_index() - pd.Timedelta(days=6))
        p = P[s].loc[s0:end].dropna(); d = D[s].loc[p.index]
        yrs = (p.index[-1] - p.index[0]).days / 365.25
        trw = W[s].dropna()
        ann_div = d.rolling(252, min_periods=200).sum(); dy = (ann_div / p).dropna()
        first = d.loc[p.index[0]: p.index[0] + pd.Timedelta(days=365)].sum(); last = d.loc[p.index[-1] - pd.Timedelta(days=365):].sum()
        rows.append(dict(symbol=s, start=p.index[0].date().isoformat(), years=yrs, avg_div_yield=dy.mean(),
                         tr_cagr=perf(trw)["cagr"], price_cagr=(p.iloc[-1] / p.iloc[0]) ** (1 / yrs) - 1,
                         div_first_yr=first, div_last_yr=last, div_change=last / first - 1 if first > 0 else np.nan,
                         maxdd=perf(trw)["maxdd"]))
    return pd.DataFrame(rows).set_index("symbol")


def vol_timing(W, col="mreit", look=13, cost_bp=10, test_start="2017-01-01"):
    """Hold the basket only when trailing 13-week realised rate vol (known at the start of the week) is at or below
    its expanding median (from 2 years of history); otherwise T-bills. Rule fixed before testing; costs per switch."""
    rv = W.rvol.rolling(look).mean().shift(1)
    med = rv.expanding(104).median()
    on = (rv <= med).astype(float).where(med.notna())
    sw = on.diff().abs().fillna(0)
    strat = on * W[col] + (1 - on) * W.bill - sw * cost_bp / 1e4
    d = pd.DataFrame({"strat": strat, "bh": W[col], "bill": W.bill, "on": on}).dropna()
    out = {}
    for nm, sl in (("train", slice(None, pd.Timestamp(test_start) - pd.Timedelta(days=1))), ("test", slice(test_start, None))):
        x = d.loc[sl]
        out[nm] = dict(strat=perf(x.strat), bh=perf(x.bh), time_in=x.on.mean(),
                       ret_on=x.loc[x.on == 1, "bh"].mean() * 52, ret_off=x.loc[x.on == 0, "bh"].mean() * 52)
    return out, d
