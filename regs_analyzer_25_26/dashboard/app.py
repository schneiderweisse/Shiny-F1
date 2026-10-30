"""regs_analyzer_25_26: how the 2026 F1 regulations changed the cars, on 7 circuits raced under both rule sets.

Run from regs_analyzer_25_26/:  python dashboard/app.py   then open http://127.0.0.1:8050
Reads results/ (made by pipeline/stats.py) and reference/.
"""
import numpy as np
from dash import Dash, Input, Output, dcc, html

import figures as F
import theme
from data import LABEL, ORDER, R, REF, SUMMARY

app = Dash(__name__, title="regs_analyzer_25_26", suppress_callback_exceptions=True)
server = app.server

CIRCUIT_OPTIONS = [{"label": LABEL[c], "value": c} for c in ORDER]


# ---------- small components ----------

def box(title, *children, sub=None, footer=None, flush=False):
    head = html.Div([html.Span(title, className="Box-title"), html.Span(sub, className="Box-sub") if sub else None], className="Box-header")
    body = html.Div(list(children), className="Box-body flush" if flush else "Box-body")
    return html.Div([head, body, html.Div(footer, className="Box-footer") if footer else None], className="Box")


def graph(fig):
    return dcc.Graph(figure=fig, config=theme.CONFIG)


def pill(text, kind="ns"):
    return html.Span(text, className=f"pill {kind}")


def p_pill(p):
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return pill("n/a")
    return pill(f"p = {p:.2g}" if p >= 0.001 else "p < 0.001", "sig" if p < 0.05 else "ns")


def table(df, numeric=(), fmt=None, head=None):
    fmt = fmt or {}
    cols = list(df.columns)
    th = [html.Th(head.get(c, c) if head else c) for c in cols]
    rows = []
    for r in df.itertuples(index=False):
        cells = []
        for c, v in zip(cols, r):
            if c in numeric:
                txt = "" if v is None or (isinstance(v, float) and np.isnan(v)) else format(v, fmt.get(c, ".2f"))
                cells.append(html.Td(txt, className="num"))
            else:
                cells.append(html.Td(v if isinstance(v, (html.Span, html.A)) else str(v)))
        rows.append(html.Tr(cells))
    return html.Div(html.Table([html.Thead(html.Tr(th)), html.Tbody(rows)], className="gh-table"), className="gh-table-wrap")


def finding(what, value, ci, why, direction="flat", p=None):
    return box(what, html.Div([
        html.Div(value, className=f"metric {direction}"),
        html.Div([ci, " ", p_pill(p)] if p is not None else ci, className="ci"),
        html.Div(why, className="why"),
    ], className="finding"))


def control(label, comp):
    return html.Div([html.Label(label), comp], className="gh-control")


def dropdown(id_, options, value, width=220):
    return dcc.Dropdown(id=id_, options=options, value=value, clearable=False, style={"width": width})


def get(path, default=None):
    cur = SUMMARY
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def fmt_ci(d, unit="", digits=2, signed=True):
    if not d:
        return "", ""
    f = f"{{:+.{digits}f}}" if signed else f"{{:.{digits}f}}"
    return f.format(d["estimate"]) + unit, f"95% CI [{f.format(d['ci_low'])}, {f.format(d['ci_high'])}]{unit}"


# ---------- pages ----------

