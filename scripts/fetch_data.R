#!/usr/bin/env Rscript
# Downloads every data source the dashboard uses, recreating this layout next to dashboard/:
#
#   F1DB/                       full history, 1950 to now (CSV, JSON, SQLite)          ~25 MB
#   Jolpica/                    Ergast-format dump with lap times and pit stops (CSV, SQL)  ~90 MB
#   OpenF1/meetings/            every session since 2023, one folder per meeting (JSON)   ~500 MB, ~1 hour
#   TracingInsights_2026/2026/  per-lap car telemetry for 2026 (git clone, needs git)      ~16 GB
#   f1-circuits/                circuit outlines (GeoJSON)
#   TUMFTM_racetrack-database/  track widths and racing lines (CSV)
#   FIA_documents/              latest FIA F1 regulations (PDF)
#
# Usage (from the repo folder):
#   Rscript scripts/fetch_data.R                       everything
#   Rscript scripts/fetch_data.R --skip=telemetry      everything except the 16 GB telemetry repo
#   Rscript scripts/fetch_data.R --only=f1db,jolpica   just some sources
#   Rscript scripts/fetch_data.R --dest=D:/f1          somewhere else (then set F1_DATA_ROOT for the app)
#
# Re-running updates in place: F1DB and Jolpica are replaced by the newest release, OpenF1 only fetches
# meetings it does not have yet, and the git repos are pulled.
#
# Sources: names = f1db, jolpica, openf1, telemetry, circuits, tum, fia

ALL <- c("f1db", "jolpica", "openf1", "telemetry", "circuits", "tum", "fia")

args <- commandArgs(trailingOnly = TRUE)
arg <- function(name) {
  a <- grep(paste0("^--", name, "="), args, value = TRUE)
  if (length(a)) sub(paste0("^--", name, "="), "", a[1]) else NULL
}
script_dir <- dirname(normalizePath(sub("^--file=", "", grep("^--file=", commandArgs(), value = TRUE)[1]), winslash = "/"))
source(file.path(script_dir, "sources.R"))

DEST <- normalizePath(arg("dest") %||% file.path(script_dir, ".."), winslash = "/", mustWork = FALSE)
only <- if (!is.null(arg("only"))) strsplit(arg("only"), ",")[[1]] else ALL
skip <- if (!is.null(arg("skip"))) strsplit(arg("skip"), ",")[[1]] else character()
todo <- setdiff(intersect(ALL, only), skip)
dir.create(DEST, showWarnings = FALSE, recursive = TRUE)

say <- function(...) cat(format(Sys.time(), "%H:%M:%S"), ..., "\n")
d <- function(...) file.path(DEST, ...)
fresh_dir <- function(p) { unlink(p, recursive = TRUE); dir.create(p, recursive = TRUE, showWarnings = FALSE); p }

download_to <- function(url, dest) {
  dir.create(dirname(dest), recursive = TRUE, showWarnings = FALSE)
  r <- http_get(url, dest)
  if (is.null(r$path)) stop("Download failed: ", url, "\n  ", r$error)
  dest
}

has_git <- nzchar(Sys.which("git"))

# Shallow-clone a GitHub repo, or pull it if it is already there; zip download when git is missing.
github_repo <- function(repo, branch, dest) {
  if (has_git) {
    if (dir.exists(file.path(dest, ".git"))) {
      system2("git", c("-C", shQuote(dest), "pull", "--ff-only", "--quiet"))
    } else {
      dir.create(dirname(dest), recursive = TRUE, showWarnings = FALSE)
      system2("git", c("clone", "--depth", "1", "--single-branch", "--branch", branch, "--quiet",
                       sprintf("https://github.com/%s.git", repo), shQuote(dest)))
    }
  } else {
    z <- download_to(sprintf("https://github.com/%s/archive/refs/heads/%s.zip", repo, branch), tempfile(fileext = ".zip"))
    tmp <- tempfile()
    utils::unzip(z, exdir = tmp)
    unlink(dest, recursive = TRUE)
    dir.create(dirname(dest), recursive = TRUE, showWarnings = FALSE)
    file.rename(list.dirs(tmp, recursive = FALSE)[1], dest)
  }
}

