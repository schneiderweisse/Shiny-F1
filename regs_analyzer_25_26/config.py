"""Shared settings for the 2025 vs 2026 regulations analysis: circuits, sessions and paths."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

DATA = HERE / "data"            # downloaded and intermediate data (not in git)
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
REFERENCE = HERE / "reference"  # curated tables (in git)
RESULTS = HERE / "results"      # model outputs the dashboard reads (in git)

YEARS = (2025, 2026)
SESSIONS = ("Practice 1", "Practice 2", "Practice 3", "Qualifying", "Race")
SESSION_TYPE = {"Practice 1": "FP", "Practice 2": "FP", "Practice 3": "FP", "Qualifying": "Q", "Race": "R"}

# Circuit key -> event names per year (TracingInsights and OpenF1 use the same names).
# The 2026 "Spanish Grand Prix" is the new Madrid race; Barcelona ran as the "Barcelona Grand Prix".
# length_m: official lap length, used as the common distance axis for both years.
CIRCUITS = {
    "australia": {"label": "Australia", "track": "Albert Park", "f1db": "melbourne", "length_m": 5278,
                  "event": {2025: "Australian Grand Prix", 2026: "Australian Grand Prix"}},
    "monaco":    {"label": "Monaco", "track": "Monte Carlo", "f1db": "monaco", "length_m": 3337,
                  "event": {2025: "Monaco Grand Prix", 2026: "Monaco Grand Prix"}},
    "barcelona": {"label": "Barcelona", "track": "Barcelona-Catalunya", "f1db": "catalunya", "length_m": 4657,
                  "event": {2025: "Spanish Grand Prix", 2026: "Barcelona Grand Prix"}},
    "hungary":   {"label": "Hungary", "track": "Hungaroring", "f1db": "hungaroring", "length_m": 4381,
                  "event": {2025: "Hungarian Grand Prix", 2026: "Hungarian Grand Prix"}},
    "monza":     {"label": "Monza", "track": "Monza", "f1db": "monza", "length_m": 5793,
                  "event": {2025: "Italian Grand Prix", 2026: "Italian Grand Prix"}},
    "singapore": {"label": "Singapore", "track": "Marina Bay", "f1db": "marina-bay", "length_m": 4927,
                  "event": {2025: "Singapore Grand Prix", 2026: "Singapore Grand Prix"}},
    "austin":    {"label": "Austin", "track": "Circuit of the Americas", "f1db": "austin", "length_m": 5513,
                  "event": {2025: "United States Grand Prix", 2026: "United States Grand Prix"}},
}

TI_REPO = "https://github.com/TracingInsights/{year}.git"
TI_LOCAL_2026 = REPO / "TracingInsights_2026" / "2026"   # full clone made by scripts/fetch_data.R, reused if present
OPENF1_LOCAL = REPO / "OpenF1" / "meetings"              # made by scripts/fetch_data.R, reused if present
OPENF1_API = "https://api.openf1.org/v1"

GRID_STEP_M = 10.0  # distance grid for telemetry, metres

# Colours shared by the dashboard and report figures (GitHub dark palette)
YEAR_COLOUR = {2025: "#58a6ff", 2026: "#f0883e"}