def page_overview():
    pace = get(["pace", "pooled_pct"])
    accel = get(["accel_contrast_above_minus_below_290"])
    clipq = get(["clipping", "odds_ratio", "Qualifying"])
    lc_pre = get(["lift_coast_m_per_lap", "Qualifying", "pre_miami"])
    lc_post = get(["lift_coast_m_per_lap", "Qualifying", "post_miami"])
    ts = get(["topspeed"], {})
    corners = get(["corners", "min_speed_kmh"], {})
    deg = get(["tyre_deg_2026_minus_2025_s_per_lap"])
    ov = get(["racing", "overtakes_rate_ratio_negbin"]) or get(["racing", "overtakes_rate_ratio_poisson"])
    lines = get(["racing_lines"], {})

    cards = []
    if pace:
        v, ci = fmt_ci(pace, "%", 2)
        cards.append(finding("Qualifying lap time", v, ci, "Pooled over the 7 circuits; team-era random effects; track temperature adjusted.",
                             "down" if pace["estimate"] > 0 else "up", pace["p"]))
    if ts:
        cards.append(finding("Top speed on straights", f"{ts.get('mean_delta_kmh', 0):+.1f} km/h",
                             f"{ts.get('significant_holm', 0)} of {ts.get('straights_tested', 0)} straights differ (Welch, Holm)",
                             "Mean 2026 − 2025 difference in qualifying top speed over all straights.", "down"))
    if accel:
        v, ci = fmt_ci(accel, " m/s²", 2)
        cards.append(finding("Acceleration gap above vs below 290 km/h", v, ci,
                             "How much worse the 2026 − 2025 acceleration gap is at ≥ 290 km/h than below: the rule C5.2.8 power taper.",
                             "down" if accel["estimate"] < 0 else "up", accel["p"]))
    if clipq:
        v, ci = fmt_ci(clipq, "×", 1, signed=False)
        cards.append(finding("Clipping in qualifying", v, ci.replace("95% CI", "odds ratio, 95% CI"),
                             "Odds that a straight has ≥ 30 m of slowing down while flat out: the car has run out of deployable energy.",
                             "down" if clipq["estimate"] > 1 else "up", clipq["p"]))
    if lc_pre and lc_post:
        cards.append(finding("Lift-and-coast in qualifying", f"{lc_pre['estimate']:+.0f} m/lap → {lc_post['estimate']:+.0f} m/lap",
                             f"pre-Miami (Australia) 95% CI [{lc_pre['ci_low']:+.0f}, {lc_pre['ci_high']:+.0f}]; post-Miami [{lc_post['ci_low']:+.0f}, {lc_post['ci_high']:+.0f}]",
                             "Extra coasting before braking vs 2025, before and after the May 2026 energy-management change.", "flat"))
    for k in ("fast (>200)", "slow (<130)"):
        r = corners.get(k)
        if r:
            cards.append(finding(f"Minimum speed in {k.split(' ')[0]} corners", f"{r['estimate']:+.1f} km/h",
                                 f"95% CI [{r['ci_low']:+.1f}, {r['ci_high']:+.1f}] km/h",
                                 "Driver-level means, corner fixed effects, SEs clustered by team-era; qualifying push laps.",
                                 "up" if r["estimate"] > 0 else "down", r["p"]))
    if deg:
        v, ci = fmt_ci(deg, " s/lap", 3)
        cards.append(finding("Tyre degradation", v, ci, "Weighted meta-analysis of per-stint degradation slopes, compound and circuit adjusted.",
                             "down" if deg["estimate"] > 0 else "up", deg["p"]))
    if ov:
        v, ci = fmt_ci(ov, "×", 2, signed=False)
        cards.append(finding("Overtakes per race", v, ci.replace("95% CI", "rate ratio, 95% CI"),
                             "Negative binomial with circuit fixed effects (Poisson is overdispersed); 7 races per season.",
                             "up" if ov["estimate"] > 1 else "down", ov["p"]))
    if lines:
        cards.append(finding("Racing lines", f"{lines['beyond_noise']} of {lines['corner_zones']} corners",
                             f"median offset {lines['median_offset_m']:.1f} m",
                             "Corner zones where the 2026 mean line differs from 2025 by more than the split-half noise of the 2025 laps.", "flat"))

    circuits = []
    for c in ORDER:
        reg = "2026 original" if c == "australia" else "2026 post-Miami"
        cov = R["coverage"]
        s25 = ", ".join(cov[(cov.circuit == c) & (cov.year == 2025)]["session"].str.replace("Practice ", "FP"))
        s26 = ", ".join(cov[(cov.circuit == c) & (cov.year == 2026)]["session"].str.replace("Practice ", "FP"))
        comp = REF["compounds"].set_index(["year", "circuit"])
        c25 = "–".join(comp.loc[(2025, c), ["hard", "medium", "soft"]][::-1]) if (2025, c) in comp.index else ""
        c26 = "–".join(comp.loc[(2026, c), ["hard", "medium", "soft"]][::-1]) if (2026, c) in comp.index else ""
        circuits.append({"Circuit": LABEL[c], "2026 rules": pill(reg, "warn" if c == "australia" else "ns"),
                         "Sessions 2025": s25, "Sessions 2026": s26, "Tyres 2025": c25, "Tyres 2026": c26})
    import pandas as pd
    return html.Div([
        html.Div([
            html.P(["This analysis compares the 2025 cars with the 2026 cars on the seven circuits raced under both rule sets: ",
                    "Australia, Monaco, Barcelona, Hungary, Monza, Singapore and Austin. ",
                    "Data are TracingInsights telemetry (practice, qualifying and race), OpenF1 timing, Pirelli tyre choices and the FIA rulebooks. ",
                    "Green means better in 2026, red worse, grey not distinguishable from no change."], className="gh-desc"),
        ]),
        html.Div(cards, className="gh-grid-3"),
        box("Circuits", table(pd.DataFrame(circuits)), sub="Australia 2026 ran before the Miami energy-management change",
            footer="Sprint weekends only have FP1: Austin 2025 and Singapore 2026."),
    ], className="gh-main")


