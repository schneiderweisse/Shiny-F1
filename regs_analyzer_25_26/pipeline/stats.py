"""Step 3: baseline statistics, 2025 rules vs 2026 rules, on the 7 matched circuits.

Every analysis writes tidy tables to results/ (read by the dashboard) and full model output to
results/models/ (used in the write-up). Conventions:
  y26        indicator for the 2026 rules
  team_era   team lineage x year: random intercept for the competitive order of each era
  driver_era driver x year: cluster for repeated laps of the same driver
  Holm correction within each family of per-circuit tests.

Run from regs_analyzer_25_26/:  python -m pipeline.stats
"""
import json
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.stats.multitest import multipletests

from config import CIRCUITS, GRID_STEP_M, INTERIM, PROCESSED, RAW, REFERENCE, RESULTS, YEARS

warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", message=".*(converge|singular|boundary|Hessian).*")

RNG = np.random.default_rng(2026)
B = 2000
MODELS = RESULTS / "models"
KEYS = ["year", "circuit", "session", "driver", "lap"]
SUMMARY: dict = {}


# ---------- helpers ----------

def save(df: pd.DataFrame, name: str) -> None:
    df.to_csv(RESULTS / f"{name}.csv", index=False)


def report(name: str, text: str) -> None:
    (MODELS / f"{name}.txt").write_text(text, encoding="utf-8")


def holm(p) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    out = np.full(p.shape, np.nan)
    ok = ~np.isnan(p)
    if ok.any():
        out[ok] = multipletests(p[ok], method="holm")[1]
    return out


def term_row(fit, term: str, scale=None) -> dict:
    est, se = fit.params[term], fit.bse[term]
    lo, hi = est - 1.96 * se, est + 1.96 * se
    p = fit.pvalues[term]
    if scale == "pct":   # log-scale coefficient -> % change
        est, lo, hi = (np.exp([est, lo, hi]) - 1) * 100
    elif scale == "ratio":
        est, lo, hi = np.exp([est, lo, hi])
    return {"estimate": est, "ci_low": lo, "ci_high": hi, "se": se, "p": p}


def mixed(formula: str, data: pd.DataFrame, groups: str, reml=True):
    return smf.mixedlm(formula, data, groups=data[groups]).fit(reml=reml, method=["lbfgs", "powell"])


def load():
    laps = pd.read_parquet(PROCESSED / "laps.parquet")
    laps = laps[laps["lineage"].notna()].copy()
    laps["y26"] = (laps["year"] == 2026).astype(int)
    laps["team_era"] = laps["lineage"].astype(str) + " " + laps["year"].astype(str)
    laps["driver_era"] = laps["driver"].astype(str) + " " + laps["year"].astype(str)
    meta = laps[KEYS + ["stype", "push", "race_pace", "best_of_session", "team", "lineage", "pu", "team_era",
                        "driver_era", "y26", "compound", "compound_c", "tyre_life", "stint", "track_temp",
                        "lap_time", "regime"]]
    # Telemetry features only from laps that passed the alignment/quality check (features.quality_check)
    fs = pd.read_parquet(PROCESSED / "feat_straights.parquet").query("tel_ok").merge(meta, on=KEYS + ["stype"])
    fc = pd.read_parquet(PROCESSED / "feat_corners.parquet").query("tel_ok").merge(meta, on=KEYS + ["stype"])
    fl = pd.read_parquet(PROCESSED / "feat_laps.parquet").query("tel_ok").merge(meta, on=KEYS + ["stype"])
    segs = pd.read_parquet(PROCESSED / "segments.parquet")
    return laps, fs, fc, fl, segs


def grid_rows(year: int, circuit: str, laps: pd.DataFrame, flag: str):
    """Telemetry matrices on the distance grid for laps with the given flag."""
    z = np.load(INTERIM / f"grid_{year}_{circuit}.npz")
    idx = pd.read_parquet(INTERIM / f"grid_index_{year}_{circuit}.parquet").reset_index()
    sel = idx[idx["tel_ok"]].merge(laps.loc[laps[flag], KEYS + ["driver_era"]], on=KEYS)
    rows = sel["index"].to_numpy()
    return {k: z[k][rows] for k in ("speed", "throttle", "brake", "time", "x", "y", "gear")}, sel, z["grid"]


# ---------- 0. coverage ----------

def coverage(laps):
    cov = (laps.groupby(["circuit", "year", "session"])
               .agg(laps=("lap", "size"), clean=("clean", "sum"), push=("push", "sum"),
                    race_pace=("race_pace", "sum"), with_telemetry=("has_tel", "sum"),
                    drivers=("driver", "nunique"), date=("date", "first"))
               .reset_index())
    # Laps whose telemetry passed the quality check
    ok = pd.concat([pd.read_parquet(INTERIM / f"grid_index_{y}_{c}.parquet") for y in YEARS for c in CIRCUITS])
    ok = ok[ok["tel_ok"]].groupby(["circuit", "year", "session"]).size().rename("telemetry_ok")
    cov = cov.join(ok, on=["circuit", "year", "session"]).fillna({"telemetry_ok": 0})
    save(cov, "coverage")
    SUMMARY["laps_total"] = int(len(laps))
    SUMMARY["laps_clean"] = int(laps["clean"].sum())


