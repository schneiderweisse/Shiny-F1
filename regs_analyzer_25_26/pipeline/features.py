"""Step 2: telemetry on a common distance grid, a shared segment map per circuit, and features.

1. Every clean lap with telemetry is resampled onto a 10 m grid along the official lap length
   (distance = TracingInsights rel_distance x official length): speed, throttle, brake, gear, RPM,
   elapsed time and x/y. One .npz per year and circuit in data/interim/.
2. Segment map per circuit, identical for both years: straights are runs where the median throttle of
   qualifying push laps (average of the 2025 and 2026 medians) is >= 90% for >= 200 m; everything
   else is a corner zone, labelled with the official corner numbers matched by x/y position.
3. Features per lap and segment (straights, corners) and per lap (whole-lap summaries).

Run from regs_analyzer_25_26/:  python -m pipeline.features
"""
import json
from concurrent.futures import ProcessPoolExecutor

import sys

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from config import CIRCUITS, GRID_STEP_M, INTERIM, PROCESSED, YEARS
from pipeline.fetch import ti_dir

CHANNELS = ("speed", "throttle", "brake", "gear", "rpm", "time", "x", "y", "drs")
FULL_THROTTLE = 98.0      # % : "flat out"
STRAIGHT_THROTTLE = 90.0  # % : median throttle that defines a straight
MIN_STRAIGHT_M = 200.0
DECEL_AT_FT = -0.05       # km/h per metre: slowing down while flat out (energy limit / clipping)
COAST_THROTTLE = 10.0     # %: below this with no brake = coasting


# ---------- 1. Resampling ----------

def grid_for(circuit: str) -> np.ndarray:
    return np.arange(0.0, CIRCUITS[circuit]["length_m"], GRID_STEP_M)


def resample_lap(path, grid: np.ndarray, length: float):
    try:
        tel = json.loads(path.read_text(encoding="utf-8"))["tel"]
    except (OSError, ValueError, KeyError):
        return None
    rel = np.asarray(pd.to_numeric(pd.Series(tel.get("rel_distance")), errors="coerce"), dtype=float)
    if rel.size < 50 or np.isnan(rel).mean() > 0.1:
        return None
    s = rel * length
    ok = ~np.isnan(s)
    out = {}
    for ch in CHANNELS:
        v = np.asarray(pd.to_numeric(pd.Series(tel.get(ch)), errors="coerce"), dtype=float)
        if v.size != rel.size:
            v = np.full(rel.size, np.nan)
        m = ok & ~np.isnan(v)
        out[ch] = np.interp(grid, s[m], v[m]) if m.sum() > 10 else np.full(grid.size, np.nan)
    out["gear"] = np.round(out["gear"])
    out["brake"] = np.clip(out["brake"], 0, 1)
    return out


def resample_circuit(args):
    year, circuit, laps = args
    grid, length = grid_for(circuit), CIRCUITS[circuit]["length_m"]
    base = ti_dir(year) / CIRCUITS[circuit]["event"][year]
    keep, mats = [], {ch: [] for ch in CHANNELS}
    for r in laps.itertuples():
        res = resample_lap(base / r.session / r.driver / f"{int(r.lap)}_tel.json", grid, length)
        if res is None:
            continue
        keep.append(r.Index)
        for ch in CHANNELS:
            mats[ch].append(res[ch])
    idx = laps.loc[keep, ["year", "circuit", "session", "stype", "driver", "lap"]].reset_index(drop=True)
    idx["tel_ok"] = True  # set by quality_check()
    arrays = {ch: np.asarray(mats[ch], dtype=np.float32) for ch in CHANNELS}
    INTERIM.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(INTERIM / f"grid_{year}_{circuit}.npz", grid=grid, **arrays)
    idx.to_parquet(INTERIM / f"grid_index_{year}_{circuit}.parquet", index=False)
    return year, circuit, len(idx)


def load_grid(year: int, circuit: str):
    z = np.load(INTERIM / f"grid_{year}_{circuit}.npz")
    return {k: z[k] for k in z.files}, pd.read_parquet(INTERIM / f"grid_index_{year}_{circuit}.parquet")