def page_pace():
    d = R["pace_qualifying_desc"]
    w = d.pivot_table(index="circuit", columns="year", values=["pole", "top10"]).reindex(ORDER)
    import pandas as pd
    t = pd.DataFrame({"Circuit": [LABEL[c] for c in w.index],
                      "Pole 2025 (s)": w[("pole", 2025)].values, "Pole 2026 (s)": w[("pole", 2026)].values,
                      "Δ pole (s)": (w[("pole", 2026)] - w[("pole", 2025)]).values,
                      "Top-10 mean 2025 (s)": w[("top10", 2025)].values, "Top-10 mean 2026 (s)": w[("top10", 2026)].values})
    het = get(["pace", "lr_heterogeneity"], {})
    meta = get(["pace", "meta_slope_per_pct_full_throttle"], {})
    return html.Div([
        html.Div([
            box("Qualifying lap time change by circuit", graph(F.pace_forest()), sub="LMM on log lap time · 95% CI · Holm p in hover",
                footer=f"Circuit heterogeneity: LR χ²({het.get('df', '')}) = {het.get('chi2', float('nan')):.1f}, p = {het.get('p', float('nan')):.2g}. "
                       "Model: log(lap time) ~ circuit + circuit:2026 + track temperature + (1 | team × year)."),
            box("Is the change bigger on power circuits?", graph(F.pace_meta()), sub="weighted meta-regression",
                footer=f"Slope: {meta.get('estimate', float('nan')):+.3f} percentage points of lap time per extra % of full throttle, "
                       f"p = {meta.get('p', float('nan')):.2g} (n = 7 circuits)."),
        ], className="gh-grid-2"),
        box("Pole and top-10 times", table(t, numeric=[c for c in t.columns if c != "Circuit"], fmt={c: ".3f" for c in t.columns}),
            sub="best qualifying lap per driver"),
    ], className="gh-main")