# ---------- 1. one-lap pace ----------

def one_lap_pace(laps, fl):
    q = laps[(laps["session"] == "Qualifying") & laps["best_of_session"]].copy()
    q["log_t"] = np.log(q["lap_time"])
    q["temp_c"] = q["track_temp"] - q["track_temp"].mean()
    desc = (q.groupby(["circuit", "year"])["lap_time"]
              .agg(n="size", pole="min", median="median", top10=lambda s: s.nsmallest(10).mean())
              .reset_index())

    # Circuit-specific era effects with team-era random intercepts
    m = mixed("log_t ~ 0 + C(circuit) + C(circuit):y26 + temp_c", q, "team_era")
    report("pace_qualifying_lmm", str(m.summary()))
    rows = []
    for c in CIRCUITS:
        r = term_row(m, f"C(circuit)[{c}]:y26", "pct")
        rows.append({"circuit": c, **r})
    eff = pd.DataFrame(rows)
    eff["p_holm"] = holm(eff["p"])

    # Common effect vs circuit-specific effects (likelihood ratio, ML fits)
    full = mixed("log_t ~ 0 + C(circuit) + C(circuit):y26 + temp_c", q, "team_era", reml=False)
    common = mixed("log_t ~ 0 + C(circuit) + y26 + temp_c", q, "team_era", reml=False)
    lr = 2 * (full.llf - common.llf)
    df = len(CIRCUITS) - 1
    pooled = term_row(mixed("log_t ~ 0 + C(circuit) + y26 + temp_c", q, "team_era"), "y26", "pct")

    # Meta-regression: is the 2026 penalty bigger on power circuits?
    ft = (fl[(fl["year"] == 2025) & (fl["session"] == "Qualifying") & fl["push"]]
            .groupby("circuit")["full_throttle_frac"].mean().rename("full_throttle_2025"))
    eff = eff.merge(ft, on="circuit", how="left")
    log_eff = np.log1p(eff["estimate"] / 100)
    se_log = (np.log1p(eff["ci_high"] / 100) - np.log1p(eff["ci_low"] / 100)) / (2 * 1.96)
    meta = sm.WLS(log_eff, sm.add_constant(eff["full_throttle_2025"] * 100), weights=1 / se_log**2).fit()
    report("pace_meta_regression", str(meta.summary()))

    save(desc, "pace_qualifying_desc")
    save(eff, "pace_qualifying_effects")
    SUMMARY["pace"] = {"pooled_pct": pooled, "lr_heterogeneity": {"chi2": lr, "df": df, "p": stats.chi2.sf(lr, df)},
                       "meta_slope_per_pct_full_throttle": {"estimate": float(meta.params.iloc[1] * 100),
                                                            "p": float(meta.pvalues.iloc[1])}}


# ---------- 2. speed and time along the lap (functional comparison) ----------

def boot_means(mat: np.ndarray, b: int) -> np.ndarray:
    n = mat.shape[0]
    idx = RNG.integers(0, n, size=(b, n))
    return np.nanmean(mat[idx], axis=1)


def simultaneous_band(est, boots):
    se = np.nanstd(boots, axis=0, ddof=1)
    se[se == 0] = np.nan
    tmax = np.nanmax(np.abs(boots - est) / se, axis=1)
    crit = np.nanquantile(tmax, 0.95)
    return est - 1.96 * se, est + 1.96 * se, est - crit * se, est + crit * se, crit


