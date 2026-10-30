"""Step 1a: download the raw data for the 7 matched circuits, 2025 and 2026.

TracingInsights telemetry: a sparse partial clone that fetches only the 7 events x 5 sessions
(Practice 1-3, Qualifying, Race; no sprints, no radio audio). The 2026 full clone made by the
main branch's scripts/fetch_data.R is reused when it exists next to this folder. OpenF1 pit stops, overtakes and race control come
from the local OpenF1 folder, or from the API when it is missing.

Run from regs_analyzer_25_26/:  python -m pipeline.fetch
"""
import json
import shutil
import subprocess
import time
from pathlib import Path

import requests

from config import CIRCUITS, OPENF1_API, OPENF1_LOCAL, RAW, SESSIONS, TI_LOCAL_2026, TI_REPO, YEARS

OPENF1_ENDPOINTS = ("sessions", "drivers", "session_result", "starting_grid", "stints", "pit",
                    "race_control", "overtakes", "position", "weather")


def git(*args, cwd=None):
    subprocess.run(["git", *args], cwd=cwd, check=True)


def ti_dir(year: int) -> Path:
    """Where the TracingInsights files for a year live (local full clone or our sparse clone)."""
    if year == 2026 and (TI_LOCAL_2026 / ".git").exists():
        return TI_LOCAL_2026
    return RAW / f"ti_{year}"


def sparse_patterns(year: int) -> list[str]:
    pats = [f"/{c['event'][year]}/{s}/" for c in CIRCUITS.values() for s in SESSIONS]
    return pats + ["!*.mp3", "!/**/radio/"]


def fetch_tracinginsights(year: int) -> None:
    dest = ti_dir(year)
    if dest == TI_LOCAL_2026:
        print(f"TracingInsights {year}: using the full local clone at {dest}")
        return
    if not (dest / ".git").exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"TracingInsights {year}: partial clone (structure only)")
        git("clone", "--filter=blob:none", "--no-checkout", "--depth", "1", "--single-branch",
            TI_REPO.format(year=year), str(dest))
    # Non-cone patterns: only our events and sessions; skip team-radio audio
    patterns = sparse_patterns(year)
    git("sparse-checkout", "init", "--no-cone", cwd=dest)
    (dest / ".git" / "info" / "sparse-checkout").write_text("\n".join(patterns) + "\n", encoding="utf-8")
    print(f"TracingInsights {year}: checking out {len(patterns) - 2} event/session folders")
    git("checkout", "main", cwd=dest)
    git("sparse-checkout", "reapply", cwd=dest)


def openf1_meeting_dir(year: int, event: str) -> Path | None:
    if not OPENF1_LOCAL.exists():
        return None
    slug = event.replace(" ", "_")
    hits = sorted(OPENF1_LOCAL.glob(f"{year}_*_{slug}"))
    return hits[0] if hits else None


def fetch_openf1(year: int, key: str, event: str) -> None:
    out = RAW / "openf1" / f"{year}_{key}"
    out.mkdir(parents=True, exist_ok=True)
    local = openf1_meeting_dir(year, event)
    if local is not None:
        for ep in OPENF1_ENDPOINTS:
            if (local / f"{ep}.json").exists():
                shutil.copy2(local / f"{ep}.json", out / f"{ep}.json")
        return
    meetings = requests.get(f"{OPENF1_API}/meetings", params={"year": year}, timeout=60).json()
    mk = next(m["meeting_key"] for m in meetings if m["meeting_name"] == event)
    for ep in OPENF1_ENDPOINTS:
        r = requests.get(f"{OPENF1_API}/{ep}", params={"meeting_key": mk}, timeout=120)
        (out / f"{ep}.json").write_text(r.text if r.status_code == 200 else "[]", encoding="utf-8")
        time.sleep(2.1)  # free tier: 30 requests a minute


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for year in YEARS:
        fetch_tracinginsights(year)
        for key, c in CIRCUITS.items():
            fetch_openf1(year, key, c["event"][year])
        print(f"OpenF1 {year}: 7 meetings")
    # Record what is on disk
    summary = {}
    for year in YEARS:
        base = ti_dir(year)
        for key, c in CIRCUITS.items():
            for s in SESSIONS:
                d = base / c["event"][year] / s
                summary[f"{year}/{key}/{s}"] = sum(1 for _ in d.glob("*/*_tel.json")) if d.exists() else None
    (RAW / "coverage.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print("Per-lap telemetry files:", sum(v or 0 for v in summary.values()))


if __name__ == "__main__":
    main()