def page_speed():
    return html.Div([
        html.Div([control("Circuit", dropdown("speed-circuit", CIRCUIT_OPTIONS, "monza"))], className="gh-controls"),
        box("Speed along the lap", dcc.Graph(id="speed-trace", config=theme.CONFIG),
            sub="mean of each driver's best qualifying lap",
            footer="Middle: 2026 − 2025 speed with pointwise (darker) and simultaneous (lighter) 95% bands from a driver bootstrap "
                   "(B = 2000, max-|t| calibration). Where the lighter band excludes 0, the difference holds for the lap as a whole. "
                   "Bottom: cumulative time gap; its last value is the lap time difference."),
        html.Div([
            box("Where 2026 is faster (green) or slower (red)", dcc.Graph(id="speed-map", config=theme.CONFIG),
                sub="bigger dots: simultaneous band excludes 0"),
            box("Time gained or lost per segment", dcc.Graph(id="speed-segments", config=theme.CONFIG),
                sub="purple straights · yellow corners · 95% bootstrap CI"),
        ], className="gh-grid-2"),
    ], className="gh-main")


def page_power():
    accel = get(["accel_contrast_above_minus_below_290"], {})
    clip = get(["clipping"], {})
    reg = get(["clipping_odds_ratio_by_regime"], {})
    rows = []
    for part, key in [("Odds of clipping", "odds_ratio"), ("Distance when it happens", "amount_ratio")]:
        for st in ("Qualifying", "Race"):
            r = clip.get(key, {}).get(st)
            if r:
                rows.append({"Model part": part, "Session": st, "2026 / 2025": r["estimate"], "CI low": r["ci_low"], "CI high": r["ci_high"],
                             "p": p_pill(r["p"])})
    import pandas as pd
    return html.Div([
        html.Div([
            box("The rule: electrical power vs speed", graph(F.ers_rule_curve()), sub="FIA 2026 Section C, Art. C5.2.8",
                footer="In 2026 the 350 kW electric motor gives full power only up to 290 km/h; above it the limit falls by 5 kW per km/h."),
            box("Acceleration at full throttle vs speed", control("Circuit", dropdown("accel-circuit", [{"label": "All circuits", "value": "all"}] + CIRCUIT_OPTIONS, "all")),
                dcc.Graph(id="accel-curve", config=theme.CONFIG), sub="qualifying push laps · lap-bootstrap 95% CI",
                footer="Raw curves mix circuits; the gap chart below compares like with like."),
        ], className="gh-grid-2"),
        box("Acceleration gap by speed, within circuit", graph(F.accel_delta()),
            sub="lap × 10 km/h bin means · circuit × bin fixed effects · driver-clustered 95% CI",
            footer=f"Pre-specified contrast (mean gap ≥ 290 km/h − mean gap < 290 km/h): {accel.get('estimate', float('nan')):+.2f} m/s² "
                   f"[{accel.get('ci_low', float('nan')):+.2f}, {accel.get('ci_high', float('nan')):+.2f}], p = {accel.get('p', float('nan')):.2g}. "
                   "Below ~260 km/h the lighter 2026 car with 350 kW of electric torque accelerates harder; above 290 km/h it falls behind."),
        html.Div([
            box("Top speed per straight", graph(F.topspeed_scatter()), sub="qualifying push laps · Welch 95% CI",
                footer="If the 290 km/h taper bites, the loss should grow with the 2025 top speed (points sloping down to the right)."),
            box("Slowing down while flat out", graph(F.clipping_bars()), sub="energy-limit signature",
                footer="Distance per lap where speed falls with the throttle at ≥ 98%: the car has run out of deployable energy (clipping)."),
        ], className="gh-grid-2"),
        html.Div([
            box("Hurdle model for clipping", table(pd.DataFrame(rows), numeric=["2026 / 2025", "CI low", "CI high"]),
                sub="logistic GEE for occurrence + gamma GEE for distance · driver-era clusters · circuit and straight length adjusted"),
            box("Clipping before and after the Miami change", graph(F.clipping_regime()), sub="share of straights with ≥ 30 m of slowing while flat out",
                footer="Odds ratio vs 2025 in the race: pre-Miami (Australia) "
                       f"{reg.get('Race', {}).get('pre_miami', {}).get('estimate', float('nan')):.1f}×, post-Miami "
                       f"{reg.get('Race', {}).get('post_miami', {}).get('estimate', float('nan')):.1f}×; in qualifying both ≈ "
                       f"{reg.get('Qualifying', {}).get('post_miami', {}).get('estimate', float('nan')):.0f}×. Australia is the only pre-Miami circuit, "
                       "so the regime and the circuit cannot be separated."),
        ], className="gh-grid-2"),
        box("Power units", control("Metric", dropdown("pu-metric", [{"label": "Top speed", "value": "v_max"},
                                                                   {"label": "Slowing at full throttle", "value": "flat_decel_m"},
                                                                   {"label": "Late-straight acceleration", "value": "acc_last30"}], "v_max")),
            dcc.Graph(id="pu-forest", config=theme.CONFIG), sub="vs Mercedes-powered cars · straight fixed effects · driver-clustered SEs",
            footer="Honda (Aston Martin) and Audi power one team each in 2026, so their engine and car cannot be separated."),
    ], className="gh-main")