# ---------- F1DB ----------
fetch_f1db <- function() {
  rel <- get_json("https://api.github.com/repos/f1db/f1db/releases/latest")
  if (is.null(rel)) stop("Could not read the latest F1DB release")
  say("F1DB", rel$tag_name)
  base <- sprintf("https://github.com/f1db/f1db/releases/download/%s", rel$tag_name)
  files <- c("f1db-csv.zip", "f1db-json-single.zip", "f1db-sqlite.zip", "checksums_sha256.txt")
  for (f in files) download_to(file.path(base, f), d("F1DB", "downloads", f))
  sums <- readLines(d("F1DB", "downloads", "checksums_sha256.txt"))
  for (f in files[1:3]) {
    expected <- sub("\\s.*$", "", grep(paste0("[ *]", f, "$"), sums, value = TRUE)[1])
    ok <- sha256_ok(d("F1DB", "downloads", f), expected)
    if (isFALSE(ok)) stop("Checksum mismatch for ", f)
  }
  utils::unzip(d("F1DB", "downloads", "f1db-csv.zip"), exdir = fresh_dir(d("F1DB", "csv")))
  utils::unzip(d("F1DB", "downloads", "f1db-json-single.zip"), exdir = fresh_dir(d("F1DB", "json")))
  utils::unzip(d("F1DB", "downloads", "f1db-sqlite.zip"), exdir = fresh_dir(d("F1DB", "sqlite")))
  writeLines(rel$tag_name, d("F1DB", "VERSION"))
}

# ---------- Jolpica ----------
fetch_jolpica <- function() {
  info <- get_json("https://api.jolpi.ca/data/dumps/download/")
  if (is.null(info)) stop("Could not read the Jolpica dump list")
  dir.create(d("Jolpica", "downloads"), recursive = TRUE, showWarnings = FALSE)
  writeLines(jsonlite::toJSON(info, auto_unbox = TRUE, pretty = TRUE), d("Jolpica", "downloads", "dumps_info.json"))
  # Free dumps are the "delayed" ones (14 days behind)
  for (type in c("csv", "sql")) {
    dump <- info$delayed_dumps[[type]]
    f <- d("Jolpica", "downloads", sprintf("jolpica-%s-%s.zip", type, substr(dump$uploaded_at, 1, 10)))
    if (!file.exists(f)) download_to(dump$download_url, f)
    if (isFALSE(sha256_ok(f, dump$file_hash))) stop("Checksum mismatch for ", basename(f))
    utils::unzip(f, exdir = fresh_dir(d("Jolpica", type)))
  }
  say("Jolpica dump from", substr(info$delayed_dumps$csv$uploaded_at, 1, 10))

  # Top up races run after the dump through the API
  dump_date <- as.Date(substr(info$delayed_dumps$csv$uploaded_at, 1, 10))
  yr <- as.integer(format(Sys.Date(), "%Y"))
  races <- get_json(sprintf("https://api.jolpi.ca/ergast/f1/%d/races/?limit=100", yr))$MRData$RaceTable$Races
  if (is.null(races) || !length(races)) return(invisible())
  races <- races[as.Date(races$date) >= dump_date - 2 & as.Date(races$date) < Sys.Date(), , drop = FALSE]
  for (i in seq_len(nrow(races))) {
    rd <- as.integer(races$round[i])
    out <- d("Jolpica", sprintf("api_%d_round%02d", yr, rd))
    dir.create(out, recursive = TRUE, showWarnings = FALSE)
    base <- sprintf("https://api.jolpi.ca/ergast/f1/%d/%d", yr, rd)
    download_to(paste0(base, "/"), file.path(out, "race.json"))
    for (e in c("results", "qualifying", "sprint", "pitstops", "driverStandings", "constructorStandings")) {
      http_get(sprintf("%s/%s/?limit=100", base, e), file.path(out, paste0(e, ".json")))
      Sys.sleep(0.5)
    }
    off <- 0
    repeat {
      f <- file.path(out, sprintf("laps_offset_%04d.json", off))
      http_get(sprintf("%s/laps/?limit=100&offset=%d", base, off), f)
      total <- tryCatch(as.integer(jsonlite::fromJSON(f)$MRData$total), error = function(e) 0L)
      off <- off + 100
      Sys.sleep(0.5)
      if (off >= total) break
    }
    say("Jolpica top-up:", races$raceName[i])
  }
}

