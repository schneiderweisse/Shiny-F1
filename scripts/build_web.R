#!/usr/bin/env Rscript
# Builds the GitHub Pages edition of the dashboard into site/:
#   1. packs the small tables the app needs into dashboard/webdata/bundle.rds
#      (F1DB history, the Jolpica race list, circuit outlines, TUM racing lines,
#       the TracingInsights event index and links to the latest FIA regulations)
#   2. exports the app with shinylive, so R runs in the visitor's browser through webR
#
# Needs these on disk first:  Rscript scripts/fetch_data.R --only=f1db,jolpica,circuits,tum
# In the browser, Race Replay (Jolpica), Timing Screen (OpenF1) and Telemetry (TracingInsights)
# fetch their data live from the public APIs.
#
# Usage: Rscript scripts/build_web.R            then serve site/ with any static web server

script_dir <- dirname(normalizePath(sub("^--file=", "", grep("^--file=", commandArgs(), value = TRUE)[1]), winslash = "/"))
source(file.path(script_dir, "sources.R"))
root <- normalizePath(file.path(script_dir, ".."), winslash = "/")
app_dir <- file.path(root, "dashboard")
say <- function(...) cat(format(Sys.time(), "%H:%M:%S"), ..., "\n")

# Load the local tables exactly as the app does in local mode
Sys.setenv(F1_DATA_ROOT = root, F1_WEB_MODE = "0")
app <- new.env()
sys.source(file.path(app_dir, "R", "data.R"), envir = app)
say("Loaded F1DB, Jolpica, circuits and TUM tables")

say("Listing TracingInsights sessions on GitHub")
ti_index <- if (nrow(app$TI_INDEX)) app$TI_INDEX else ti_index_github()

say("Listing the latest FIA regulations")
fia <- tryCatch(fia_latest_regulations(), error = function(e) { message("FIA list skipped: ", conditionMessage(e)); NULL })

bundle <- list(
  DB        = app$DB,
  jol_races = app$JOL_RACES[, .(key = paste(year, number, sep = "/"), year, number, name, date)],
  stats     = app$STATS,
  circuits  = app$CIRCUITS,
  tum       = sapply(app$TUM_TRACKS, app$tum_track, simplify = FALSE),
  ti_index  = ti_index,
  fia       = if (is.null(fia)) character() else setNames(fia$url, fia$label)
)
dir.create(file.path(app_dir, "webdata"), showWarnings = FALSE)
out <- file.path(app_dir, "webdata", "bundle.rds")
saveRDS(bundle, out, compress = "xz")
say(sprintf("Wrote %s (%.1f MB)", out, file.size(out) / 1e6))

say("Exporting with shinylive")
site <- file.path(root, "site")
unlink(site, recursive = TRUE)
shinylive::export(app_dir, site)
say("Done: serve", site, "with a static web server, e.g. httpuv::runStaticServer('site')")
