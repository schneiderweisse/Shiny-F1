# 2025 vs 2026 regulations dashboard

**Live:** https://schneiderweisse.github.io/Shiny-F1/regs/ · **Report:** [REPORT.md](../REPORT.md)

An interactive dashboard that answers one question: **what did the 2026 Formula 1 rules change about the cars?** It compares the 2025 and 2026 cars on the seven circuits raced under both rule sets (Australia, Monaco, Barcelona, Hungary, Monza, Singapore, Austin), using practice, qualifying and race telemetry.

It is the visual companion to the statistical study in [REPORT.md](../REPORT.md). Every number on it is an estimate with an uncertainty attached, not just an average. The aim is that you can see *where* the rules show up on track and *how sure* we can be about each effect.

This is the second dashboard in the [Shiny-F1](https://github.com/schneiderweisse/Shiny-F1) repository. The first, the F1 Data Pit Wall (R/Shiny) on the `main` branch, is a general explorer of F1 history and data. This one lives on the `regs_analyzer_25_26` branch: a focused study, written in Python with Dash.

---

## What it shows

Eight tabs, styled like a GitHub repository page:

| Tab | What you can do and read |
|---|---|
| **Overview** | Ten headline findings as cards. Each shows the estimate, its 95% confidence interval and a p-value, coloured green (better in 2026), red (worse) or grey (no clear change). Below: the seven circuits with the sessions available and Pirelli's compound choices per year. |
| **Lap time** | How much slower qualifying got at each circuit (forest plot, Holm-adjusted p-values on hover). A scatter checks whether power-sensitive circuits were hit harder. A table compares pole and top-10 times. |
| **Speed trace** | Pick a circuit. Top: mean speed along the lap, 2025 vs 2026. Middle: the difference, with pointwise and simultaneous 95% bands. Bottom: the cumulative time gap. A track map colours every 10 m by where 2026 is faster or slower, and a bar chart splits the time gained or lost by straight and corner. |
| **Power & energy** | The new power-unit rule (electrical power falling above 290 km/h) next to the measured acceleration-vs-speed curves for every circuit. A within-circuit acceleration-gap chart tests that rule. Also here: top speed per straight, how often cars run out of energy and slow down at full throttle ("clipping"), the effect of the May 2026 Miami rule change, and a comparison of the five power-unit makers. |
| **Corners & lines** | Minimum corner speed and braking deceleration by corner type (slow, medium, fast), and lift-and-coast before and after the Miami change. Pick a circuit to compare each corner's minimum speed and the 2025 vs 2026 racing lines, with a measurement-noise reference. |
| **Tyres & race** | Compound choices, tyre degradation per compound, pit stops per finisher, overtakes per race and how spread out the field's race pace was. |
| **Regulations** | The 2025 and 2026 technical rules side by side with their FIA article numbers, plus a timeline of the races analysed and the rule changes during 2026. |
| **Data & methods** | Lap filters, telemetry processing, the models used, the caveats, and how many laps each session contributed and passed the telemetry quality check. |

**How to read the charts.** 2025 is always blue and 2026 orange. Dots with horizontal lines are estimates with 95% confidence intervals: if the line crosses zero, the data can't tell the effect apart from no change. Hovering any chart shows exact values. Drag to zoom, double-click to reset.

---

## How it was built

### 1. A data pipeline writes everything the dashboard needs

The dashboard never reads raw telemetry. A four-step pipeline in [`../pipeline/`](../pipeline/) does the heavy work once and writes small result tables to [`../results/`](../results/):

1. **`fetch.py`** downloads only the 35 event/session folders needed from the TracingInsights telemetry archives. It uses a sparse partial git clone, 1.2 GB instead of the full ~15 GB 2025 archive. It also collects OpenF1 race data.
2. **`build_laps.py`** builds one table of ~40,000 laps. Each lap carries its compound (C1–C6), team, power unit, rule regime (2025 / 2026 before Miami / 2026 after) and quality flags (clean lap, push lap, race-pace lap).
3. **`features.py`** resamples every clean lap's telemetry onto a common 10 m grid along the track. A quality check cross-correlates each lap with a reference lap and drops misaligned laps; this is how the broken 2026 Hungarian GP race data was caught. It then cuts each circuit into straights and corner zones, and measures top speed, clipping, braking, minimum speed and lift-and-coast on every lap.
4. **`stats.py`** fits the statistical models: mixed models, bootstrap confidence bands, GEE, difference-in-differences and others. It writes tidy tables plus `summary.json` with the headline estimates.

Because `results/` is committed to the repository, the dashboard (and the GitHub Pages build) runs without downloading any data.

### 2. The app: Dash, Plotly and a small design system

| File | Role |
|---|---|
| [`app.py`](app.py) | The Dash app. Small layout helpers (`box`, `finding`, `table`, `pill`) build GitHub-style components. One function per tab returns its layout (`PAGES`). The `DYNAMIC` table maps each dropdown to the charts it controls, and the app's callbacks are generated from it. |
| [`figures.py`](figures.py) | Every chart, one function each (forest plots, speed traces with bands, track maps, dumbbells and others), built with Plotly from the result tables. |
| [`theme.py`](theme.py) | A Plotly template (`github_dark`) and the shared colours, so every chart matches the page. |
| [`data.py`](data.py) | Loads `results/` and the curated tables in `reference/` once, at startup. |
| [`assets/github.css`](assets/github.css) | The page style. Dash serves the `assets/` folder automatically. |

**Design.** The look follows GitHub's own dark theme (the *Primer* design system):
- **Colours:** background `#0d1117`, borders `#30363d`, text `#e6edf3`, links `#4493f8`.
- **Components:** content in bordered *boxes* with a grey header strip, the *underline navigation* for tabs, and *labels* (pills) for p-values.
- **Fonts:** the system font stack, with monospaced numbers so columns line up.
- **Meaning colours:** green, red and grey carry the result ("better", "worse", "not distinguishable"); blue and orange only mean 2025 and 2026.

**Statistics conventions.** Wherever there is an estimate, there is an interval:
- Lap-time and corner effects come from models with team-era effects, so a team's form doesn't masquerade as a rule effect.
- Speed traces carry *simultaneous* bootstrap bands, valid for the whole lap at once.
- Per-circuit tests are Holm-corrected.

The models are explained in [REPORT.md](../REPORT.md#4-statistical-methods).

### 3. Hosting on GitHub Pages: a static export

GitHub Pages only serves static files, while a Dash app normally needs a Python server running. Every chart here is precomputed, though, so [`export_static.py`](export_static.py) renders the dashboard ahead of time:

1. It walks the **same** page functions the live app uses (`app.PAGES`) and writes them out as plain HTML.
2. It saves every chart as JSON, one file per tab. For dropdowns, it pre-renders the charts for every option, using the same `DYNAMIC` table as the live callbacks, so the two versions can't drift apart.
3. It adds ~30 lines of JavaScript to switch tabs (with linkable URLs such as `#speed`) and dropdown options, and copies the `plotly.js` that ships with Python's plotly, so charts render exactly as in the live app.

The export is about 6 MB, of which 4.8 MB is plotly.js. GitHub Pages publishes from `main`, whose Pages workflow ([`pages.yml` on main](https://github.com/schneiderweisse/Shiny-F1/blob/main/.github/workflows/pages.yml)) builds the Shiny app at the site root. It then checks out this branch and runs the export into **`/regs/`**. A push to this branch triggers that workflow through [`refresh-pages.yml`](../../.github/workflows/refresh-pages.yml), so the published dashboard follows this branch.

---

## Run it on your computer

The live app (`app.py`) needs Python 3.10 or newer. From the `regs_analyzer_25_26` folder:

```bash
py -3.11 -m venv .venv
```

```bash
./.venv/Scripts/python.exe -m pip install -r requirements.txt
```

```bash
./.venv/Scripts/python.exe dashboard/app.py
```

Then open http://127.0.0.1:8050 and stop it with **Ctrl+C**. On macOS or Linux, use `python3 -m venv .venv` and `.venv/bin/python`.

- **VS Code:** open the `regs_analyzer_25_26` folder and pick the `.venv` interpreter (**Python: Select Interpreter**). Then open `dashboard/app.py` and click **Run Python File**.
- **RStudio:** open [`../run_dashboard.R`](../run_dashboard.R) and click **Source**. It creates the Python environment on first use, starts the app in the background, picks another port if 8050 is busy, and shows the app in the Viewer pane. `stop_dashboard()` stops it.

To build the static version yourself and preview it:

```bash
./.venv/Scripts/python.exe dashboard/export_static.py data/static_site
```

```bash
./.venv/Scripts/python.exe -m http.server 8060 --directory data/static_site
```

Then open http://127.0.0.1:8060.

## Change or extend it

- **New results:** rerun the pipeline (`python -m pipeline.stats` after the earlier steps), then push to `main`. The Pages site rebuilds itself.
- **New tab:** write a `page_...()` function in `app.py` and add it to `PAGES`. The static export picks it up automatically.
- **New dropdown chart:** add the dropdown to a page and an entry in `DYNAMIC` (dropdown id → chart ids and a function returning one figure per chart). It then works in both the live and the static versions.
- **New component type:** if you use a Dash component the exporter doesn't know yet, `export_static.py` stops with *"No static renderer for …"*. Add a branch for it in `render()`.