def lift_coast_note():
    lc = get(["lift_coast_m_per_lap"], {})
    parts = []
    for st in ("Qualifying", "Race"):
        r = lc.get(st)
        if r:
            parts.append(f"{st}: {r['pre_miami']['estimate']:+.0f} m/lap before the Miami change (Australia), "
                         f"{r['post_miami']['estimate']:+.0f} m/lap after (difference-in-differences p = {r['pre_minus_post']['p']:.2g})")
    return ("Extra coasting vs 2025. " + "; ".join(parts) + ". Driver-level means, circuit × session fixed effects, team-era clustered SEs.")


def page_corners():
    return html.Div([
        box("Corners by speed class", graph(F.corner_class_forest()),
            sub="2026 − 2025 · driver-level means · corner fixed effects · team-era clustered 95% CI · qualifying push laps",
            footer="Classes use the 2025 median minimum speed: slow < 130, medium 130–200, fast > 200 km/h. "
                   "Braking deceleration = (v_brake² − v_min²) / (2 × braking distance)."),
        box("Lift-and-coast", graph(F.lift_coast_bars()), sub="distance coasting (throttle < 10%, no brake) before braking zones",
            footer=lift_coast_note()),
        html.Div([control("Circuit", dropdown("corner-circuit", CIRCUIT_OPTIONS, "monaco"))], className="gh-controls"),
        html.Div([
            box("Minimum speed per corner", dcc.Graph(id="corner-dumbbell", config=theme.CONFIG), sub="qualifying push laps"),
            box("Racing lines", dcc.Graph(id="lines-map", config=theme.CONFIG), sub="mean x/y of qualifying push laps"),
        ], className="gh-grid-2"),
        box("How far apart are the lines?", dcc.Graph(id="lines-offsets", config=theme.CONFIG),
            sub="orange: offset larger than the 95th percentile of the split-half noise of the 2025 laps",
            footer="Position data are interpolated GPS, so offsets of a metre or two are within measurement noise."),
    ], className="gh-main")


