"""Static figures for REPORT.md, drawn from results/. Run from regs_analyzer_25_26/:  python report/make_figures.py"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config import CIRCUITS, RESULTS  # noqa: E402

OUT = Path(__file__).resolve().parent / "figures"
OUT.mkdir(exist_ok=True)
LABEL = {k: v["label"] for k, v in CIRCUITS.items()}
ORDER = list(CIRCUITS)
C25, C26, GREY, RED, GREEN = "#0969da", "#bc4c00", "#6e7781", "#cf222e", "#1a7f37"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.color": "#d0d7de", "grid.linewidth": 0.6, "axes.edgecolor": "#8c959f", "figure.dpi": 150,
                     "savefig.bbox": "tight", "font.family": "DejaVu Sans"})


def ci_colour(lo, hi, good_positive=True):
    if lo <= 0 <= hi:
        return GREY
    return GREEN if (lo > 0) == good_positive else RED


def fig_pace():
    d = pd.read_csv(RESULTS / "pace_qualifying_effects.csv").set_index("circuit").loc[ORDER[::-1]].reset_index()
    fig, ax = plt.subplots(figsize=(6.2, 3.4))
    for i, r in d.iterrows():
        ax.errorbar(r["estimate"], i, xerr=[[r["estimate"] - r["ci_low"]], [r["ci_high"] - r["estimate"]]], fmt="o",
                    color=ci_colour(r["ci_low"], r["ci_high"], good_positive=False), capsize=0, lw=2)
    ax.set_yticks(range(len(d)), d["circuit"].map(LABEL))
    ax.axvline(0, color=GREY, ls=":", lw=1)
    ax.set_xlabel("Qualifying lap time, 2026 vs 2025 (%) · 95% CI")
    ax.set_xlim(left=0)
    fig.savefig(OUT / "fig1_pace.png")


def fig_speed(circuit="monza"):
    d = pd.read_parquet(RESULTS / "speed_profiles.parquet").query("circuit == @circuit")
    seg = pd.read_csv(RESULTS / "segments.csv").query("circuit == @circuit and kind == 'straight'")
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 4.8), sharex=True, gridspec_kw={"height_ratios": [2, 1.2]})
    for a in (a1, a2):
        for r in seg.itertuples():
            a.axvspan(r.start_m, r.end_m, color="#eaeef2", lw=0, zorder=0)
    a1.plot(d["dist_m"], d["speed_2025"], color=C25, lw=1.3, label=f"2025 (n={int(d['n_2025'].iloc[0])})")
    a1.plot(d["dist_m"], d["speed_2026"], color=C26, lw=1.3, label=f"2026 (n={int(d['n_2026'].iloc[0])})")
    a1.set_ylabel("Speed (km/h)")
    a1.legend(frameon=False, loc="lower right")
    a2.fill_between(d["dist_m"], d["sim_lo"], d["sim_hi"], color=C26, alpha=0.2, lw=0, label="simultaneous 95% band")
    a2.fill_between(d["dist_m"], d["lo"], d["hi"], color=C26, alpha=0.35, lw=0, label="pointwise 95% band")
    a2.plot(d["dist_m"], d["delta"], color=C26, lw=1.1)
    a2.axhline(0, color=GREY, ls=":", lw=1)
    a2.set_ylabel("Δ speed (km/h)")
    a2.set_xlabel(f"Distance along the lap at {LABEL[circuit]} (m) · grey = straights")
    a2.legend(frameon=False, loc="lower left", fontsize=8)
    fig.savefig(OUT / f"fig2_speed_{circuit}.png")


def fig_accel():
    d = pd.read_csv(RESULTS / "accel_speed_delta.csv")
    fig, ax = plt.subplots(figsize=(6.6, 3.2))
    ax.axvspan(290, 352, color="#fff1e5", lw=0, zorder=0)
    for r in d.itertuples():
        ax.errorbar(r.v_bin, r.estimate, yerr=[[r.estimate - r.ci_low], [r.ci_high - r.estimate]], fmt="o",
                    color=ci_colour(r.ci_low, r.ci_high), capsize=0, lw=2)
    ax.axhline(0, color=GREY, ls=":", lw=1)
    ax.text(292, ax.get_ylim()[1] * 0.9, "2026 electrical power\nlimit falls (C5.2.8)", fontsize=8, color=C26, va="top")
    ax.set_xlabel("Speed (km/h)")
    ax.set_ylabel("Acceleration gap\n2026 − 2025 (m/s²)")
    fig.savefig(OUT / "fig3_accel_gap.png")


def fig_energy():
    clip = pd.read_csv(RESULTS / "clipping_share_by_circuit.csv")
    lc = pd.read_csv(RESULTS / "lift_coast_summary.csv")
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.4))
    w = 0.38
    x = np.arange(len(ORDER))
    for ax, st in zip(axes, ["Qualifying", "Race"]):
        a = lc[(lc["stype"] == st)].pivot(index="circuit", columns="year", values="mean").reindex(ORDER)
        ax.bar(x - w / 2, a[2025], w, color=C25, label="2025")
        ax.bar(x + w / 2, a[2026], w, color=[RED if c == "australia" else C26 for c in ORDER], label="2026 (red: before Miami change)")
        ax.set_xticks(x, [LABEL[c] for c in ORDER], rotation=40, ha="right")
        ax.set_title(f"Lift-and-coast, {st.lower()}", fontsize=10)
        ax.set_ylabel("metres per lap")
    axes[0].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig4_lift_coast.png")

    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.4), sharey=True)
    for ax, st in zip(axes, ["Qualifying", "Race"]):
        s = clip[clip["stype"] == st]
        y25 = s[s["reg"] == "2025"].set_index("circuit")["clip"].reindex(ORDER) * 100
        y26 = s[s["reg"] != "2025"].set_index("circuit")["clip"].reindex(ORDER) * 100
        ax.bar(x - w / 2, y25, w, color=C25, label="2025")
        ax.bar(x + w / 2, y26, w, color=[RED if c == "australia" else C26 for c in ORDER], label="2026 (red: before Miami change)")
        ax.set_xticks(x, [LABEL[c] for c in ORDER], rotation=40, ha="right")
        ax.set_title(f"Straights with clipping, {st.lower()}", fontsize=10)
    axes[0].set_ylabel("% of straights")
    axes[0].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig5_clipping.png")


def fig_corners():
    d = pd.read_csv(RESULTS / "corner_effects.csv")
    order = ["slow (<130)", "medium (130-200)", "fast (>200)"]
    fig, axes = plt.subplots(1, 2, figsize=(9, 2.6))
    for ax, (m, title) in zip(axes, [("min_speed_kmh", "Minimum corner speed (km/h)"), ("braking_decel_ms2", "Braking deceleration (m/s²)")]):
        s = d[d["metric"] == m].set_index("speed_class").loc[order].reset_index()
        for i, r in s.iterrows():
            ax.errorbar(r["estimate"], i, xerr=[[r["estimate"] - r["ci_low"]], [r["ci_high"] - r["estimate"]]], fmt="o",
                        color=ci_colour(r["ci_low"], r["ci_high"]), capsize=0, lw=2)
        ax.set_yticks(range(3), order)
        ax.axvline(0, color=GREY, ls=":", lw=1)
        ax.set_title(f"{title}, 2026 − 2025", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "fig6_corners.png")


def fig_time_split():
    d = pd.read_csv(RESULTS / "segment_time_delta.csv").groupby(["circuit", "kind"])["time_delta"].sum().unstack().reindex(ORDER)
    fig, ax = plt.subplots(figsize=(6.6, 3.2))
    x = np.arange(len(ORDER))
    ax.bar(x - 0.2, d["corner"], 0.4, color="#9a6700", label="corner zones")
    ax.bar(x + 0.2, d["straight"], 0.4, color="#8250df", label="straights")
    ax.axhline(0, color=GREY, lw=1)
    ax.set_xticks(x, [LABEL[c] for c in ORDER], rotation=30, ha="right")
    ax.set_ylabel("Time lost in 2026 (s)\n(negative = gained)")
    ax.legend(frameon=False)
    fig.savefig(OUT / "fig7_time_split.png")


if __name__ == "__main__":
    fig_pace(); fig_speed("monza"); fig_speed("monaco"); fig_accel(); fig_energy(); fig_corners(); fig_time_split()
    print("figures written to", OUT)
