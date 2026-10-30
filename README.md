# regs_analyzer_25_26: how the 2026 rules changed F1 cars

> This branch holds the **2025 vs 2026 regulations study**: a Python data pipeline, statistical analysis and Dash dashboard. The F1 Data Pit Wall Shiny app lives on the [`main` branch](https://github.com/schneiderweisse/Shiny-F1/tree/main).

The 2026 Formula 1 rules brought a new power unit (no MGU-H; a 350 kW electric motor whose power fades above 290 km/h), active aerodynamics, lighter and shorter cars, and narrower tyres. This study measures what that did on track. It compares the 2025 and 2026 cars on the seven circuits raced under both rule sets (Australia, Monaco, Barcelona, Hungary, Monza, Singapore and Austin), using practice, qualifying and race telemetry.

- **Dashboard (live):** https://schneiderweisse.github.io/Shiny-F1/regs/
- **Report:** [REPORT.md](regs_analyzer_25_26/REPORT.md): data, methods, results and limitations
- **How the dashboard works and was built:** [dashboard/README.md](regs_analyzer_25_26/dashboard/README.md)

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

Everything lives in the [`regs_analyzer_25_26/`](regs_analyzer_25_26/) folder. Its `results/` are committed, so the dashboard runs without downloading any data. You need Python 3.10 or newer.

```bash
cd regs_analyzer_25_26
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python dashboard\app.py
```

Then open http://127.0.0.1:8050. On macOS or Linux use `python3 -m venv .venv` and `.venv/bin/python`.

- **VS Code:** open the `regs_analyzer_25_26` folder, pick the `.venv` interpreter (**Python: Select Interpreter**), open `dashboard/app.py` and click **Run Python File**.
- **RStudio:** open [`regs_analyzer_25_26/run_dashboard.R`](regs_analyzer_25_26/run_dashboard.R) and click **Source**. It sets up the Python environment on first use and shows the app in the Viewer pane.

## Rebuild everything from the sources

From `regs_analyzer_25_26/`:

```bash
.venv\Scripts\python -m pipeline.fetch        # TracingInsights 2025 (sparse clone, ~1.2 GB) and 2026, OpenF1
.venv\Scripts\python -m pipeline.build_laps
.venv\Scripts\python -m pipeline.features
.venv\Scripts\python -m pipeline.stats
.venv\Scripts\python report\make_figures.py
```

If the full 2026 telemetry clone made by the `main` branch's `scripts/fetch_data.R` sits next to this folder (`../TracingInsights_2026/2026`), `pipeline.fetch` reuses it. Otherwise it sparse-clones 2026 as well.

## Layout

```
regs_analyzer_25_26/
  config.py              circuits, sessions, paths
  pipeline/
    fetch.py             downloads (sparse git clone, OpenF1)
    build_laps.py        lap table: compounds, teams, PUs, rule regime, lap filters
    features.py          10 m grids, telemetry quality check, segment maps, features
    stats.py             all models -> results/ and results/models/
  reference/             curated tables with sources: compounds, regulations, rule changes, teams
  results/               model outputs read by the dashboard
  dashboard/             Dash app (app.py, figures.py, theme.py, assets/github.css)
                         and export_static.py, the static export for GitHub Pages
  report/                figure script and figures for REPORT.md
  run_dashboard.R        starts the dashboard from RStudio
  data/                  downloaded and intermediate data (not in git)
.github/workflows/
  refresh-pages.yml      after a push here, rebuilds the GitHub Pages site on main
```

## How it's published

GitHub Pages serves the whole repository from `main`. The Pages workflow on `main` builds the Shiny app at the site root, then checks out this branch and runs `dashboard/export_static.py` to put the static version of this dashboard under `/regs/`. A push to this branch triggers that workflow (`refresh-pages.yml`), so the published dashboard follows this branch.

## Data sources

TracingInsights (telemetry, Apache-2.0), OpenF1 (CC BY-NC-SA 4.0), F1DB (CC BY 4.0), Pirelli and F1.com (compound choices), FIA (regulations). This is an unofficial analysis, not associated with Formula 1 or the FIA.