def page_tyres():
    comp = REF["compounds"].pivot(index="circuit", columns="year", values=["soft", "medium", "hard"]).reindex(ORDER)
    import pandas as pd
    ct = pd.DataFrame({"Circuit": [LABEL[c] for c in comp.index],
                       "2025 (S / M / H)": [" / ".join(comp.loc[c, (k, 2025)] for k in ("soft", "medium", "hard")) for c in comp.index],
                       "2026 (S / M / H)": [" / ".join(comp.loc[c, (k, 2026)] for k in ("soft", "medium", "hard")) for c in comp.index]})
    rac = get(["racing"], {})
    stops = get(["stops_rate_ratio"], {})
    rs = R["racing_summary"]
    return html.Div([
        html.Div([
            box("Pirelli compound choices", table(ct), sub="softest to hardest", footer="C6 existed in 2025 only. Sources in reference/compounds.csv."),
            box("Pit stops", graph(F.stops_bars()), sub="finishers (≥ 90% of race distance)",
                footer=f"Poisson rate ratio 2026 / 2025 = {stops.get('estimate', float('nan')):.2f} "
                       f"[{stops.get('ci_low', float('nan')):.2f}, {stops.get('ci_high', float('nan')):.2f}], p = {stops.get('p', float('nan')):.2g}."),
        ], className="gh-grid-2"),
        box("Tyre degradation per compound", graph(F.deg_dots()), sub="race laps · LMM per circuit-year: lap time ~ compound × tyre age + lap + (1 | driver)",
            footer="The lap term absorbs fuel burn. Slopes are seconds lost per lap of tyre age."),
        html.Div([
            box("Overtakes per race", graph(F.dumbbell(rs, "overtakes", "Overtakes (OpenF1)")), sub="race session",
                footer=f"Paired Wilcoxon over circuits p = {rac.get('overtakes_wilcoxon_p', float('nan')):.2g}; "
                       f"Pearson dispersion {rac.get('overtakes_dispersion', float('nan')):.1f}."),
            box("Field spread in race pace", graph(F.dumbbell(rs, "spread_sd", "SD of drivers' gap to the fastest median lap (%)", ".2f")),
                sub="smaller = closer field",
                footer=f"Mean change {rac.get('spread_sd_change_pct_points', float('nan')):+.2f} points; paired Wilcoxon p = {rac.get('spread_wilcoxon_p', float('nan')):.2g}."),
        ], className="gh-grid-2"),
    ], className="gh-main")


def page_regs():
    r = REF["regulations"]
    t = r.rename(columns={"area": "Area", "parameter": "Parameter", "value_2025": "2025", "value_2026": "2026",
                          "ref_2025": "Article 2025", "ref_2026": "Article 2026", "expected_effect": "Expected effect"})
    rc = REF["rule_changes"].rename(columns={"date": "Date", "event": "Event", "change": "Change"})
    rc["Source"] = [html.A("link", href=u, target="_blank") for u in rc["source"]]
    return html.Div([
        box("2025 vs 2026 technical rules", table(t), sub="FIA Technical Regulations 2025 (issue 3) and 2026 Section C (issue 21)",
            footer="Values are quoted from the FIA PDFs, except tyre sizes and the 2025 per-lap energy flows (energy-flow diagram)."),
        box("Timeline", graph(F.timeline()), sub="races analysed and rule changes"),
        box("Rule changes during the 2026 season", table(rc[["Date", "Event", "Change", "Source"]])),
    ], className="gh-main")


def page_data():
    import pandas as pd
    cov = R["coverage"].copy()
    cov["circuit"] = cov["circuit"].map(LABEL)
    cov = cov.rename(columns={"circuit": "Circuit", "year": "Year", "session": "Session", "laps": "Laps", "clean": "Clean",
                              "push": "Push", "race_pace": "Race pace", "with_telemetry": "With telemetry", "telemetry_ok": "Telemetry OK",
                              "drivers": "Drivers", "date": "Date"})
    cov["Year"] = cov["Year"].astype(str)
    num = ["Laps", "Clean", "Push", "Race pace", "With telemetry", "Telemetry OK", "Drivers"]
    methods = dcc.Markdown("""
**Lap filters.** *Clean*: timed, dry tyres, not deleted, not an in- or out-lap, no safety car, virtual safety car or red flag, and for races not lap 1.
*Push*: a clean practice or qualifying lap within 102% of that driver's best of the session. *Race pace*: a clean race lap within 107% of the driver's median.

**Telemetry.** Each lap is resampled to a 10 m grid along the official lap length (raw data ≈ 3.7 Hz, one sample every ~22 m at 300 km/h).
Laps whose trace is misaligned or broken are dropped by a quality check (circular cross-correlation with the median qualifying lap).
Straights are runs where the average of the 2025 and 2026 median qualifying throttle is ≥ 90% for ≥ 200 m; the rest are corner zones, labelled by matching
the official corner positions to the mean driving line.

**Models.** Linear mixed models (statsmodels MixedLM, REML) with a random intercept for team × year, so a team's competitiveness in each era does not leak into the rule effect.
Repeated laps by the same driver are handled with driver × year random intercepts or GEE/cluster-robust errors. Per-circuit tests are Holm-corrected.
Functional comparisons use a driver bootstrap (B = 2000) with max-|t| simultaneous bands. With 7 circuits, circuit-level regressions have little power: read their slopes as descriptive.

**Caveats.** 2026 Australia ran before the May energy-management change; teams developed their cars through each season; Honda and Audi power one team each;
OpenF1 overtakes are derived from timing data. Full model output is in `results/models/`, and the write-up is `REPORT.md`.
""", className="gh-markdown")
    return html.Div([
        box("Methods", methods),
        box("Data coverage", table(cov, numeric=num, fmt={c: ".0f" for c in num}),
            footer="Telemetry OK: laps whose speed trace aligns with the circuit's reference lap (FFT cross-correlation) and whose "
                   "telemetry duration matches the official lap time. The 2026 Hungarian GP race telemetry is mis-sliced and mostly excluded."),
    ], className="gh-main")