def quality_check(year: int, circuit: str, laps: pd.DataFrame) -> pd.Series:
    """Flag laps whose telemetry is misaligned or broken (tel_ok column in the grid index).

    Each speed trace is cross-correlated (circularly, via FFT) with the median qualifying push lap
    of the same circuit and year. A lap passes when its best alignment is within 30 m, its
    correlation at zero shift is >= 0.90 and the telemetry duration matches the official lap time
    within 0.5 s. This catches sessions where laps were sliced from the wrong start point.
    """
    g, idx = load_grid(year, circuit)
    v = g["speed"].astype(float)
    keys = ["year", "circuit", "session", "driver", "lap"]
    m = idx.merge(laps[keys + ["push", "lap_time"]], on=keys, how="left")
    ref_rows = np.flatnonzero((m["session"] == "Qualifying").to_numpy() & m["push"].fillna(False).to_numpy())
    ref = np.nanmedian(v[ref_rows if ref_rows.size >= 5 else slice(None)], axis=0)
    vz = np.nan_to_num(v - np.nanmean(v, axis=1, keepdims=True))
    rz = ref - np.nanmean(ref)
    norm = np.linalg.norm(vz, axis=1) * np.linalg.norm(rz)
    cc = np.fft.irfft(np.fft.rfft(vz, axis=1) * np.conj(np.fft.rfft(rz)), n=v.shape[1], axis=1) / np.where(norm > 0, norm, np.nan)[:, None]
    shift = np.nanargmax(np.nan_to_num(cc, nan=-1), axis=1)
    shift = np.where(shift > v.shape[1] // 2, shift - v.shape[1], shift)
    tdiff = np.abs(g["time"][:, -1] - g["time"][:, 0] - m["lap_time"].to_numpy())
    idx["tel_shift_m"] = shift * GRID_STEP_M
    idx["tel_corr"] = cc[:, 0]
    idx["tel_time_diff"] = tdiff
    idx["tel_ok"] = (np.abs(shift) <= 3) & (cc[:, 0] >= 0.90) & (tdiff <= 0.5)
    idx.to_parquet(INTERIM / f"grid_index_{year}_{circuit}.parquet", index=False)
    return idx.groupby("stype")["tel_ok"].agg(["mean", "size"])


# ---------- 2. Segment map ----------

def runs(mask: np.ndarray):
    """Start/end (exclusive) indices of True runs."""
    d = np.diff(np.r_[0, mask.astype(int), 0])
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def split_corner_zone(speed: np.ndarray, a: int, b: int, prominence: float = 10.0) -> list[tuple[int, int]]:
    """Split a corner zone at the speed peaks between corners, so each piece holds one braking event."""
    v = speed[a:b]
    if v.size < 8:
        return [(a, b)]
    minima, _ = find_peaks(-v, prominence=prominence, distance=5)
    if minima.size < 2:
        return [(a, b)]
    cuts = [a + m0 + int(np.argmax(v[m0:m1])) for m0, m1 in zip(minima[:-1], minima[1:])]
    edges = [a] + cuts + [b]
    return [(x, y) for x, y in zip(edges[:-1], edges[1:]) if y > x]


def segment_map(circuit: str) -> pd.DataFrame:
    grid = grid_for(circuit)
    med_thr, med_v, xs, ys = [], [], [], []
    for year in YEARS:
        g, idx = load_grid(year, circuit)
        laps = pd.read_parquet(PROCESSED / "laps.parquet", columns=["year", "circuit", "session", "driver", "lap", "push"])
        laps = laps[(laps["year"] == year) & (laps["circuit"] == circuit) & laps["push"] & (laps["session"] == "Qualifying")]
        sel = idx[idx["tel_ok"]].reset_index().merge(laps, on=["year", "circuit", "session", "driver", "lap"])["index"].to_numpy()
        if sel.size < 5:  # fall back to all good practice/qualifying laps
            sel = np.flatnonzero((idx["stype"].isin(["Q", "FP"]) & idx["tel_ok"]).to_numpy())
        med_thr.append(np.nanmedian(g["throttle"][sel], axis=0))
        med_v.append(np.nanmedian(g["speed"][sel], axis=0))
        xs.append(np.nanmedian(g["x"][sel], axis=0))
        ys.append(np.nanmedian(g["y"][sel], axis=0))
    thr = np.nanmean(med_thr, axis=0)
    straight = thr >= STRAIGHT_THROTTLE
    # Close gaps shorter than 50 m inside a straight (kinks taken flat by most drivers)
    for a, b in runs(~straight):
        if 0 < a and b < straight.size and (b - a) * GRID_STEP_M < 50:
            straight[a:b] = True
    seg_rows = []
    for a, b in runs(straight):
        # The start/finish straight is split by the line: keep both halves if each is >= 100 m
        at_line = a == 0 or b == straight.size
        if (b - a) * GRID_STEP_M >= MIN_STRAIGHT_M or (at_line and (b - a) * GRID_STEP_M >= 100):
            seg_rows.append(("straight", a, b))
    straight_mask = np.zeros_like(straight)
    for _, a, b in seg_rows:
        straight_mask[a:b] = True
    speed = np.convolve(np.nanmean(med_v, axis=0), np.ones(3) / 3, mode="same")
    for a, b in runs(~straight_mask):
        seg_rows += [("corner", x, y) for x, y in split_corner_zone(speed, a, b)]
    segs = pd.DataFrame(seg_rows, columns=["kind", "i0", "i1"]).sort_values("i0").reset_index(drop=True)

    # Label corner zones with official corner numbers, matched by x/y to the mean line
    lx, ly = np.nanmean(xs, axis=0), np.nanmean(ys, axis=0)
    year = 2026
    c = json.loads((ti_dir(year) / CIRCUITS[circuit]["event"][year] / "Qualifying" / "corners.json").read_text(encoding="utf-8"))
    pos = [int(np.nanargmin((lx - x) ** 2 + (ly - y) ** 2)) for x, y in zip(c["X"], c["Y"])]
    names = [f"{n}{l or ''}" for n, l in zip(c["CornerNumber"], c.get("CornerLetter", [""] * len(pos)))]
    segs["corners"] = [", ".join(n for n, p in zip(names, pos) if a <= p < b) for a, b in zip(segs["i0"], segs["i1"])]
    segs["start_m"], segs["end_m"] = segs["i0"] * GRID_STEP_M, segs["i1"] * GRID_STEP_M
    segs["length_m"] = segs["end_m"] - segs["start_m"]
    segs["circuit"] = circuit
    n = {"straight": 0, "corner": 0}
    ids = []
    for k in segs["kind"]:
        n[k] += 1
        ids.append(("S" if k == "straight" else "C") + str(n[k]))
    segs["segment"] = ids
    segs["label"] = np.where(segs["kind"] == "corner",
                             np.where(segs["corners"] != "", "Turn " + segs["corners"], segs["segment"]),
                             segs["segment"])
    corners_xy = pd.DataFrame({"circuit": circuit, "corner": names, "grid_i": pos,
                               "x": lx[pos], "y": ly[pos]})
    line = pd.DataFrame({"circuit": circuit, "i": np.arange(grid.size), "dist_m": grid, "x": lx, "y": ly, "throttle_med": thr})
    return segs, corners_xy, line


# ---------- 3. Features ----------

def straight_features(g, i0, i1):
    v, thr, brk, t = g["speed"][:, i0:i1], g["throttle"][:, i0:i1], g["brake"][:, i0:i1], g["time"][:, i0:i1]
    n = i1 - i0
    dv = np.gradient(v, GRID_STEP_M, axis=1)                    # km/h per metre
    vms = v / 3.6
    acc = vms * np.gradient(vms, GRID_STEP_M, axis=1)           # m/s^2 = v dv/ds
    flat = thr >= FULL_THROTTLE
    last = slice(int(n * 0.7), n)
    with np.errstate(invalid="ignore"):
        a_last = np.nanmean(np.where(flat[:, last], acc[:, last], np.nan), axis=1)
    return pd.DataFrame({
        "v_entry": v[:, 0], "v_max": np.nanmax(v, axis=1), "v_exit": v[:, -1],
        "vmax_pos": np.nanargmax(np.nan_to_num(v, nan=-1), axis=1) / max(n - 1, 1),
        "full_throttle_frac": flat.mean(axis=1),
        "acc_last30": a_last,
        "flat_decel_m": ((flat & (dv < DECEL_AT_FT)).sum(axis=1)) * GRID_STEP_M,
        "coast_m": ((thr < COAST_THROTTLE) & (brk < 0.5)).sum(axis=1) * GRID_STEP_M,
        "seg_time": t[:, -1] - t[:, 0],
        "rpm_max": np.nanmax(g["rpm"][:, i0:i1], axis=1),
    })


def corner_features(g, i0, i1, look_back=30):
    a = max(0, i0 - look_back)                                  # braking starts on the preceding straight
    v, thr, brk = g["speed"][:, a:i1], g["throttle"][:, a:i1], g["brake"][:, a:i1]
    off = i0 - a
    vz = v[:, off:]
    i_min = off + np.nanargmin(np.nan_to_num(vz, nan=1e9), axis=1)
    rows = np.arange(v.shape[0])
    braking = brk >= 0.5
    # First brake application in the window before the minimum-speed point
    before = np.arange(v.shape[1])[None, :] <= i_min[:, None]
    b_any = (braking & before).any(axis=1)
    i_brake = np.where(b_any, np.argmax(braking & before, axis=1), -1)
    # Throttle back to flat after the minimum
    after = np.arange(v.shape[1])[None, :] >= i_min[:, None]
    ft_after = (thr >= 95) & after
    t_any = ft_after.any(axis=1)
    i_thr = np.where(t_any, np.argmax(ft_after, axis=1), -1)
    # Coasting between the last flat-out point and the brake (lift and coast)
    coast = np.full(v.shape[0], np.nan)
    for r in np.flatnonzero(b_any):
        flat_before = np.flatnonzero(thr[r, : i_brake[r]] >= 95)
        if flat_before.size:
            j = flat_before[-1]
            coast[r] = ((thr[r, j:i_brake[r]] < COAST_THROTTLE) & (brk[r, j:i_brake[r]] < 0.5)).sum() * GRID_STEP_M
    return pd.DataFrame({
        "v_min": v[rows, i_min],
        "vmin_pos_m": (i_min - off) * GRID_STEP_M,
        "v_brake": np.where(b_any, v[rows, np.maximum(i_brake, 0)], np.nan),
        "brake_dist_m": np.where(b_any, (i_min - i_brake) * GRID_STEP_M, np.nan),
        "throttle_on_m": np.where(t_any, (i_thr - i_min) * GRID_STEP_M, np.nan),
        "lift_coast_m": coast,
        "gear_min": np.nanmin(g["gear"][:, i0:i1], axis=1),
        "seg_time": g["time"][:, i1 - 1] - g["time"][:, i0],
    })


def lap_features(g):
    v, thr, brk = g["speed"], g["throttle"], g["brake"]
    dv = np.gradient(v, GRID_STEP_M, axis=1)
    flat = thr >= FULL_THROTTLE
    return pd.DataFrame({
        "v_max_lap": np.nanmax(v, axis=1),
        "v_mean": np.nanmean(v, axis=1),
        "full_throttle_frac": flat.mean(axis=1),
        "braking_frac": (brk >= 0.5).mean(axis=1),
        "coast_frac": ((thr < COAST_THROTTLE) & (brk < 0.5)).mean(axis=1),
        "flat_decel_m": (flat & (dv < DECEL_AT_FT)).sum(axis=1) * GRID_STEP_M,
        "tel_lap_time": g["time"][:, -1] - g["time"][:, 0],
        "drs_frac": np.nanmean(g["drs"] > 0.5, axis=1),
    })


def main() -> None:
    laps = pd.read_parquet(PROCESSED / "laps.parquet")
    todo = laps[laps["clean"] & laps["has_tel"]]
    # --reuse: keep grids that already exist (resampling is the slow part)
    reuse = "--reuse" in sys.argv
    tasks = [(y, c, todo[(todo["year"] == y) & (todo["circuit"] == c)]) for y in YEARS for c in CIRCUITS
             if not (reuse and (INTERIM / f"grid_{y}_{c}.npz").exists())]
    if tasks:
        with ProcessPoolExecutor(max_workers=7) as ex:
            for year, circuit, n in ex.map(resample_circuit, tasks):
                print(f"resampled {year} {circuit:<10} {n:>5} laps")

    qa = []
    for year in YEARS:
        for circuit in CIRCUITS:
            r = quality_check(year, circuit, laps).reset_index()
            r["year"], r["circuit"] = year, circuit
            qa.append(r)
    qa = pd.concat(qa).rename(columns={"mean": "share_ok", "size": "laps"})
    qa.to_csv(PROCESSED / "telemetry_qa.csv", index=False)
    print(qa.pivot_table(index=["year", "circuit"], columns="stype", values="share_ok").round(2).to_string())

    seg_all, corners_all, lines_all, fs, fc, fl = [], [], [], [], [], []
    for circuit in CIRCUITS:
        segs, cxy, line = segment_map(circuit)
        seg_all.append(segs); corners_all.append(cxy); lines_all.append(line)
        for year in YEARS:
            g, idx = load_grid(year, circuit)
            for s in segs.itertuples():
                f = (straight_features if s.kind == "straight" else corner_features)(g, s.i0, s.i1)
                f = pd.concat([idx, f], axis=1)
                f["segment"], f["label"] = s.segment, s.label
                (fs if s.kind == "straight" else fc).append(f)
            fl.append(pd.concat([idx, lap_features(g)], axis=1))
        print(f"features  {circuit:<10} {int((segs.kind == 'straight').sum())} straights, {int((segs.kind == 'corner').sum())} corner zones")

    pd.concat(seg_all).to_parquet(PROCESSED / "segments.parquet", index=False)
    pd.concat(corners_all).to_parquet(PROCESSED / "corners_xy.parquet", index=False)
    pd.concat(lines_all).to_parquet(PROCESSED / "track_lines.parquet", index=False)
    pd.concat(fs, ignore_index=True).to_parquet(PROCESSED / "feat_straights.parquet", index=False)
    pd.concat(fc, ignore_index=True).to_parquet(PROCESSED / "feat_corners.parquet", index=False)
    pd.concat(fl, ignore_index=True).to_parquet(PROCESSED / "feat_laps.parquet", index=False)
    print("done")


if __name__ == "__main__":
    main()
