"""Loads the result tables written by pipeline/stats.py and the curated reference tables."""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config import CIRCUITS, RESULTS, REFERENCE  # noqa: E402

LABEL = {k: v["label"] for k, v in CIRCUITS.items()}
ORDER = list(CIRCUITS)  # calendar order


def _csv(name):
    p = RESULTS / f"{name}.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


def _parquet(name):
    p = RESULTS / f"{name}.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


R = {name: _csv(name) for name in [
    "coverage", "pace_qualifying_desc", "pace_qualifying_effects", "segment_time_delta", "accel_speed_curve",
    "straights_summary", "straights_topspeed_delta", "lift_coast_summary", "lift_coast_by_corner", "corner_effects",
    "corners_summary", "racing_line_offsets", "tyre_degradation", "race_stops", "race_stints", "racing_summary",
    "race_pace_by_driver", "power_unit_effects", "segments", "corners_xy", "accel_speed_delta", "clipping_share_by_circuit"]}
R["speed_profiles"] = _parquet("speed_profiles")
R["racing_lines"] = _parquet("racing_lines")
SUMMARY = json.loads((RESULTS / "summary.json").read_text(encoding="utf-8")) if (RESULTS / "summary.json").exists() else {}

REF = {name: pd.read_csv(REFERENCE / f"{name}.csv") for name in ["compounds", "regulations", "rule_changes", "teams"]}
MODEL_DIR = RESULTS / "models"