PAGES = {"overview": ("Overview", page_overview), "pace": ("Lap time", page_pace), "speed": ("Speed trace", page_speed),
         "power": ("Power & energy", page_power), "corners": ("Corners & lines", page_corners), "tyres": ("Tyres & race", page_tyres),
         "regs": ("Regulations", page_regs), "data": ("Data & methods", page_data)}

app.layout = html.Div([
    html.Header(html.Div([
        html.Div([html.Span("Shiny-F1", className="owner"), html.Span("/", className="sep"), html.Span("regs_analyzer_25_26", className="name"),
                  html.Span("2025 vs 2026", className="gh-label")], className="gh-repo"),
        html.P("How the 2026 Formula 1 rules (new power units, active aero, lighter cars, narrower tyres) changed lap time, speed, "
               "energy use, corners, tyres and racing on seven circuits raced under both rule sets.", className="gh-desc"),
        dcc.Tabs(id="tabs", value="overview", className="gh-tabs", children=[
            dcc.Tab(label=lab, value=k, className="gh-tab", selected_className="gh-tab--selected") for k, (lab, _) in PAGES.items()]),
    ], className="gh-header-inner"), className="gh-header"),
    html.Div(id="page"),
    html.Footer(["Data: TracingInsights, OpenF1, Jolpica, Pirelli, FIA. Unofficial analysis, not associated with Formula 1 or the FIA."], className="gh-footer"),
])


@app.callback(Output("page", "children"), Input("tabs", "value"))
def render(tab):
    return PAGES[tab][1]()


# Charts that follow a dropdown: dropdown id -> (graph ids, function returning one figure per graph).
# The callbacks below and the static GitHub Pages export (export_static.py) both read this table.
DYNAMIC = {
    "speed-circuit": (["speed-trace", "speed-map", "speed-segments"],
                      lambda c: [F.speed_trace(c), F.track_delta_map(c), F.segment_bars(c)]),
    "accel-circuit": (["accel-curve"], lambda c: [F.accel_curve(c)]),
    "pu-metric": (["pu-forest"], lambda m: [F.pu_forest(m)]),
    "corner-circuit": (["corner-dumbbell", "lines-map", "lines-offsets"],
                       lambda c: [F.corner_dumbbell(c), F.lines_map(c), F.line_offsets(c)]),
}

for _dropdown, (_graphs, _build) in DYNAMIC.items():
    app.callback([Output(g, "figure") for g in _graphs], Input(_dropdown, "value"))(_build)


if __name__ == "__main__":
    import os
    app.run(debug=False, port=int(os.environ.get("PORT", 8050)))
