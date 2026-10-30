# F1 Data Pit Wall

A Shiny dashboard for Formula 1 data, styled like 2000s F1 TV graphics. It brings together seven open data sources: 77 seasons of results, lap-by-lap race charts, live-timing feeds since 2023, 2026 car telemetry, circuit maps and the FIA rulebook.

**Try it in your browser:** https://schneiderweisse.github.io/Shiny-F1/

> **Also in this repository:** the 2025 vs 2026 regulations study (Python, Dash) lives on the [`regs_analyzer_25_26` branch](https://github.com/schneiderweisse/Shiny-F1/tree/regs_analyzer_25_26). Its dashboard is published at https://schneiderweisse.github.io/Shiny-F1/regs/.

## What's inside

| Tab | Data | What it shows |
|---|---|---|
| Pit Wall | all | Intro, headline numbers and what each source holds |
| Hall of Fame | F1DB | The championship battle round by round for any season since 1950, standings, all-time driver leaders |
| Engine Room | F1DB | Engine layouts on the grid over time, wins by engine maker, the tyre wars, constructor leaders |
| Race Replay | Jolpica | Lap chart, lap times, pit stops and classification for any race since 1996 |
| Timing Screen | OpenF1 | Tyre strategy, lap times, running order, result, weather, team radio and race control for any session since 2023 |
| Telemetry | TracingInsights | Two laps compared over distance (gap, speed, throttle, brake, gear, RPM), a track map coloured by the faster driver in each mini-sector, lap times |
| Circuits | f1-circuits, TUM, F1DB | World map of circuit outlines with the winners at each circuit, and minimum-curvature racing lines |
| Rulebook | FIA | The current F1 regulations (sections A to F) and next season's drafts |

## Two ways to run it

### In the browser (GitHub Pages)

The [web edition](https://schneiderweisse.github.io/Shiny-F1/) runs the same app with [Shinylive](https://posit-dev.github.io/r-shinylive/): R runs inside your browser through WebAssembly, so nothing needs installing. The first load downloads R and its packages and takes a minute or so. Race Replay, Timing Screen and Telemetry fetch their data live from the Jolpica, OpenF1 and TracingInsights APIs, so each new selection takes a few seconds.

A GitHub Actions workflow ([.github/workflows/pages.yml](.github/workflows/pages.yml)) rebuilds the site on every push and every Monday, so new races show up on their own. The same workflow also publishes the regulations study's dashboard from its branch under `/regs/`.

### On your computer (full data, offline)

You need R (4.3 or newer) and git.

1. Clone the repo and install the packages:

   ```bash
   git clone https://github.com/schneiderweisse/Shiny-F1.git
   cd Shiny-F1
   Rscript -e "install.packages(c('shiny','bslib','data.table','jsonlite','plotly','leaflet','DT','htmltools','openssl'))"
   ```

2. Download the data. This creates one folder per source next to `dashboard/`:

   ```bash
   Rscript scripts/fetch_data.R
   ```

   | Folder | Source | Size | Time |
   |---|---|---|---|
   | `F1DB/` | [F1DB](https://github.com/f1db/f1db) latest release (CSV, JSON, SQLite) | ~200 MB | 10 s |
   | `Jolpica/` | [Jolpica F1](https://github.com/jolpica/jolpica-f1) database dump (CSV, SQL), topped up with races since the dump | ~110 MB | 1 min |
   | `OpenF1/meetings/` | [OpenF1](https://openf1.org) every meeting since 2023 (JSON) | ~500 MB | ~1 hour (API limit of 30 requests a minute) |
   | `TracingInsights_2026/` | [TracingInsights 2026](https://github.com/TracingInsights/2026) per-lap telemetry (git clone) | ~16 GB | 10+ min |
   | `f1-circuits/` | [bacinger/f1-circuits](https://github.com/bacinger/f1-circuits) (GeoJSON) | 1 MB | seconds |
   | `TUMFTM_racetrack-database/` | [TUM racetrack database](https://github.com/TUMFTM/racetrack-database) (CSV) | 23 MB | seconds |
   | `FIA_documents/` | [FIA regulations](https://www.fia.com/regulation/category/110), latest issue of each section (PDF) | ~17 MB | 20 s |

   Pick sources with `--only` or leave some out with `--skip`, for example `Rscript scripts/fetch_data.R --skip=telemetry` to avoid the 16 GB download. Run the script again whenever you want new races: it updates what is there and only fetches what is missing.

3. Start the dashboard:

   ```bash
   Rscript -e "shiny::runApp('dashboard', launch.browser = TRUE)"
   ```

   Or open `dashboard/app.R` in RStudio and click **Run App**. To keep the data somewhere else, pass `--dest=PATH` to the fetch script and set the `F1_DATA_ROOT` environment variable to that path.

## Building the web edition yourself

```bash
Rscript scripts/fetch_data.R --only=f1db,jolpica,circuits,tum
Rscript scripts/build_web.R
Rscript -e "httpuv::runStaticServer('site')"
```

`build_web.R` packs the small tables into `dashboard/webdata/bundle.rds` and exports the app to `site/` with the `shinylive` package. In R, `Sys.setenv(F1_WEB_MODE = "1")` before `runApp` makes the normal app behave like the web edition.

## Repo layout

```
dashboard/
  app.R            UI and server: the eight tabs
  R/data.R         loads the data (local folders, or bundle + live APIs on the web)
  R/plots.R        chart styling and builders (telemetry trace, track map, leaderboards)
  www/pitwall.css  the 2000s TV-graphics theme
scripts/
  fetch_data.R     downloads every source into the folder layout above
  build_web.R      builds the Shinylive site for GitHub Pages
  sources.R        shared download helpers
.github/workflows/pages.yml
```

## Data sources and licences

The data is not stored in this repo; the scripts download it from the sources, each under its own terms.

| Source | Licence |
|---|---|
| [F1DB](https://github.com/f1db/f1db) | CC BY 4.0 |
| [Jolpica F1](https://github.com/jolpica/jolpica-f1) | CC BY-NC-SA 4.0 (non-commercial) |
| [OpenF1](https://openf1.org) | CC BY-NC-SA 4.0 (non-commercial) |
| [TracingInsights](https://github.com/TracingInsights/2026) | Apache-2.0 |
| [f1-circuits](https://github.com/bacinger/f1-circuits) | MIT |
| [TUM racetrack database](https://github.com/TUMFTM/racetrack-database) | LGPL-3.0 |
| [FIA regulations](https://www.fia.com/regulation/category/110) | © FIA |
| Map tiles | © Esri |

This is an unofficial fan project. It is not associated with Formula 1, the FIA or any team. F1, Formula 1 and related marks belong to Formula One Licensing B.V.
