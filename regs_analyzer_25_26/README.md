# regs_analyzer_25_26

How the 2026 Formula 1 regulations changed the cars, measured on the seven circuits raced under both the 2025 and 2026 rules: Australia, Monaco, Barcelona, Hungary, Monza, Singapore and Austin. Practice, qualifying and race sessions only (no sprints).

- **Write-up:** [REPORT.md](REPORT.md): data, methods, results and limitations
- **Dashboard:** a GitHub-styled dark Dash app with eight tabs (overview, lap time, speed trace, power & energy, corners & lines, tyres & race, regulations, data & methods)
  - Live: https://schneiderweisse.github.io/Shiny-F1/regs/
  - What it shows and how it was built: [dashboard/README.md](dashboard/README.md)

## Headline results

| | 2026 vs 2025 |
|---|---|
| Qualifying lap time | +3.97% (95% CI 3.03–4.92) |
| Top speed | −7.9 km/h on average |
| Acceleration, ≥ 290 km/h vs below | −0.57 m/s² (rule C5.2.8 power taper) |
| Straights with clipping (qualifying) | 3.8% → 29.1% |
| Minimum speed, fast corners | −20.1 km/h |
| Lift-and-coast in qualifying | +107 m/lap before the Miami change, +1 m/lap after |

## Run the dashboard

The `results/` folder is in the repo, so the dashboard runs without downloading any data:

```bash
cd regs_analyzer_25_26
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python dashboard\app.py
```

Then open http://127.0.0.1:8050. On macOS or Linux use `python3 -m venv .venv` and `.venv/bin/python`.

From RStudio, open [run_dashboard.R](run_dashboard.R) and click **Source**. It sets up the Python environment on first use and shows the app in the Viewer pane.

## Rebuild everything from the sources

```bash
.venv\Scripts\python -m pipeline.fetch        # TracingInsights 2025 (sparse clone, ~1.2 GB) and 2026, OpenF1
.venv\Scripts\python -m pipeline.build_laps
.venv\Scripts\python -m pipeline.features
.venv\Scripts\python -m pipeline.stats
.venv\Scripts\python report\make_figures.py
```

If the full 2026 telemetry clone made by `scripts/fetch_data.R` exists (`../TracingInsights_2026/2026`), `pipeline.fetch` reuses it. Otherwise it sparse-clones 2026 as well.

## Layout

```
config.py              circuits, sessions, paths
pipeline/
  fetch.py             downloads (sparse git clone, OpenF1)
  build_laps.py        lap table: compounds, teams, PUs, rule regime, lap filters
  features.py          10 m grids, telemetry quality check, segment maps, features
  stats.py             all models -> results/ and results/models/
reference/             curated tables with sources: compounds, regulations, rule changes, teams
results/               model outputs read by the dashboard
dashboard/             Dash app (app.py, figures.py, theme.py, assets/github.css) and export_static.py for GitHub Pages
report/                figure script and figures for REPORT.md
run_dashboard.R        starts the dashboard from RStudio
data/                  downloaded and intermediate data (not in git)
```

## Data sources

TracingInsights (telemetry, Apache-2.0), OpenF1 (CC BY-NC-SA 4.0), F1DB (CC BY 4.0), Pirelli and F1.com (compound choices), FIA (regulations). This is an unofficial analysis, not associated with Formula 1 or the FIA.