def speed_profiles(laps, segs):
    out, seg_delta = [], []
    for c in CIRCUITS:
        cur = {}
        for y in YEARS:
            g, sel, grid = grid_rows(y, c, laps[laps["session"] == "Qualifying"], "best_of_session")
            cur[y] = g
        v25, v26 = cur[2025]["speed"], cur[2026]["speed"]
        t25 = cur[2025]["time"] - cur[2025]["time"][:, :1]
        t26 = cur[2026]["time"] - cur[2026]["time"][:, :1]
        dv = np.nanmean(v26, 0) - np.nanmean(v25, 0)
        dvb = boot_means(v26, B) - boot_means(v25, B)
        lo, hi, slo, shi, crit = simultaneous_band(dv, dvb)
        dt = np.nanmean(t26, 0) - np.nanmean(t25, 0)
        dtb = boot_means(t26, B) - boot_means(t25, B)
        tlo, thi, tslo, tshi, _ = simultaneous_band(dt, dtb)
        out.append(pd.DataFrame({
            "circuit": c, "dist_m": grid, "speed_2025": np.nanmean(v25, 0), "speed_2026": np.nanmean(v26, 0),
            "delta": dv, "lo": lo, "hi": hi, "sim_lo": slo, "sim_hi": shi,
            "throttle_2025": np.nanmean(cur[2025]["throttle"], 0), "throttle_2026": np.nanmean(cur[2026]["throttle"], 0),
            "time_delta": dt, "time_lo": tlo, "time_hi": thi, "time_sim_lo": tslo, "time_sim_hi": tshi,
            "x": np.nanmean(np.r_[cur[2025]["x"], cur[2026]["x"]], 0), "y": np.nanmean(np.r_[cur[2025]["y"], cur[2026]["y"]], 0),
            "n_2025": v25.shape[0], "n_2026": v26.shape[0], "crit": crit}))
        # Time gained/lost per segment: increment of the cumulative gap across the segment
        for s in segs[segs["circuit"] == c].itertuples():
            a, b = s.i0, min(s.i1, dt.size) - 1
            inc = dt[b] - (dt[a - 1] if a > 0 else 0.0)
            incb = dtb[:, b] - (dtb[:, a - 1] if a > 0 else 0.0)
            seg_delta.append({"circuit": c, "segment": s.segment, "label": s.label, "kind": s.kind,
                              "start_m": s.start_m, "end_m": s.end_m, "time_delta": inc,
                              "ci_low": np.nanquantile(incb, 0.025), "ci_high": np.nanquantile(incb, 0.975)})
    prof = pd.concat(out, ignore_index=True)
    prof.to_parquet(RESULTS / "speed_profiles.parquet", index=False)
    sd = pd.DataFrame(seg_delta)
    save(sd, "segment_time_delta")
    share = sd.groupby(["circuit", "kind"])["time_delta"].sum().unstack()
    SUMMARY["time_by_segment_kind"] = share.round(3).to_dict(orient="index")


# ---------- 3. acceleration vs speed (Art. C5.2.8 power taper) ----------