# ---------- OpenF1 ----------
fetch_openf1 <- function() {
  base <- "https://api.openf1.org/v1"
  endpoints <- c("drivers", "sessions", "session_result", "starting_grid", "laps", "stints", "pit",
                 "weather", "race_control", "team_radio", "overtakes", "intervals", "position",
                 "championship_drivers", "championship_teams")
  root <- d("OpenF1")
  dir.create(file.path(root, "meetings"), recursive = TRUE, showWarnings = FALSE)
  log_file <- file.path(root, "download_log.txt")
  log <- function(msg) { say("OpenF1", msg); cat(format(Sys.time(), "%Y-%m-%dT%H:%M:%S"), msg, "\n", file = log_file, append = TRUE) }

  # Free tier: 30 requests a minute
  gap <- function() Sys.sleep(2.1)
  fetch_ep <- function(url, dest) {
    for (attempt in 1:5) {
      r <- http_get(url, dest)
      if (!is.null(r$path)) return(TRUE)
      if (grepl("404", r$error)) { writeLines("[]", dest); return(TRUE) }   # no data for this meeting
      if (grepl("429", r$error)) { log("rate limited, waiting 65 s"); Sys.sleep(65); next }
      log(paste("retry", attempt, url, r$error)); Sys.sleep(10)
    }
    FALSE
  }

  fetch_ep(paste0(base, "/meetings"), file.path(root, "meetings.json")); gap()
  fetch_ep(paste0(base, "/sessions"), file.path(root, "sessions_all.json")); gap()
  m <- jsonlite::fromJSON(file.path(root, "meetings.json"))
  m <- m[!m$is_cancelled & as.POSIXct(substr(m$date_end, 1, 19), format = "%Y-%m-%dT%H:%M:%S", tz = "UTC") < Sys.time(), ]
  m <- m[order(m$date_start), ]
  slug <- function(s) gsub("^_|_$", "", gsub("[^A-Za-z0-9]+", "_", iconv(s, to = "ASCII//TRANSLIT")))
  m$folder <- sprintf("%d_%s_%s", m$year, substr(m$date_start, 6, 10), slug(m$meeting_name))
  log(paste(nrow(m), "past meetings"))

  for (i in seq_len(nrow(m))) {
    dir <- file.path(root, "meetings", m$folder[i])
    dir.create(dir, showWarnings = FALSE)
    writeLines(jsonlite::toJSON(as.list(m[i, setdiff(names(m), "folder")]), auto_unbox = TRUE, pretty = TRUE),
               file.path(dir, "meeting.json"))
    missing <- endpoints[!file.exists(file.path(dir, paste0(endpoints, ".json")))]
    for (ep in missing) {
      fetch_ep(sprintf("%s/%s?meeting_key=%d", base, ep, m$meeting_key[i]), file.path(dir, paste0(ep, ".json")))
      gap()
    }
    if (length(missing)) log(paste("done", m$folder[i]))
  }
  utils::write.csv(data.frame(year = m$year, meeting_key = m$meeting_key, meeting_name = m$meeting_name,
                              location = m$location, date_start = m$date_start, folder = m$folder),
                   file.path(root, "meetings_index.csv"), row.names = FALSE)
}

# ---------- TracingInsights telemetry ----------
fetch_telemetry <- function() {
  if (!has_git) stop("The telemetry repo is ~4.5 GB; install git to fetch it")
  say("TracingInsights 2026: cloning or pulling (several GB, this takes a while)")
  github_repo("TracingInsights/2026", "main", d("TracingInsights_2026", "2026"))
}

# ---------- Circuits and racing lines ----------
fetch_circuits <- function() { say("f1-circuits"); github_repo("bacinger/f1-circuits", "master", d("f1-circuits", "f1-circuits")) }
fetch_tum <- function() { say("TUM racetrack database"); github_repo("TUMFTM/racetrack-database", "master", d("TUMFTM_racetrack-database", "racetrack-database")) }

# ---------- FIA regulations ----------
fetch_fia <- function() {
  regs <- fia_latest_regulations()
  for (i in seq_len(nrow(regs))) {
    f <- d("FIA_documents", sprintf("%d_regulations", regs$year[i]), regs$file[i])
    if (!file.exists(f)) { download_to(regs$url[i], f); Sys.sleep(1) }
  }
  say("FIA:", nrow(regs), "regulation documents")
}

say("Fetching", paste(todo, collapse = ", "), "into", DEST)
for (s in todo) {
  t0 <- Sys.time()
  res <- tryCatch({ get(paste0("fetch_", s))(); "ok" }, error = function(e) conditionMessage(e))
  say(sprintf("%-10s %s (%.0f s)", s, res, as.numeric(difftime(Sys.time(), t0, units = "secs"))))
}
