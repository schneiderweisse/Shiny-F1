"""Figure builders for the dashboard. Every function returns a plotly Figure in the github_dark theme."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data import LABEL, ORDER, R, REF
from theme import BORDER, FG, GREEN, MUTED, MONO, PURPLE, RED, Y2025, Y2026, YEAR, YELLOW, rgba

DIVERGING = [[0.0, RED], [0.5, "#30363d"], [1.0, GREEN]]


def empty(msg="No data"):
    f = go.Figure()
    f.add_annotation(text=msg, showarrow=False, font=dict(color=MUTED, family=MONO))
    f.update_xaxes(visible=False)
    f.update_yaxes(visible=False)
    return f.update_layout(height=240)


def forest(df, label, est, lo, hi, x_title, sig=None, height=None, zero=0.0, positive_good=True):
    """Horizontal estimates with 95% CIs; green when better in 2026, red when worse, grey when the CI spans zero."""
    if df.empty:
        return empty()
    d = df.iloc[::-1]
    spans = (d[lo] <= zero) & (d[hi] >= zero)
    better = (d[est] > zero) if positive_good else (d[est] < zero)
    col = np.where(spans, MUTED, np.where(better, GREEN, RED))
    hover = [f"{l}: {e:+.3g} [{a:+.3g}, {b:+.3g}]" + (f"<br>Holm p = {p:.3g}" if sig else "")
             for l, e, a, b, p in zip(d[label], d[est], d[lo], d[hi], d[sig] if sig else [0] * len(d))]
    f = go.Figure(go.Scatter(
        x=d[est], y=d[label], mode="markers", marker=dict(color=col, size=10, line=dict(color="#0d1117", width=1)),
        error_x=dict(type="data", symmetric=False, array=d[hi] - d[est], arrayminus=d[est] - d[lo], color=BORDER, thickness=2, width=0),
        hovertext=hover, hoverinfo="text"))
    f.add_vline(x=zero, line=dict(color=MUTED, dash="dot", width=1))
    f.update_layout(height=height or 70 + 34 * len(d), showlegend=False, xaxis_title=x_title, margin=dict(l=150, r=16, t=16, b=44))
    return f


# ---------- Lap time ----------

def pace_forest():
    d = R["pace_qualifying_effects"].copy()
    if d.empty:
        return empty()
    d["label"] = d["circuit"].map(LABEL)
    d = d.set_index("circuit").loc[ORDER].reset_index()
    return forest(d, "label", "estimate", "ci_low", "ci_high", "Qualifying lap time change, 2026 vs 2025 (%)",
                  sig="p_holm", positive_good=False)


def pace_meta():
    d = R["pace_qualifying_effects"]
    if d.empty or "full_throttle_2025" not in d:
        return empty()
    x = d["full_throttle_2025"] * 100
    f = go.Figure(go.Scatter(
        x=x, y=d["estimate"], mode="markers+text", text=d["circuit"].map(LABEL), textposition="top center",
        textfont=dict(color=MUTED, size=11), marker=dict(color=Y2026, size=10),
        error_y=dict(type="data", symmetric=False, array=d["ci_high"] - d["estimate"], arrayminus=d["estimate"] - d["ci_low"],
                     color=BORDER, thickness=2, width=0),
        hovertemplate="%{text}<br>full throttle %{x:.1f}%<br>change %{y:+.2f}%<extra></extra>"))
    w = 1 / ((d["ci_high"] - d["ci_low"]) / 3.92) ** 2
    b1, b0 = np.polyfit(x, d["estimate"], 1, w=np.sqrt(w))
    xs = np.linspace(x.min() - 2, x.max() + 2, 20)
    f.add_trace(go.Scatter(x=xs, y=b0 + b1 * xs, mode="lines", line=dict(color=MUTED, dash="dash"), hoverinfo="skip"))
    f.update_layout(height=360, showlegend=False, xaxis_title="Share of the 2025 lap at full throttle (%)",
                    yaxis_title="Lap time change (%)")
    return f


# ---------- Speed trace ----------

def _straight_rects(f, circuit, rows):
    s = R["segments"]
    for r in s[(s["circuit"] == circuit) & (s["kind"] == "straight")].itertuples():
        for row in rows:
            f.add_vrect(x0=r.start_m, x1=r.end_m, fillcolor="rgba(110,118,129,0.10)", line_width=0, layer="below", row=row, col=1)


def speed_trace(circuit):
    d = R["speed_profiles"]
    d = d[d["circuit"] == circuit]
    if d.empty:
        return empty()
    f = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.48, 0.26, 0.26])
    for y, col in YEAR.items():
        f.add_trace(go.Scatter(x=d["dist_m"], y=d[f"speed_{y}"], name=f"{y} (n={int(d[f'n_{y}'].iloc[0])})",
                               line=dict(color=col, width=1.6), hovertemplate=f"{y}: %{{y:.0f}} km/h<extra></extra>"), 1, 1)
    for lo, hi, a, name in [("sim_lo", "sim_hi", 0.18, "simultaneous 95%"), ("lo", "hi", 0.32, "pointwise 95%")]:
        f.add_trace(go.Scatter(x=np.r_[d["dist_m"], d["dist_m"][::-1]], y=np.r_[d[hi], d[lo][::-1]], fill="toself",
                               fillcolor=rgba(Y2026, a), line=dict(width=0), name=name, hoverinfo="skip", showlegend=False), 2, 1)
    f.add_trace(go.Scatter(x=d["dist_m"], y=d["delta"], line=dict(color=Y2026, width=1.4), showlegend=False,
                           hovertemplate="Δ speed %{y:+.1f} km/h<extra></extra>"), 2, 1)
    f.add_trace(go.Scatter(x=np.r_[d["dist_m"], d["dist_m"][::-1]], y=np.r_[d["time_sim_hi"], d["time_sim_lo"][::-1]], fill="toself",
                           fillcolor=rgba(Y2026, 0.18), line=dict(width=0), hoverinfo="skip", showlegend=False), 3, 1)
    f.add_trace(go.Scatter(x=d["dist_m"], y=d["time_delta"], line=dict(color=Y2026, width=1.4), showlegend=False,
                           hovertemplate="cumulative Δ %{y:+.3f} s<extra></extra>"), 3, 1)
    for row in (2, 3):
        f.add_hline(y=0, line=dict(color=MUTED, width=1, dash="dot"), row=row, col=1)
    _straight_rects(f, circuit, (1, 2, 3))
    f.update_yaxes(title_text="Speed (km/h)", row=1, col=1)
    f.update_yaxes(title_text="Δ speed (km/h)", row=2, col=1)
    f.update_yaxes(title_text="Cumulative Δt (s)", row=3, col=1)
    f.update_xaxes(title_text="Distance along the lap (m) · shaded = straights", row=3, col=1)
    f.update_layout(height=640, hovermode="x unified", legend=dict(y=1.04))
    return f


def track_delta_map(circuit):
    d = R["speed_profiles"]
    d = d[d["circuit"] == circuit]
    if d.empty:
        return empty()
    lim = float(np.nanpercentile(np.abs(d["delta"]), 98)) or 1.0
    sig = (d["sim_lo"] > 0) | (d["sim_hi"] < 0)
    f = go.Figure(go.Scatter(
        x=d["x"], y=d["y"], mode="markers",
        marker=dict(color=d["delta"], colorscale=DIVERGING, cmin=-lim, cmax=lim, size=np.where(sig, 7, 4),
                    colorbar=dict(title=dict(text="Δ km/h", font=dict(color=MUTED)), tickfont=dict(color=MUTED, family=MONO), thickness=10)),
        customdata=np.c_[d["dist_m"], d["delta"]], hovertemplate="%{customdata[0]:.0f} m<br>Δ %{customdata[1]:+.1f} km/h<extra></extra>"))
    c = R["corners_xy"]
    c = c[c["circuit"] == circuit]
    f.add_trace(go.Scatter(x=c["x"], y=c["y"], mode="text", text=c["corner"], textfont=dict(color=FG, size=10, family=MONO), hoverinfo="skip"))
    f.update_xaxes(visible=False)
    f.update_yaxes(visible=False, scaleanchor="x")
    f.update_layout(height=420, showlegend=False, margin=dict(l=8, r=8, t=8, b=8))
    return f


def segment_bars(circuit):
    d = R["segment_time_delta"]
    d = d[d["circuit"] == circuit].sort_values("start_m")
    if d.empty:
        return empty()
    col = np.where(d["kind"] == "straight", PURPLE, YELLOW)
    f = go.Figure(go.Bar(
        x=d["label"], y=d["time_delta"], marker_color=col,
        error_y=dict(type="data", symmetric=False, array=d["ci_high"] - d["time_delta"], arrayminus=d["time_delta"] - d["ci_low"], color=MUTED, thickness=1.2, width=3),
        hovertemplate="%{x}<br>Δt %{y:+.3f} s<extra></extra>"))
    f.add_hline(y=0, line=dict(color=MUTED, width=1))
    f.update_layout(height=320, yaxis_title="Time 2026 − 2025 (s) · + = slower", xaxis_tickangle=-45, showlegend=False,
                    margin=dict(l=56, r=16, t=16, b=90))
    return f


# ---------- Power and energy ----------

def ers_rule_curve():
    v = np.linspace(0, 360, 361)
    p26 = np.clip(np.where(v < 340, 1800 - 5 * v, np.where(v < 345, 6900 - 20 * v, 0)), 0, 350)
    pov = np.clip(np.where(v < 355, 7100 - 20 * v, 0), 0, 350)
    f = go.Figure()
    f.add_trace(go.Scatter(x=v, y=np.full_like(v, 120), name="2025 MGU-K (120 kW, no speed limit)", line=dict(color=Y2025, width=2)))
    f.add_trace(go.Scatter(x=v, y=p26, name="2026 ERS-K (Art. C5.2.8 i)", line=dict(color=Y2026, width=2)))
    f.add_trace(go.Scatter(x=v, y=pov, name="2026 with Overtake (C5.2.8 ii)", line=dict(color=Y2026, width=1.5, dash="dot")))
    f.add_vline(x=290, line=dict(color=MUTED, dash="dot", width=1))
    f.update_layout(height=320, xaxis_title="Car speed (km/h)", yaxis_title="Max electrical power (kW)", legend=dict(y=1.18))
    return f


def accel_curve(circuit):
    d = R["accel_speed_curve"]
    d = d[d["circuit"] == circuit]
    if d.empty:
        return empty()
    f = go.Figure()
    for y, col in YEAR.items():
        s = d[d["year"] == y].sort_values("v_bin")
        f.add_trace(go.Scatter(x=np.r_[s["v_bin"], s["v_bin"][::-1]], y=np.r_[s["ci_high"], s["ci_low"][::-1]], fill="toself",
                               fillcolor=rgba(col, 0.2), line=dict(width=0), hoverinfo="skip", showlegend=False))
        f.add_trace(go.Scatter(x=s["v_bin"], y=s["acc"], name=str(y), line=dict(color=col, width=2), mode="lines+markers",
                               marker=dict(size=4), hovertemplate=f"{y}: %{{y:.2f}} m/s² at %{{x}} km/h<extra></extra>"))
    f.add_vline(x=290, line=dict(color=MUTED, dash="dot", width=1), annotation_text="290 km/h: 2026 power starts to fade",
                annotation_font=dict(color=MUTED, size=11), annotation_position="top left")
    f.add_hline(y=0, line=dict(color=MUTED, width=1))
    f.update_layout(height=380, xaxis_title="Speed (km/h)", yaxis_title="Acceleration at full throttle (m/s²)")
    return f


def accel_delta():
    d = R.get("accel_speed_delta", pd.DataFrame())
    if d.empty:
        return empty()
    spans = (d["ci_low"] <= 0) & (d["ci_high"] >= 0)
    col = np.where(spans, MUTED, np.where(d["estimate"] > 0, GREEN, RED))
    f = go.Figure(go.Scatter(
        x=d["v_bin"], y=d["estimate"], mode="markers", marker=dict(color=col, size=9),
        error_y=dict(type="data", symmetric=False, array=d["ci_high"] - d["estimate"], arrayminus=d["estimate"] - d["ci_low"], color=BORDER, thickness=2, width=0),
        customdata=d["cells"], hovertemplate="%{x} km/h: %{y:+.2f} m/s² (%{customdata} circuits)<extra></extra>"))
    f.add_hline(y=0, line=dict(color=MUTED, width=1, dash="dot"))
    f.add_vrect(x0=290, x1=355, fillcolor="rgba(240,136,62,0.08)", line_width=0, layer="below",
                annotation_text="2026 power limit falls", annotation_font=dict(color=MUTED, size=11), annotation_position="top left")
    f.update_layout(height=320, showlegend=False, xaxis_title="Speed (km/h)", yaxis_title="Acceleration gap 2026 − 2025 (m/s²)")
    return f


def clipping_regime():
    d = R.get("clipping_share_by_circuit", pd.DataFrame())
    if d.empty:
        return empty()
    reg_col = {"2025": Y2025, "2026 pre-Miami": RED, "2026 post-Miami": Y2026}
    f = make_subplots(rows=1, cols=2, subplot_titles=["Qualifying", "Race"], shared_yaxes=True, horizontal_spacing=0.04)
    for i, st in enumerate(["Qualifying", "Race"], start=1):
        s = d[d["stype"] == st]
        for reg, col in reg_col.items():
            r = s[s["reg"] == reg].set_index("circuit").reindex(ORDER)
            f.add_trace(go.Bar(x=[LABEL[c] for c in r.index], y=r["clip"] * 100, name=reg, marker_color=col, showlegend=i == 1,
                               hovertemplate=f"{reg}: %{{y:.0f}}% of straights<extra></extra>"), 1, i)
    f.update_layout(height=340, barmode="group", yaxis_title="Straights with clipping (%)", legend=dict(y=1.16))
    f.update_annotations(font=dict(color=MUTED, size=12))
    return f


def topspeed_scatter():
    d = R["straights_topspeed_delta"]
    if d.empty:
        return empty()
    f = go.Figure()
    for c in ORDER:
        s = d[d["circuit"] == c]
        f.add_trace(go.Scatter(
            x=s["v_max_2025"], y=s["delta"], mode="markers", name=LABEL[c], marker=dict(size=9),
            error_y=dict(type="data", symmetric=False, array=s["ci_high"] - s["delta"], arrayminus=s["delta"] - s["ci_low"], thickness=1.2, width=0),
            customdata=np.c_[s["label"], s["length_m"]],
            hovertemplate=LABEL[c] + " %{customdata[0]} (%{customdata[1]:.0f} m)<br>2025 %{x:.0f} km/h<br>Δ %{y:+.1f} km/h<extra></extra>"))
    f.add_hline(y=0, line=dict(color=MUTED, width=1, dash="dot"))
    f.add_vline(x=290, line=dict(color=MUTED, width=1, dash="dot"))
    f.update_layout(height=400, xaxis_title="2025 top speed on that straight (km/h)", yaxis_title="Top speed 2026 − 2025 (km/h)",
                    legend=dict(y=1.14))
    return f


def clipping_bars():
    d = R["straights_summary"]
    if d.empty:
        return empty()
    g = d.groupby(["circuit", "stype", "year"]).apply(lambda s: np.average(s["flat_decel_m"], weights=s["laps"]), include_groups=False)
    g = g.rename("m").reset_index()
    # Per-lap total: sum over the circuit's straights of the mean distance per straight
    tot = d.groupby(["circuit", "stype", "year"])["flat_decel_m"].sum().rename("per_lap").reset_index()
    f = make_subplots(rows=1, cols=2, subplot_titles=["Qualifying", "Race"], shared_yaxes=True, horizontal_spacing=0.04)
    for i, st in enumerate(["Qualifying", "Race"], start=1):
        for y, col in YEAR.items():
            s = tot[(tot["stype"] == st) & (tot["year"] == y)].set_index("circuit").reindex(ORDER)
            f.add_trace(go.Bar(x=[LABEL[c] for c in s.index], y=s["per_lap"], name=str(y), marker_color=col,
                               showlegend=i == 1, hovertemplate=f"{y}: %{{y:.0f}} m per lap<extra></extra>"), 1, i)
    f.update_layout(height=340, barmode="group", yaxis_title="Distance slowing at full throttle (m per lap)", legend=dict(y=1.16))
    f.update_annotations(font=dict(color=MUTED, size=12))
    return f


def pu_forest(metric):
    d = R["power_unit_effects"]
    d = d[d["metric"] == metric]
    if d.empty:
        return empty()
    titles = {"v_max": "Top speed vs Mercedes PU (km/h)", "flat_decel_m": "Slowing at full throttle vs Mercedes PU (m per straight)",
              "acc_last30": "Late-straight acceleration vs Mercedes PU (m/s²)"}
    f = make_subplots(rows=1, cols=2, subplot_titles=["2025", "2026"], horizontal_spacing=0.18)
    for i, y in enumerate((2025, 2026), start=1):
        s = d[d["year"] == y].sort_values("estimate")
        good = s["estimate"] > 0 if metric != "flat_decel_m" else s["estimate"] < 0
        spans = (s["ci_low"] <= 0) & (s["ci_high"] >= 0)
        col = np.where(s["pu"] == "Mercedes", MUTED, np.where(spans, MUTED, np.where(good, GREEN, RED)))
        f.add_trace(go.Scatter(x=s["estimate"], y=s["pu"], mode="markers", marker=dict(color=col, size=10),
                               error_x=dict(type="data", symmetric=False, array=s["ci_high"] - s["estimate"], arrayminus=s["estimate"] - s["ci_low"], color=BORDER, thickness=2, width=0),
                               customdata=s["teams"], hovertemplate="%{y} (%{customdata})<br>%{x:+.2f}<extra></extra>", showlegend=False), 1, i)
        f.add_vline(x=0, line=dict(color=MUTED, dash="dot", width=1), row=1, col=i)
    f.update_layout(height=300, margin=dict(l=110, r=16, t=40, b=44))
    f.update_xaxes(title_text=titles[metric], title_font=dict(size=11))
    f.update_annotations(font=dict(color=MUTED, size=12))
    return f


# ---------- Corners and lines ----------

def corner_class_forest():
    d = R["corner_effects"]
    if d.empty:
        return empty()
    f = make_subplots(rows=1, cols=2, subplot_titles=["Minimum corner speed (km/h)", "Braking deceleration (m/s²)"], horizontal_spacing=0.2)
    for i, m in enumerate(["min_speed_kmh", "braking_decel_ms2"], start=1):
        s = d[d["metric"] == m]
        spans = (s["ci_low"] <= 0) & (s["ci_high"] >= 0)
        col = np.where(spans, MUTED, np.where(s["estimate"] > 0, GREEN, RED))
        f.add_trace(go.Scatter(x=s["estimate"], y=s["speed_class"], mode="markers", marker=dict(color=col, size=11),
                               error_x=dict(type="data", symmetric=False, array=s["ci_high"] - s["estimate"], arrayminus=s["estimate"] - s["ci_low"], color=BORDER, thickness=2, width=0),
                               hovertemplate="%{y}<br>%{x:+.2f}<extra></extra>", showlegend=False), 1, i)
        f.add_vline(x=0, line=dict(color=MUTED, dash="dot", width=1), row=1, col=i)
    f.update_layout(height=260, margin=dict(l=130, r=16, t=40, b=36))
    f.update_annotations(font=dict(color=MUTED, size=12))
    return f


def corner_dumbbell(circuit):
    d = R["corners_summary"]
    d = d[d["circuit"] == circuit]
    if d.empty:
        return empty()
    w = d.pivot_table(index=["segment", "label"], columns="year", values="v_min").reset_index()
    order = R["segments"].query("circuit == @circuit").set_index("segment")["start_m"]
    w["start"] = w["segment"].map(order)
    w = w.sort_values("start", ascending=False)
    f = go.Figure()
    for a, b, lab in zip(w[2025], w[2026], w["label"]):
        f.add_trace(go.Scatter(x=[a, b], y=[lab, lab], mode="lines", line=dict(color=BORDER, width=2),
                               hoverinfo="skip", showlegend=False))
    for y, col in YEAR.items():
        f.add_trace(go.Scatter(x=w[y], y=w["label"], mode="markers", name=str(y), marker=dict(color=col, size=9),
                               hovertemplate=f"{y}: %{{x:.0f}} km/h<extra></extra>"))
    f.update_layout(height=80 + 26 * len(w), xaxis_title="Mean minimum speed, qualifying push laps (km/h)", margin=dict(l=120, r=16, t=30, b=44),
                    legend=dict(y=1.06))
    return f


def lift_coast_bars():
    d = R["lift_coast_summary"]
    if d.empty:
        return empty()
    f = make_subplots(rows=1, cols=2, subplot_titles=["Qualifying", "Race"], shared_yaxes=True, horizontal_spacing=0.04)
    for i, st in enumerate(["Qualifying", "Race"], start=1):
        for y, col in YEAR.items():
            s = d[(d["stype"] == st) & (d["year"] == y)].set_index("circuit").reindex(ORDER)
            f.add_trace(go.Bar(x=[LABEL[c] for c in s.index], y=s["mean"], name=str(y), marker_color=col, showlegend=i == 1,
                               hovertemplate=f"{y}: %{{y:.0f}} m per lap<extra></extra>"), 1, i)
    f.update_layout(height=320, barmode="group", yaxis_title="Lift-and-coast before braking (m per lap)", legend=dict(y=1.16))
    f.update_annotations(font=dict(color=MUTED, size=12))
    return f


def lines_map(circuit):
    d = R["racing_lines"]
    d = d[d["circuit"] == circuit]
    if d.empty:
        return empty()
    f = go.Figure()
    for y, col in YEAR.items():
        f.add_trace(go.Scatter(x=d[f"x_{y}"], y=d[f"y_{y}"], mode="lines", name=f"{y} mean line", line=dict(color=col, width=2)))
    c = R["corners_xy"]
    c = c[c["circuit"] == circuit]
    f.add_trace(go.Scatter(x=c["x"], y=c["y"], mode="text", text=c["corner"], textfont=dict(color=FG, size=10, family=MONO), hoverinfo="skip", showlegend=False))
    f.update_xaxes(visible=False)
    f.update_yaxes(visible=False, scaleanchor="x")
    f.update_layout(height=420, margin=dict(l=8, r=8, t=30, b=8), legend=dict(y=1.04))
    return f


def line_offsets(circuit):
    d = R["racing_line_offsets"]
    d = d[d["circuit"] == circuit]
    if d.empty:
        return empty()
    col = np.where(d["beyond_noise"], Y2026, MUTED)
    f = go.Figure()
    f.add_trace(go.Bar(x=d["label"], y=d["offset_m"], marker_color=col, name="2026 vs 2025 offset",
                       hovertemplate="%{x}<br>%{y:.1f} m<extra></extra>"))
    f.add_trace(go.Scatter(x=d["label"], y=d["noise_p95"], mode="markers", marker=dict(symbol="line-ew-open", size=18, color=FG),
                           name="noise (95th pct, split-half 2025)", hovertemplate="noise p95 %{y:.1f} m<extra></extra>"))
    f.update_layout(height=320, yaxis_title="Mean distance between lines (m)", xaxis_tickangle=-45, legend=dict(y=1.16),
                    margin=dict(l=56, r=16, t=16, b=90))
    return f


# ---------- Tyres and race ----------

def deg_dots():
    d = R["tyre_degradation"]
    if d.empty:
        return empty()
    d = d.copy()
    d["row"] = d["circuit"].map(LABEL) + " · " + d["compound"].str.title()
    cmp_order = {"SOFT": 0, "MEDIUM": 1, "HARD": 2}
    d["o1"], d["o2"] = d["circuit"].map({c: i for i, c in enumerate(ORDER)}), d["compound"].map(cmp_order)
    d = d.sort_values(["o1", "o2"], ascending=False)
    f = go.Figure()
    for y, col in YEAR.items():
        s = d[d["year"] == y]
        f.add_trace(go.Scatter(x=s["deg_s_per_lap"], y=s["row"], mode="markers", name=str(y), marker=dict(color=col, size=9),
                               error_x=dict(type="data", symmetric=False, array=s["ci_high"] - s["deg_s_per_lap"], arrayminus=s["deg_s_per_lap"] - s["ci_low"], color=rgba(col, 0.6), thickness=1.5, width=0),
                               customdata=np.c_[s["compound_c"], s["laps"], s["stints"]],
                               hovertemplate=f"{y} %{{y}} (%{{customdata[0]}})<br>%{{x:+.3f}} s/lap · %{{customdata[1]}} laps, %{{customdata[2]}} stints<extra></extra>"))
    f.add_vline(x=0, line=dict(color=MUTED, dash="dot", width=1))
    f.update_layout(height=90 + 22 * d["row"].nunique(), xaxis_title="Degradation (s per lap of tyre age, fuel-corrected)",
                    margin=dict(l=170, r=16, t=30, b=44), legend=dict(y=1.04))
    return f


def dumbbell(df, value, title, fmt=".0f"):
    if df.empty:
        return empty()
    w = df.pivot_table(index="circuit", columns="year", values=value).reindex(ORDER[::-1])
    f = go.Figure()
    for c, r in w.iterrows():
        f.add_trace(go.Scatter(x=[r.get(2025), r.get(2026)], y=[LABEL[c]] * 2, mode="lines", line=dict(color=BORDER, width=2), hoverinfo="skip", showlegend=False))
    for y, col in YEAR.items():
        f.add_trace(go.Scatter(x=w[y], y=[LABEL[c] for c in w.index], mode="markers", name=str(y), marker=dict(color=col, size=10),
                               hovertemplate=f"{y}: %{{x:{fmt}}}<extra></extra>"))
    f.update_layout(height=300, xaxis_title=title, margin=dict(l=100, r=16, t=30, b=44), legend=dict(y=1.1))
    return f


def stops_bars():
    d = R["race_stops"]
    if d.empty:
        return empty()
    g = d.groupby(["year", "stops"]).size().rename("drivers").reset_index()
    g["share"] = g["drivers"] / g.groupby("year")["drivers"].transform("sum") * 100
    f = go.Figure()
    for y, col in YEAR.items():
        s = g[g["year"] == y]
        f.add_trace(go.Bar(x=s["stops"].astype(str), y=s["share"], name=str(y), marker_color=col,
                           hovertemplate=f"{y}: %{{y:.0f}}% of finishers<extra></extra>"))
    f.update_layout(height=300, barmode="group", xaxis_title="Pit stops per finisher", yaxis_title="Share of finishers (%)", legend=dict(y=1.12))
    return f


# ---------- Regulations ----------

def timeline():
    rc = REF["rule_changes"].copy()
    cov = R["coverage"]
    races = cov[cov["session"] == "Race"][["circuit", "year", "date"]].dropna()
    f = go.Figure()
    for y, col in YEAR.items():
        s = races[races["year"] == y]
        f.add_trace(go.Scatter(x=pd.to_datetime(s["date"]), y=[str(y)] * len(s), mode="markers+text", text=s["circuit"].map(LABEL),
                               textposition="top center", textfont=dict(size=10, color=MUTED), marker=dict(color=col, size=11, symbol="circle"),
                               name=f"{y} races analysed", hovertemplate="%{text} %{x|%d %b %Y}<extra></extra>"))
    f.add_trace(go.Scatter(x=pd.to_datetime(rc["date"]), y=["rule changes"] * len(rc), mode="markers", marker=dict(color=RED, size=11, symbol="diamond"),
                           text=rc["event"] + ": " + rc["change"], name="rule changes", hovertemplate="%{x|%d %b %Y}<br>%{text}<extra></extra>"))
    f.update_layout(height=280, yaxis=dict(categoryorder="array", categoryarray=["rule changes", "2026", "2025"]), legend=dict(y=1.2),
                    margin=dict(l=100, r=16, t=40, b=36))
    return f
