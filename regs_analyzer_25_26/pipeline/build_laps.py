"""Step 1b: the matched lap table, one row per driver lap, for the 7 circuits in 2025 and 2026.

Adds the compound C-number, team lineage and power unit, the rule regime, weather and lap-quality
flags used everywhere downstream:
  clean     timed, dry tyres, not deleted, not an in/out lap, no SC/VSC/red flag; race laps after lap 1
  push      clean practice/qualifying lap within 102% of the driver's best in that session
  race_pace clean race lap within 107% of the driver's median clean race lap

Run from regs_analyzer_25_26/:  python -m pipeline.build_laps
"""
import json

import numpy as np
import pandas as pd

from config import CIRCUITS, PROCESSED, RAW, REFERENCE, SESSION_TYPE, SESSIONS, YEARS
from pipeline.fetch import ti_dir

RENAME = {"time": "lap_time", "life": "tyre_life", "pos": "position", "pb": "personal_best",
          "del": "deleted", "delR": "deleted_reason", "iacc": "accurate", "ff1G": "generated",
          "sesT": "session_time", "lST": "lap_start_time", "lSD": "lap_start_date",
          "pin": "pit_in_time", "pout": "pit_out_time", "qs": "quali_segment",
          "wTT": "track_temp", "wAT": "air_temp", "wH": "humidity", "wP": "pressure",
          "wR": "rain", "wWS": "wind_speed", "wWD": "wind_dir"}
NUMERIC = ["lap", "lap_time", "stint", "tyre_life", "position", "s1", "s2", "s3", "vi1", "vi2", "vfl", "vst",
           "session_time", "lap_start_time", "pit_in_time", "pit_out_time", "track_temp", "air_temp",
           "humidity", "pressure", "wind_speed", "wind_dir"]
BOOLEAN = ["personal_best", "deleted", "accurate", "generated", "fresh", "rain"]
KEEP = ["lap", "lap_time", "s1", "s2", "s3", "vi1", "vi2", "vfl", "vst", "compound", "stint", "tyre_life",
        "fresh", "position", "status", "personal_best", "deleted", "deleted_reason", "accurate", "generated",
        "session_time", "lap_start_time", "lap_start_date", "pit_in_time", "pit_out_time", "quali_segment",
        "track_temp", "air_temp", "humidity", "pressure", "rain", "wind_speed", "wind_dir"]


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def as_bool(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().isin(["true", "1"])


def session_laps(year: int, key: str, session: str) -> pd.DataFrame | None:
    base = ti_dir(year) / CIRCUITS[key]["event"][year] / session
    drivers = read_json(base / "drivers.json")
    if drivers is None:
        return None
    frames = []
    for d in drivers["drivers"]:
        x = read_json(base / d["driver"] / "laptimes.json")
        if not x:
            continue
        n = max(len(v) for v in x.values() if isinstance(v, list))
        df = pd.DataFrame({k: v for k, v in x.items() if isinstance(v, list) and len(v) == n})
        df = df.rename(columns=RENAME)
        for col in KEEP:
            if col not in df:
                df[col] = np.nan
        df = df[KEEP].copy()
        df["driver"], df["team"], df["driver_number"] = d["driver"], d["team"], str(d.get("dn", ""))
        frames.append(df)
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    for col in NUMERIC:
        df[col] = pd.to_numeric(df[col].replace({"None": np.nan}), errors="coerce")
    for col in BOOLEAN:
        df[col] = as_bool(df[col])
    df["status"] = df["status"].astype(str).replace({"None": "", "nan": ""})
    df["has_tel"] = [(base / d / f"{int(l)}_tel.json").exists() if pd.notna(l) else False
                     for d, l in zip(df["driver"], df["lap"])]
    df.insert(0, "session", session)
    df.insert(0, "circuit", key)
    df.insert(0, "year", year)
    return df


def session_dates() -> pd.DataFrame:
    rows = []
    for year in YEARS:
        for key in CIRCUITS:
            s = read_json(RAW / "openf1" / f"{year}_{key}" / "sessions.json") or []
            rows += [{"year": year, "circuit": key, "session": x["session_name"], "date": x["date_start"][:10]} for x in s]
    return pd.DataFrame(rows)


def add_flags(df: pd.DataFrame) -> pd.DataFrame:
    df["stype"] = df["session"].map(SESSION_TYPE)
    neutralised = df["status"].str.contains("[4567]", regex=True)
    in_out = df["pit_in_time"].notna() | df["pit_out_time"].notna()
    df["neutralised"], df["in_out"] = neutralised, in_out
    dry = df["compound"].astype(str).str.upper().isin(["SOFT", "MEDIUM", "HARD"])
    df["clean"] = (df["lap_time"].notna() & ~df["deleted"] & ~df["generated"] & ~in_out & ~neutralised
                   & dry & ~((df["stype"] == "R") & (df["lap"] <= 1)))
    grp = ["year", "circuit", "session", "driver"]
    best = df[df["clean"]].groupby(grp)["lap_time"].min().rename("driver_best")
    median = df[df["clean"]].groupby(grp)["lap_time"].median().rename("driver_median")
    df = df.join(best, on=grp).join(median, on=grp)
    df["push"] = df["clean"] & df["stype"].isin(["FP", "Q"]) & (df["lap_time"] <= 1.02 * df["driver_best"])
    df["race_pace"] = df["clean"] & (df["stype"] == "R") & (df["lap_time"] <= 1.07 * df["driver_median"])
    # Fastest lap per driver per session (one-lap pace)
    idx = df[df["clean"]].groupby(grp)["lap_time"].idxmin()
    df["best_of_session"] = False
    df.loc[idx, "best_of_session"] = True
    return df


def main() -> None:
    frames = []
    for year in YEARS:
        for key in CIRCUITS:
            for session in SESSIONS:
                df = session_laps(year, key, session)
                if df is not None:
                    frames.append(df)
                    print(f"{year} {key:<10} {session:<11} {len(df):>5} laps")
    laps = add_flags(pd.concat(frames, ignore_index=True))

    # Compound C-number, team lineage and power unit
    comp = pd.read_csv(REFERENCE / "compounds.csv")
    comp = comp.melt(id_vars=["year", "circuit"], value_vars=["hard", "medium", "soft"],
                     var_name="compound", value_name="compound_c")
    comp["compound"] = comp["compound"].str.upper()
    laps["compound"] = laps["compound"].astype(str).str.upper()
    laps = laps.merge(comp, on=["year", "circuit", "compound"], how="left")
    teams = pd.read_csv(REFERENCE / "teams.csv")
    laps = laps.merge(teams, on=["year", "team"], how="left")
    missing = laps.loc[laps["pu"].isna(), "team"].unique()
    if len(missing):
        print("WARNING: teams without a PU mapping:", missing)

    # Dates and rule regime: 2026 Australia ran before the Miami energy-management change
    laps = laps.merge(session_dates(), on=["year", "circuit", "session"], how="left")
    laps["regime"] = np.where(laps["year"] == 2025, "2025",
                              np.where(laps["circuit"] == "australia", "2026 original", "2026 post-Miami"))

    PROCESSED.mkdir(parents=True, exist_ok=True)
    laps.to_parquet(PROCESSED / "laps.parquet", index=False)
    cov = laps.groupby(["year", "circuit", "stype"]).agg(laps=("lap", "size"), clean=("clean", "sum"),
                                                        push=("push", "sum"), race_pace=("race_pace", "sum"),
                                                        with_tel=("has_tel", "sum"))
    cov.to_csv(PROCESSED / "coverage.csv")
    print(cov.to_string())


if __name__ == "__main__":
    main()
