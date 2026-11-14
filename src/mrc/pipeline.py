"""Run everything: python -m mrc.pipeline  -> reports/metrics.json + reports/figures/*.png"""
import json, sys, numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator, PercentFormatter
from .core import AGENCY, weekly, income_table, convexity_reg, move_bins, vol_timing, perf

FIG = "reports/figures/"; plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
NAVY, GOLD, GREY, RED = "#1f3b5a", "#c9a227", "#8a8f98", "#b5523b"


def main():
    W, P, D = weekly()
    m = {"sample": [W.index[0].date().isoformat(), W.index[-1].date().isoformat()], "weeks": len(W)}
    it = income_table(W, P, D); m["income"] = it.reset_index().to_dict("records")
    m["basket_full"] = perf(W.mreit)
    regs = {c: convexity_reg(W, c) for c in ["mreit"] + AGENCY + ["JNK", "T5"]}
    split = "2016-12-31"
    regs["mreit_2008_2016"] = convexity_reg(W.loc[:split], "mreit"); regs["mreit_2017_2026"] = convexity_reg(W.loc["2017-01-01":], "mreit")
    regs["T5_2008_2016"] = convexity_reg(W.loc[:split], "T5"); regs["T5_2017_2026"] = convexity_reg(W.loc["2017-01-01":], "T5")
    m["regressions"] = regs
    mb = move_bins(W); mt = move_bins(W, "T5")
    m["move_bins"] = {"labels": [str(i) for i in mb.index], "mreit": mb.avg_resid_pct.tolist(), "T5": mt.avg_resid_pct.tolist(), "weeks": mb.weeks.tolist()}
    tim, d = vol_timing(W); m["vol_timing"] = tim
    rob = {}
    for look in (8, 13, 26, 52):
        for c in (10, 25):
            o, _ = vol_timing(W, look=look, cost_bp=c); rob[f"look{look}_cost{c}"] = {"strat_cagr": o["test"]["strat"]["cagr"], "bh_cagr": o["test"]["bh"]["cagr"], "ret_on": o["test"]["ret_on"], "ret_off": o["test"]["ret_off"]}
    m["vol_timing_robustness"] = rob
    t = d.loc["2017":]; ex = t[(t.index.year != 2020)]
    m["vol_timing_test_ex2020"] = {"strat": perf(ex.strat), "bh": perf(ex.bh)}
    m["switches_test"] = int(t.on.diff().abs().sum())
    per = {}
    for s in AGENCY + ["SPY", "JNK", "T5"]:
        o, _ = vol_timing(W, col=s); per[s] = {"ret_on": o["test"]["ret_on"], "ret_off": o["test"]["ret_off"], "strat_cagr": o["test"]["strat"]["cagr"], "bh_cagr": o["test"]["bh"]["cagr"]}
    m["vol_timing_by_asset"] = per
    # residual (after full-sample SPY beta) in calm vs volatile weeks, test period
    b = regs["mreit"]["beta_spy"]; res = (W.mreit - W.bill) - b * (W.SPY - W.bill)
    rt = res.reindex(t.index)
    m["resid_on_off_test"] = {"on": rt[t.on == 1].mean() * 52, "off": rt[t.on == 0].mean() * 52}
    yr = d.groupby(d.index.year).apply(lambda x: pd.Series({"on": x.on.mean(), "bh": (1 + x.bh).prod() - 1, "strat": (1 + x.strat).prod() - 1}))
    m["by_year"] = {int(k): v for k, v in yr.T.to_dict().items()}
    json.dump(m, open("reports/metrics.json", "w"), indent=1, default=float)

    # 1 income vs return
    fig, ax = plt.subplots(figsize=(10, 5.2)); x = np.arange(len(AGENCY)); w = 0.27
    ax.bar(x - w, it.loc[AGENCY, "avg_div_yield"] * 100, w, color=GOLD, label="Average dividend yield")
    ax.bar(x, it.loc[AGENCY, "tr_cagr"] * 100, w, color=NAVY, label="Total return a year (dividends reinvested)")
    ax.bar(x + w, it.loc[AGENCY, "price_cagr"] * 100, w, color=RED, label="Share price change a year")
    ax.axhline(0, color="k", lw=0.8); ax.set_xticks(x, [f"{s}\nfrom {it.loc[s,'start'][:4]}" for s in AGENCY])
    ax.set_ylabel("% a year"); ax.set_title("The dividend is not the return: agency mortgage REITs, mid-2008 to Oct 2026")
    ax.legend(frameon=False, fontsize=9, loc="upper right"); fig.tight_layout(); fig.savefig(FIG + "income.png", dpi=160); plt.close(fig)

    # 2 dividends per share, indexed
    fig, ax = plt.subplots(figsize=(10, 5))
    for s, c in zip(["AGNC", "NLY", "TWO", "ORC", "DX", "ARR"], [NAVY, GOLD, RED, GREY, "#4a7a5c", "#7a5c8a"]):
        a = D[s].resample("YE").sum(); a = a[(a.index.year >= 2010) & (a.index.year <= 2025)]
        a = a[a > 0]
        if s == "ORC": a = a[a.index.year >= 2014]
        ax.plot(a.index.year, a / a.iloc[0] * 100, lw=2, color=c, label=s)
    ax.axhline(100, color="k", lw=0.6, ls=":"); ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.set_ylabel("Dividends paid per share in the year\n(first full year = 100, split-adjusted)"); ax.set_title("Dividends per share kept shrinking")
    ax.legend(frameon=False, ncol=3); fig.tight_layout(); fig.savefig(FIG + "dividends.png", dpi=160); plt.close(fig)

    # 3 move bins
    fig, ax = plt.subplots(figsize=(10, 5)); x = np.arange(len(mb))
    ax.bar(x - 0.2, mb.avg_resid_pct, 0.4, color=NAVY, label="Mortgage REIT basket (after removing its stock-market beta)")
    ax.bar(x + 0.2, mt.avg_resid_pct, 0.4, color=GREY, label="5-year Treasury bond")
    lab = ["Fell >25bp", "Fell 15-25", "Fell 5-15", "Within 5bp", "Rose 5-15", "Rose 15-25", "Rose >25bp"]
    ax.set_xticks(x, [f"{l}\n({n} wks)" for l, n in zip(lab, mb.weeks)], fontsize=9); ax.axhline(0, color="k", lw=0.8)
    ax.set_ylabel("Average weekly return, %"); ax.set_xlabel("Change in the 10-year Treasury yield that week")
    ax.set_title("Weekly: mortgage REITs trade like a long bond, not a short option"); ax.legend(frameon=False, fontsize=9)
    fig.tight_layout(); fig.savefig(FIG + "moves.png", dpi=160); plt.close(fig)

    # 4 regime test period
    fig, ax = plt.subplots(figsize=(10, 5)); tt = d.loc["2017":]
    ax.plot(tt.index, (1 + tt.bh).cumprod(), color=RED, lw=1.8, label=f"Hold the basket ({tim['test']['bh']['cagr']*100:.1f}% a year)")
    ax.plot(tt.index, (1 + tt.strat).cumprod(), color=NAVY, lw=2, label=f"Hold only when rates have been calm ({tim['test']['strat']['cagr']*100:.1f}% a year, after costs)")
    off = tt.on == 0; ax.fill_between(tt.index, 0, 1, where=off, transform=ax.get_xaxis_transform(), color=GOLD, alpha=0.18, label="Rate volatility above its median: in T-bills")
    ax.set_ylabel("Growth of $1"); ax.set_title("Out of sample, 2017 to Oct 2026: the return comes in calm-rate weeks")
    ax.legend(frameon=False, fontsize=9, loc="lower left"); fig.tight_layout(); fig.savefig(FIG + "regime.png", dpi=160); plt.close(fig)
    print(json.dumps({k: m[k] for k in ["sample", "weeks", "vol_timing", "resid_on_off_test", "switches_test"]}, default=float, indent=0)[:1800])


if __name__ == "__main__":
    main()