def accel_speed(laps):
    rows = []
    for c in CIRCUITS:
        for y in YEARS:
            g, sel, grid = grid_rows(y, c, laps[laps["stype"].isin(["Q"])], "push")
            v = g["speed"]
            k = 5  # 50 m moving average before differentiating: 3.7 Hz data is noisy
            ker = np.ones(k) / k
            vs = np.apply_along_axis(lambda r: np.convolve(r, ker, mode="same"), 1, v)
            vms = vs / 3.6
            acc = vms * np.gradient(vms, GRID_STEP_M, axis=1)
            ok = (g["throttle"] >= 98) & (g["brake"] < 0.1) & (g["gear"] >= 5) & (vs > 150)
            ok[:, :k] = ok[:, -k:] = False
            r, col = np.nonzero(ok)
            rows.append(pd.DataFrame({"circuit": c, "year": y, "v": vs[r, col], "acc": acc[r, col],
                                      "driver_era": sel["driver_era"].to_numpy()[r], "lap_id": f"{y}{c}" + pd.Series(r).astype(str)}))
    d = pd.concat(rows, ignore_index=True)
    d = d[(d["acc"] > -6) & (d["acc"] < 20)]
    d["y26"] = (d["year"] == 2026).astype(int)
    d["v_bin"] = (d["v"] // 10 * 10 + 5).astype(int)

    # 2026 - 2025 gap in each 10 km/h bin, compared within the same circuit and speed:
    # lap x bin means, circuit x bin fixed effects, driver-clustered SEs.
    lb = (d.groupby(["lap_id", "circuit", "year", "y26", "driver_era", "v_bin"])["acc"].mean().reset_index())
    lb = lb[(lb["v_bin"] >= 185) & (lb["v_bin"] <= 345)]
    cells = lb.groupby(["circuit", "v_bin"])["year"].nunique()
    both = cells[cells == 2].index
    lb = lb.set_index(["circuit", "v_bin"]).loc[both].reset_index()
    lb["cell"] = lb["circuit"] + ":" + lb["v_bin"].astype(str)
    lb["vb"] = lb["v_bin"].astype(str)
    f = smf.ols("acc ~ 0 + C(cell) + C(vb):y26", lb).fit(cov_type="cluster", cov_kwds={"groups": lb["driver_era"]})
    report("accel_speed_bins", str(f.summary()))
    terms = [t for t in f.params.index if t.startswith("C(vb)[") and t.endswith(":y26")]
    gaps = pd.DataFrame([{"v_bin": int(t.split("[")[1].split("]")[0]), **term_row(f, t)} for t in terms]).sort_values("v_bin")
    gaps["cells"] = gaps["v_bin"].map(lb.groupby("v_bin")["circuit"].nunique())
    save(gaps, "accel_speed_delta")
    # Pre-specified contrast: mean gap at >= 290 km/h minus mean gap below 290 km/h
    hi_t = [t for t, v in zip(terms, [int(t.split("[")[1].split("]")[0]) for t in terms]) if v >= 290]
    lo_t = [t for t in terms if t not in hi_t]
    w = pd.Series(0.0, index=f.params.index)
    w[hi_t] = 1 / len(hi_t)
    w[lo_t] = -1 / len(lo_t)
    est = float(w @ f.params)
    se = float(np.sqrt(w @ f.cov_params() @ w))
    SUMMARY["accel_contrast_above_minus_below_290"] = {"estimate": est, "ci_low": est - 1.96 * se, "ci_high": est + 1.96 * se,
                                                       "se": se, "p": float(2 * stats.norm.sf(abs(est / se)))}
    SUMMARY["accel_gap_low_speed_185_245"] = {"mean_gap": float(gaps.loc[gaps["v_bin"] <= 245, "estimate"].mean())}

    # Binned curves with lap-cluster bootstrap CIs, per circuit and pooled (for plotting)
    curves = []
    for c, sub in [("all", d)] + [(c, d[d["circuit"] == c]) for c in CIRCUITS]:
        for y in YEARS:
            s = sub[sub["year"] == y]
            for vb, g in s.groupby("v_bin"):
                if g["lap_id"].nunique() < 8:
                    continue
                per_lap = g.groupby("lap_id")["acc"].mean().to_numpy()
                bm = per_lap[RNG.integers(0, per_lap.size, (500, per_lap.size))].mean(1)
                curves.append({"circuit": c, "year": y, "v_bin": vb, "acc": per_lap.mean(),
                               "ci_low": np.quantile(bm, 0.025), "ci_high": np.quantile(bm, 0.975), "laps": per_lap.size})
    save(pd.DataFrame(curves), "accel_speed_curve")


# ---------- 4. straights: top speed and energy-limit signature ----------

def straights(fs, segs):
    d = fs[(fs["push"] & (fs["stype"] == "Q")) | fs["race_pace"]].copy()
    d["stype"] = np.where(d["stype"] == "Q", "Qualifying", "Race")
    d["clip"] = (d["flat_decel_m"] >= 30).astype(int)
    d["seg_id"] = d["circuit"] + ":" + d["segment"]
    seg_len = segs.assign(seg_id=segs["circuit"] + ":" + segs["segment"]).set_index("seg_id")["length_m"]
    d["length_m"] = d["seg_id"].map(seg_len)

    # Per straight, per era: summaries and the 2026 - 2025 difference in qualifying top speed (Welch)
    summ = (d.groupby(["circuit", "segment", "label", "stype", "year"])
              .agg(laps=("v_max", "size"), v_max=("v_max", "mean"), v_max_sd=("v_max", "std"),
                   flat_decel_m=("flat_decel_m", "mean"), clip_share=("clip", "mean"),
                   acc_last30=("acc_last30", "mean"), seg_time=("seg_time", "mean"))
              .reset_index())
    summ["length_m"] = (summ["circuit"] + ":" + summ["segment"]).map(seg_len)
    save(summ, "straights_summary")

    qd = d[d["stype"] == "Qualifying"]
    rows = []
    for (c, s), g in qd.groupby(["circuit", "segment"]):
        a, b = g.loc[g["year"] == 2025, "v_max"], g.loc[g["year"] == 2026, "v_max"]
        if len(a) < 5 or len(b) < 5:
            continue
        t = stats.ttest_ind(b, a, equal_var=False)
        diff = b.mean() - a.mean()
        se = np.sqrt(b.var() / len(b) + a.var() / len(a))
        rows.append({"circuit": c, "segment": s, "label": g["label"].iloc[0], "length_m": seg_len[f"{c}:{s}"],
                     "v_max_2025": a.mean(), "v_max_2026": b.mean(), "delta": diff,
                     "ci_low": diff - 1.96 * se, "ci_high": diff + 1.96 * se, "p": t.pvalue})
    vt = pd.DataFrame(rows)
    vt["p_holm"] = holm(vt["p"])
    # Does the top-speed loss grow with the 2025 top speed (power fades above 290 km/h)?
    w = sm.WLS(vt["delta"], sm.add_constant(vt["v_max_2025"]), weights=1 / ((vt["ci_high"] - vt["ci_low"]) / 3.92) ** 2).fit()
    report("topspeed_meta_regression", str(w.summary()))
    save(vt, "straights_topspeed_delta")

    # Hurdle model for slowing down at full throttle: P(any) by logistic GEE, amount by gamma GEE
    logit = smf.gee("clip ~ C(circuit) + y26 * C(stype) + np.log(length_m)", "driver_era", d,
                    family=sm.families.Binomial(), cov_struct=sm.cov_struct.Exchangeable()).fit()
    pos = d[d["clip"] == 1]
    gamma = smf.gee("flat_decel_m ~ C(circuit) + y26 * C(stype) + np.log(length_m)", "driver_era", pos,
                    family=sm.families.Gamma(sm.families.links.Log()), cov_struct=sm.cov_struct.Exchangeable()).fit()
    report("clipping_hurdle_logit", str(logit.summary()))
    report("clipping_hurdle_gamma", str(gamma.summary()))

    def combo(fit, scale):
        """Era effect in qualifying (reference) and in the race (main + interaction)."""
        b, V = fit.params, fit.cov_params()
        out = {"Qualifying": term_row(fit, "y26", scale)}
        t1, t2 = "y26", "y26:C(stype)[T.Race]"
        est = b[t1] + b[t2]
        se = np.sqrt(V.loc[t1, t1] + V.loc[t2, t2] + 2 * V.loc[t1, t2])
        lo, hi = est - 1.96 * se, est + 1.96 * se
        conv = np.exp if scale == "ratio" else (lambda x: x)
        out["Race"] = {"estimate": float(conv(est)), "ci_low": float(conv(lo)), "ci_high": float(conv(hi)),
                       "se": float(se), "p": float(2 * stats.norm.sf(abs(est / se)))}
        return out

    SUMMARY["clipping"] = {"odds_ratio": combo(logit, "ratio"), "amount_ratio": combo(gamma, "ratio"),
                           "share": d.groupby(["year", "stype"])["clip"].mean().round(3).unstack().to_dict()}
    # Same occurrence model with 2026 split by regime (Australia before the Miami change)
    d = regime_terms(d)
    logit_r = smf.gee("clip ~ C(circuit) + C(stype) + C(stype):y26_pre + C(stype):y26_post + np.log(length_m)", "driver_era", d,
                      family=sm.families.Binomial(), cov_struct=sm.cov_struct.Exchangeable()).fit()
    report("clipping_logit_by_regime", str(logit_r.summary()))
    SUMMARY["clipping_odds_ratio_by_regime"] = regime_effects(logit_r, ["Qualifying", "Race"], scale="ratio")
    share = d.assign(reg=np.where(d["year"] == 2025, "2025", np.where(d["y26_pre"] == 1, "2026 pre-Miami", "2026 post-Miami")))
    save(share.groupby(["circuit", "stype", "reg"])["clip"].mean().reset_index(), "clipping_share_by_circuit")
    SUMMARY["topspeed"] = {"straights_tested": int(len(vt)), "significant_holm": int((vt["p_holm"] < 0.05).sum()),
                           "mean_delta_kmh": float(vt["delta"].mean()),
                           "slope_vs_2025_top_speed": {"estimate": float(w.params.iloc[1]), "p": float(w.pvalues.iloc[1])}}


# ---------- 5. lift and coast ----------

def regime_terms(d: pd.DataFrame) -> pd.DataFrame:
    """2026 split by energy-management regime: Australia ran before the Miami change, the rest after."""
    d["y26_pre"] = ((d["year"] == 2026) & (d["circuit"] == "australia")).astype(int)
    d["y26_post"] = ((d["year"] == 2026) & (d["circuit"] != "australia")).astype(int)
    return d


def regime_effects(fit, stypes, prefix="C(stype)", scale=None):
    """Era effects per session type and regime, plus the difference-in-differences pre - post."""
    out = {}
    V = fit.cov_params()
    for st in stypes:
        pre, post = f"{prefix}[{st}]:y26_pre", f"{prefix}[{st}]:y26_post"
        out[st] = {"pre_miami": term_row(fit, pre, scale), "post_miami": term_row(fit, post, scale)}
        est = fit.params[pre] - fit.params[post]
        se = float(np.sqrt(V.loc[pre, pre] + V.loc[post, post] - 2 * V.loc[pre, post]))
        conv = np.exp if scale == "ratio" else (lambda x: x)   # ratio scale: ratio of odds ratios
        out[st]["pre_minus_post"] = {"estimate": float(conv(est)), "ci_low": float(conv(est - 1.96 * se)),
                                     "ci_high": float(conv(est + 1.96 * se)), "se": se,
                                     "p": float(2 * stats.norm.sf(abs(est / se)))}
    return out


def lift_coast(fc):
    d = fc[(fc["push"] & (fc["stype"] == "Q")) | fc["race_pace"]].copy()
    d["stype"] = np.where(d["stype"] == "Q", "Qualifying", "Race")
    per_lap = (d.groupby(KEYS + ["stype", "y26", "driver_era", "team_era"])["lift_coast_m"]
                .sum(min_count=1).reset_index().dropna())
    # One value per driver, circuit and session type (mean metres per lap); circuit x session fixed
    # effects; 2026 split into pre- and post-Miami; SEs clustered by team-era.
    agg = per_lap.groupby(["circuit", "year", "stype", "driver_era", "team_era"])["lift_coast_m"].mean().reset_index()
    agg = regime_terms(agg)
    m = smf.ols("lift_coast_m ~ 0 + C(circuit):C(stype) + C(stype):y26_pre + C(stype):y26_post", agg).fit(
        cov_type="cluster", cov_kwds={"groups": agg["team_era"]})
    report("lift_coast_ols_cluster", str(m.summary()))
    SUMMARY["lift_coast_m_per_lap"] = regime_effects(m, ["Qualifying", "Race"])
    summ = per_lap.groupby(["circuit", "stype", "year"])["lift_coast_m"].agg(["mean", "median", "size"]).reset_index()
    save(summ, "lift_coast_summary")
    by_corner = d.groupby(["circuit", "segment", "label", "stype", "year"])["lift_coast_m"].mean().reset_index()
    save(by_corner, "lift_coast_by_corner")


# ---------- 6. corners ----------

def corners(fc):
    d = fc[fc["push"] & (fc["stype"] == "Q")].copy()
    d["seg_id"] = d["circuit"] + ":" + d["segment"]
    ref = d[d["year"] == 2025].groupby("seg_id")["v_min"].median()
    d["speed_class"] = pd.cut(d["seg_id"].map(ref), [0, 130, 200, 400], labels=["slow (<130)", "medium (130-200)", "fast (>200)"])
    d = d.dropna(subset=["speed_class"])
    d["speed_class"] = d["speed_class"].astype(str)
    cls = sorted(d["speed_class"].unique())

    # One value per driver and corner (mean over push laps), corner fixed effects,
    # SEs clustered by team-era: robust where the mixed model's Hessian is not positive definite.
    def fit(df, y, name):
        agg = (df.groupby(["seg_id", "speed_class", "driver_era", "team_era", "y26"])[y].mean().reset_index())
        m = smf.ols(f"{y} ~ 0 + C(seg_id) + y26:C(speed_class)", agg).fit(cov_type="cluster", cov_kwds={"groups": agg["team_era"]})
        report(name, str(m.summary()))
        return pd.DataFrame([{"speed_class": k, **term_row(m, f"y26:C(speed_class)[{k}]")} for k in cls
                             if f"y26:C(speed_class)[{k}]" in m.params])

    vmin = fit(d, "v_min", "corner_vmin_ols_cluster")
    # Average braking deceleration (m/s^2) where the car brakes for at least 20 m
    bk = d[(d["brake_dist_m"] >= 20) & d["v_brake"].notna()].copy()
    bk["decel"] = ((bk["v_brake"] / 3.6) ** 2 - (bk["v_min"] / 3.6) ** 2) / (2 * bk["brake_dist_m"])
    bk = bk[(bk["decel"] > 5) & (bk["decel"] < 60)]
    decel = fit(bk, "decel", "corner_braking_decel_ols_cluster")
    vmin["metric"], decel["metric"] = "min_speed_kmh", "braking_decel_ms2"
    save(pd.concat([vmin, decel]), "corner_effects")

    per = (d.groupby(["circuit", "segment", "label", "speed_class", "year"])
             .agg(laps=("v_min", "size"), v_min=("v_min", "mean"), brake_dist_m=("brake_dist_m", "mean"),
                  throttle_on_m=("throttle_on_m", "mean"), gear_min=("gear_min", "median"), seg_time=("seg_time", "mean"))
             .reset_index())
    save(per, "corners_summary")
    SUMMARY["corners"] = {"min_speed_kmh": vmin.set_index("speed_class")[["estimate", "ci_low", "ci_high", "p"]].round(3).to_dict(orient="index"),
                          "braking_decel_ms2": decel.set_index("speed_class")[["estimate", "ci_low", "ci_high", "p"]].round(3).to_dict(orient="index")}


# ---------- 7. racing lines ----------

def nearest_offset(px, py, lx, ly):
    """Distance from each point (px, py) to the nearest vertex of a densified line (lx, ly)."""
    t = np.linspace(0, 1, 5)
    dx = (lx[:-1, None] + (lx[1:, None] - lx[:-1, None]) * t).ravel()
    dy = (ly[:-1, None] + (ly[1:, None] - ly[:-1, None]) * t).ravel()
    out = np.empty(px.size)
    for i, (x, y) in enumerate(zip(px, py)):
        out[i] = np.sqrt(np.nanmin((dx - x) ** 2 + (dy - y) ** 2))
    return out / 10.0  # position data are in decimetres


def racing_lines(laps, segs):
    rows, lines = [], []
    for c in CIRCUITS:
        g = {y: grid_rows(y, c, laps[laps["stype"] == "Q"], "push")[0] for y in YEARS}
        x25, y25 = np.nanmean(g[2025]["x"], 0), np.nanmean(g[2025]["y"], 0)
        x26, y26 = np.nanmean(g[2026]["x"], 0), np.nanmean(g[2026]["y"], 0)
        off = nearest_offset(x26, y26, x25, y25)
        # Noise floor: offset between two random halves of the 2025 laps
        n = g[2025]["x"].shape[0]
        noise = []
        for _ in range(50):
            p = RNG.permutation(n)
            h1, h2 = p[: n // 2], p[n // 2:]
            noise.append(nearest_offset(np.nanmean(g[2025]["x"][h1], 0), np.nanmean(g[2025]["y"][h1], 0),
                                        np.nanmean(g[2025]["x"][h2], 0), np.nanmean(g[2025]["y"][h2], 0)))
        noise = np.array(noise)
        lines.append(pd.DataFrame({"circuit": c, "i": np.arange(off.size), "x_2025": x25, "y_2025": y25,
                                   "x_2026": x26, "y_2026": y26, "offset_m": off, "noise_m": noise.mean(0)}))
        for s in segs[(segs["circuit"] == c) & (segs["kind"] == "corner")].itertuples():
            sl = slice(s.i0, s.i1)
            rows.append({"circuit": c, "segment": s.segment, "label": s.label, "offset_m": off[sl].mean(),
                         "noise_m": noise[:, sl].mean(), "noise_p95": np.quantile(noise[:, sl].mean(1), 0.95)})
    pd.concat(lines).to_parquet(RESULTS / "racing_lines.parquet", index=False)
    rl = pd.DataFrame(rows)
    rl["beyond_noise"] = rl["offset_m"] > rl["noise_p95"]
    save(rl, "racing_line_offsets")
    SUMMARY["racing_lines"] = {"corner_zones": int(len(rl)), "beyond_noise": int(rl["beyond_noise"].sum()),
                               "median_offset_m": float(rl["offset_m"].median())}


# ---------- 8. tyres ----------

def tyres(laps):
    d = laps[laps["race_pace"] & laps["compound"].isin(["SOFT", "MEDIUM", "HARD"])].copy()
    d = d.dropna(subset=["tyre_life", "lap_time", "lap"])
    for col in ("tyre_life", "lap_time", "lap"):
        d[col] = d[col].astype("float64")
    d["compound"] = d["compound"].astype(object)
    rows = []
    for (c, y), g in d.groupby(["circuit", "year"]):
        keep = g.groupby("compound")["lap"].transform("size") >= 30
        g = g[keep]
        if g["compound"].nunique() == 0:
            continue
        form = "lap_time ~ 0 + C(compound) + C(compound):tyre_life + lap" if g["compound"].nunique() > 1 \
            else "lap_time ~ tyre_life + lap"
        try:
            m = mixed(form, g, "driver")
        except Exception as e:  # noqa: BLE001 - record and continue
            print("tyre model failed", c, y, e)
            continue
        report(f"tyre_deg_{c}_{y}", str(m.summary()))
        for comp in g["compound"].unique():
            term = f"C(compound)[{comp}]:tyre_life" if g["compound"].nunique() > 1 else "tyre_life"
            r = term_row(m, term)
            cc = g.loc[g["compound"] == comp, "compound_c"].iloc[0]
            rows.append({"circuit": c, "year": y, "compound": comp, "compound_c": cc, "laps": int((g["compound"] == comp).sum()),
                         "stints": int(g.loc[g["compound"] == comp, ["driver", "stint"]].drop_duplicates().shape[0]),
                         "deg_s_per_lap": r["estimate"], "ci_low": r["ci_low"], "ci_high": r["ci_high"], "p": r["p"],
                         "fuel_s_per_lap": m.params["lap"]})
    deg = pd.DataFrame(rows)
    save(deg, "tyre_degradation")
    # Meta-analysis across circuits: era difference in degradation, compound-class and circuit adjusted
    w = 1 / ((deg["ci_high"] - deg["ci_low"]) / 3.92) ** 2
    meta = smf.wls("deg_s_per_lap ~ C(circuit) + C(compound) + C(year)", deg, weights=w).fit()
    report("tyre_deg_meta", str(meta.summary()))
    SUMMARY["tyre_deg_2026_minus_2025_s_per_lap"] = term_row(meta, "C(year)[T.2026]")

    # Strategy: stops and stint lengths (race)
    r = laps[laps["stype"] == "R"]
    n_laps = r.groupby(["year", "circuit"])["lap"].max().rename("race_laps")
    drv = (r.groupby(["year", "circuit", "driver"])
             .agg(laps_done=("lap", "max"), stops=("pit_in_time", lambda s: s.notna().sum()))
             .reset_index().join(n_laps, on=["year", "circuit"]))
    drv = drv[drv["laps_done"] >= 0.9 * drv["race_laps"]]
    stints = (r.dropna(subset=["stint"]).groupby(["year", "circuit", "driver", "stint", "compound"])
                .agg(length=("lap", "size")).reset_index())
    save(drv, "race_stops")
    save(stints, "race_stints")
    pois = smf.glm("stops ~ C(circuit) + C(year)", drv, family=sm.families.Poisson()).fit()
    report("stops_poisson", str(pois.summary()) + f"\nPearson chi2/df = {pois.pearson_chi2 / pois.df_resid:.3f}")
    SUMMARY["stops_rate_ratio"] = term_row(pois, "C(year)[T.2026]", "ratio")


# ---------- 9. the racing: overtakes and field spread ----------

def racing(laps):
    rows = []
    for y in YEARS:
        for c in CIRCUITS:
            base = RAW / "openf1" / f"{y}_{c}"
            try:
                ses = json.loads((base / "sessions.json").read_text(encoding="utf-8"))
                ov = json.loads((base / "overtakes.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            race = [s["session_key"] for s in ses if s["session_name"] == "Race"]
            n = sum(1 for o in ov if o.get("session_key") in race)
            rows.append({"year": y, "circuit": c, "overtakes": n})
    ov = pd.DataFrame(rows)
    pace = laps[laps["race_pace"]].groupby(["year", "circuit", "driver"])["lap_time"].median().reset_index()
    pace["gap_pct"] = pace.groupby(["year", "circuit"])["lap_time"].transform(lambda s: (s / s.min() - 1) * 100)
    spread = pace.groupby(["year", "circuit"])["gap_pct"].agg(spread_sd="std", spread_max="max", drivers="size").reset_index()
    out = ov.merge(spread, on=["year", "circuit"], how="outer")
    save(out, "racing_summary")
    save(pace, "race_pace_by_driver")

    wide = out.pivot(index="circuit", columns="year")
    res = {}
    if ov["overtakes"].sum() > 0:
        g = smf.glm("overtakes ~ C(circuit) + C(year)", ov, family=sm.families.Poisson()).fit()
        disp = g.pearson_chi2 / g.df_resid
        nb = smf.glm("overtakes ~ C(circuit) + C(year)", ov, family=sm.families.NegativeBinomial(alpha=max(disp - 1, 1e-3) / ov["overtakes"].mean())).fit()
        report("overtakes_glm", str(g.summary()) + f"\nPearson chi2/df = {disp:.2f}\n\n" + str(nb.summary()))
        res["overtakes_rate_ratio_poisson"] = term_row(g, "C(year)[T.2026]", "ratio")
        res["overtakes_rate_ratio_negbin"] = term_row(nb, "C(year)[T.2026]", "ratio")
        res["overtakes_dispersion"] = disp
        dif = wide["overtakes"][2026] - wide["overtakes"][2025]
        res["overtakes_wilcoxon_p"] = float(stats.wilcoxon(dif.dropna()).pvalue)
    dsp = wide["spread_sd"][2026] - wide["spread_sd"][2025]
    res["spread_sd_change_pct_points"] = float(dsp.mean())
    res["spread_wilcoxon_p"] = float(stats.wilcoxon(dsp.dropna()).pvalue)
    bf = {c: float(stats.levene(pace.loc[(pace["year"] == 2025) & (pace["circuit"] == c), "gap_pct"],
                                pace.loc[(pace["year"] == 2026) & (pace["circuit"] == c), "gap_pct"], center="median").pvalue)
          for c in CIRCUITS}
    res["spread_brown_forsythe_p_holm"] = dict(zip(bf, holm(list(bf.values())).round(4)))
    SUMMARY["racing"] = res


# ---------- 10. power units ----------

def power_units(fs):
    d = fs[fs["push"] & (fs["stype"] == "Q")].copy()
    d["seg_id"] = d["circuit"] + ":" + d["segment"]
    rows = []
    for y in YEARS:
        s = d[d["year"] == y]
        ref = "Mercedes"
        for metric in ("v_max", "flat_decel_m", "acc_last30"):
            ss = s.dropna(subset=[metric])
            f = smf.ols(f"{metric} ~ C(seg_id) + C(pu, Treatment('{ref}'))", ss).fit(cov_type="cluster", cov_kwds={"groups": ss["driver_era"]})
            report(f"pu_{metric}_{y}", str(f.summary()))
            for pu in sorted(ss["pu"].dropna().unique()):
                if pu == ref:
                    rows.append({"year": y, "metric": metric, "pu": pu, "estimate": 0.0, "ci_low": 0.0, "ci_high": 0.0, "p": np.nan,
                                 "teams": ", ".join(sorted(ss.loc[ss["pu"] == pu, "lineage"].unique()))})
                    continue
                r = term_row(f, f"C(pu, Treatment('{ref}'))[T.{pu}]")
                rows.append({"year": y, "metric": metric, "pu": pu, **r,
                             "teams": ", ".join(sorted(ss.loc[ss["pu"] == pu, "lineage"].unique()))})
    save(pd.DataFrame(rows), "power_unit_effects")


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    MODELS.mkdir(parents=True, exist_ok=True)
    laps, fs, fc, fl, segs = load()
    steps = [("coverage", lambda: coverage(laps)), ("one-lap pace", lambda: one_lap_pace(laps, fl)),
             ("speed profiles", lambda: speed_profiles(laps, segs)), ("acceleration vs speed", lambda: accel_speed(laps)),
             ("straights", lambda: straights(fs, segs)), ("lift and coast", lambda: lift_coast(fc)),
             ("corners", lambda: corners(fc)), ("racing lines", lambda: racing_lines(laps, segs)),
             ("tyres", lambda: tyres(laps)), ("racing", lambda: racing(laps)), ("power units", lambda: power_units(fs))]
    for name, fn in steps:
        fn()
        print("done:", name)
    segs.drop(columns=["i0", "i1"]).to_csv(RESULTS / "segments.csv", index=False)
    pd.read_parquet(PROCESSED / "corners_xy.parquet").to_csv(RESULTS / "corners_xy.csv", index=False)
    (RESULTS / "summary.json").write_text(json.dumps(SUMMARY, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
