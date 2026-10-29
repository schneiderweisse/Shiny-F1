# Data loading for the F1 Data Pit Wall. Shiny sources this file automatically (R/ folder).
#
# Two modes, same functions and table shapes:
#   local  reads the folders made by scripts/fetch_data.R, one level above the app (or F1_DATA_ROOT).
#   web    the GitHub Pages build, running in the browser through Shinylive/webR. Small tables come from
#          webdata/bundle.rds (made by scripts/build_web.R); OpenF1, Jolpica and TracingInsights are
#          fetched live from their public APIs. Set F1_WEB_MODE=1 to try web mode in normal R.

# jsonlite is used as jsonlite:: only; attaching it would mask shiny::validate
suppressPackageStartupMessages({
  library(shiny)
  library(bslib)
  library(data.table)
  library(plotly)
  library(leaflet)
  library(DT)
  library(htmltools)
})

IS_WEB <- grepl("emscripten", R.version$platform) || identical(Sys.getenv("F1_WEB_MODE"), "1")

OF1_API <- "https://api.openf1.org/v1"
JOL_API <- "https://api.jolpi.ca/ergast/f1"
TI_RAW  <- "https://raw.githubusercontent.com/TracingInsights/2026/main"

# ---------- Shared helpers ----------

TYRE_COL <- c(SOFT = "#ff2a2a", MEDIUM = "#ffd200", HARD = "#f2f2f2",
              INTERMEDIATE = "#2fb84a", WET = "#2a7fff", UNKNOWN = "#7b828c")
PAL <- c("#e10600", "#ffd200", "#d9dde3", "#2a7fff", "#2fb84a", "#ff7a00", "#b04cff",
         "#00c2c7", "#ff4f9a", "#8d95a1", "#c08a4a", "#9be22d", "#6a7cff", "#ffa3a3")
PODIUM <- c("#ffd200", "#d9dde3", "#c8803e")
SESSION_ORDER <- c("Practice 1", "Practice 2", "Practice 3", "Sprint Qualifying", "Sprint Shootout",
                   "Sprint", "Qualifying", "Race")

# "00:01:16.290", "1:16.290" or "22.5" -> seconds
hms_to_sec <- function(x) {
  vapply(strsplit(as.character(x), ":", fixed = TRUE), function(v) {
    v <- suppressWarnings(as.numeric(v))
    if (!length(v) || anyNA(v)) NA_real_ else sum(v * 60^(rev(seq_along(v)) - 1))
  }, numeric(1))
}

fmt_lap <- function(s) {
  out <- sprintf("%d:%06.3f", as.integer(s %/% 60), s %% 60)
  out[is.na(s)] <- ""
  out
}

hex <- function(x, fallback = "#8d95a1") {
  x <- ifelse(is.na(x) | x == "", NA, sub("^#?", "#", x))
  ifelse(is.na(x), fallback, x)
}

compound <- function(x) {
  x <- toupper(ifelse(is.na(x) | x == "", "UNKNOWN", x))
  ifelse(x %in% names(TYRE_COL), x, "UNKNOWN")
}

# Download a URL (once per session) to a temp file; NULL when it fails or has no data
.url_cache <- new.env()
fetch_url <- function(url, pause = 0) {
  url <- utils::URLencode(url)
  hit <- .url_cache[[url]]
  if (!is.null(hit)) return(hit)
  if (pause > 0) Sys.sleep(pause)
  f <- tempfile(fileext = ".json")
  ok <- tryCatch({ suppressWarnings(utils::download.file(url, f, quiet = TRUE, mode = "wb")); TRUE },
                 error = function(e) FALSE)
  if (!ok || !file.exists(f) || file.size(f) == 0) return(NULL)
  .url_cache[[url]] <- f
  f
}

safe_json <- function(file, pause = 0, ...) {
  if (grepl("^https?://", file)) file <- fetch_url(file, pause)
  if (is.null(file) || !file.exists(file)) return(NULL)
  tryCatch(jsonlite::fromJSON(file, ...), error = function(e) NULL)
}

# In web mode there is no folder to look in, so files are assumed to exist and fetched on demand
exists_file <- function(p) if (IS_WEB) rep(TRUE, length(p)) else file.exists(p)
exists_dir  <- function(p) if (IS_WEB) rep(TRUE, length(p)) else dir.exists(p)

add_team_colours <- function(e) {
  # Team colour (or a palette colour); the second driver of a team gets a dotted line
  teams <- unique(e$team)
  e[, colour := hex(primary_color, PAL[(match(team, teams) - 1) %% length(PAL) + 1])]
  e[, dash := fifelse(seq_len(.N) == 1, "solid", "dot"), by = team]
  e[]
}

of1_time <- function(x) as.POSIXct(substr(x, 1, 19), format = "%Y-%m-%dT%H:%M:%S", tz = "UTC")

# ---------- Load the tables ----------

if (IS_WEB) {
  W <- readRDS("webdata/bundle.rds")
  DB <- W$DB; JOL_RACES <- W$jol_races; STATS <- W$stats; CIRCUITS <- W$circuits
  TUM <- W$tum; TI_INDEX <- W$ti_index; FIA_PDFS <- W$fia
  rm(W)
} else {
  ROOT <- normalizePath(Sys.getenv("F1_DATA_ROOT", ".."), winslash = "/", mustWork = TRUE)
  path <- function(...) file.path(ROOT, ...)

  # F1DB: full history
  f1db <- function(name) fread(path("F1DB", "csv", paste0("f1db-", name, ".csv")), encoding = "UTF-8", na.strings = "")
  DB <- list(
    drivers       = f1db("drivers"),
    constructors  = f1db("constructors"),
    races         = f1db("races"),
    gp            = f1db("grands-prix"),
    results       = f1db("races-race-results"),
    race_dstand   = f1db("races-driver-standings"),
    season_dstand = f1db("seasons-driver-standings"),
    season_cstand = f1db("seasons-constructor-standings"),
    engines       = f1db("engines"),
    engman        = f1db("engine-manufacturers"),
    ent_eng       = f1db("seasons-entrants-engines"),
    tyreman       = f1db("tyre-manufacturers"),
    circuits      = f1db("circuits")
  )
  DB$races <- merge(DB$races, DB$gp[, .(grandPrixId = id, gpName = fullName)], by = "grandPrixId", all.x = TRUE)

  # Jolpica: lap-by-lap race data
  jol <- function(name, select) fread(path("Jolpica", "csv", paste0("formula_one_", name, ".csv")), select = select, na.strings = "")
  J <- list(
    season  = jol("season", c("id", "year")),
    round   = jol("round", c("id", "circuit_id", "date", "name", "number", "season_id")),
    session = jol("session", c("id", "round_id", "type")),
    entry   = jol("sessionentry", c("id", "session_id", "round_entry_id", "grid", "position", "points",
                                    "detail", "time", "laps_completed")),
    rentry  = jol("roundentry", c("id", "team_driver_id", "car_number")),
    tdriver = jol("teamdriver", c("id", "driver_id", "team_id")),
    driver  = jol("driver", c("id", "abbreviation", "forename", "surname")),
    team    = jol("team", c("id", "name", "primary_color")),
    lap     = jol("lap", c("id", "number", "position", "session_entry_id", "time")),
    pit     = jol("pitstop", c("duration", "lap_id", "number", "session_entry_id"))
  )
  J$lap <- J$lap[!is.na(number)]
  JOL_RACES <- local({
    r <- merge(J$session[type == "R", .(session_id = id, round_id)],
               J$round[, .(round_id = id, name, date, number, season_id)], by = "round_id")
    r <- merge(r, J$season[, .(season_id = id, year)], by = "season_id")
    with_laps <- unique(J$entry[id %in% unique(J$lap$session_entry_id), session_id])
    r <- r[session_id %in% with_laps][order(year, number)]
    r[, .(key = as.character(session_id), year, number, name, date)]
  })
  STATS <- list(laps = nrow(J$lap), pits = nrow(J$pit))

  # Circuit outlines
  CIRCUITS <- local({
    g <- jsonlite::fromJSON(path("f1-circuits", "f1-circuits", "f1-circuits.geojson"), simplifyVector = FALSE)
    out <- lapply(g$features, function(f) {
      xy <- do.call(rbind, lapply(f$geometry$coordinates, unlist))
      list(id = f$properties$id, name = f$properties$Name, location = f$properties$Location,
           opened = f$properties$opened, firstgp = f$properties$firstgp,
           length = f$properties$length, altitude = f$properties$altitude,
           lng = xy[, 1], lat = xy[, 2])
    })
    setNames(out, vapply(out, `[[`, "", "id"))
  })

  # TUM racing lines, read when a track is picked
  TUM_DIR <- path("TUMFTM_racetrack-database", "racetrack-database")
  TUM <- sub("\\.csv$", "", list.files(file.path(TUM_DIR, "tracks"), pattern = "\\.csv$"))
  TUM <- setNames(vector("list", length(TUM)), TUM)

  # TracingInsights: which events and sessions are on disk, ordered by race date
  TI_INDEX <- local({
    base <- path("TracingInsights_2026", "2026")
    if (!dir.exists(base)) return(data.table(event = character(), session = character(), date = character()))
    ev <- list.dirs(base, recursive = FALSE, full.names = FALSE)
    ev <- ev[!startsWith(ev, ".")]
    idx <- rbindlist(lapply(ev, function(e) {
      s <- list.dirs(file.path(base, e), recursive = FALSE, full.names = FALSE)
      s <- s[file.exists(file.path(base, e, s, "drivers.json"))]
      if (length(s)) data.table(event = e, session = s) else NULL
    }))
    if (!nrow(idx)) return(data.table(event = character(), session = character(), date = character()))
    cal <- safe_json(path("OpenF1", "meetings.json"))
    idx[, date := if (!is.null(cal)) { cal <- as.data.table(cal)[year == 2026]; cal$date_start[match(event, cal$meeting_name)] } else NA_character_]
    idx
  })

  # FIA regulations on disk: label -> path under FIA_documents/
  FIA_PDFS <- local({
    f <- list.files(path("FIA_documents"), pattern = "\\.pdf$", recursive = TRUE)
    m <- regmatches(basename(f), regexec("fia_(\\d{4})_f1_regulations_-_section_([a-f])_(.+?)_-_iss_(\\d+)_-_(\\d{4}-\\d{2}-\\d{2})", basename(f)))
    lab <- vapply(seq_along(f), function(i) {
      x <- m[[i]]
      if (length(x) < 6) return(basename(f[i]))
      topic <- tools::toTitleCase(gsub("_", " ", gsub("_-_", " / ", x[4])))
      sprintf("%s · Section %s · %s · Issue %d (%s)", x[2], toupper(x[3]), topic, as.integer(x[5]), x[6])
    }, "")
    setNames(f, lab)[order(lab)]
  })
}

# ---------- Derived tables (both modes) ----------

drv_name  <- setNames(DB$drivers$name, DB$drivers$id)
con_name  <- setNames(DB$constructors$name, DB$constructors$id)
eng_name  <- setNames(DB$engman$name, DB$engman$id)
tyre_name <- setNames(DB$tyreman$name, DB$tyreman$id)

F1DB_YEARS <- sort(unique(DB$season_dstand$year), decreasing = TRUE)
JOL_YEARS <- sort(unique(JOL_RACES$year), decreasing = TRUE)
CIRCUIT_CHOICES <- sort(setNames(names(CIRCUITS), vapply(CIRCUITS, `[[`, "", "name")))
TUM_TRACKS <- names(TUM)
TI_INDEX <- as.data.table(TI_INDEX)
TI_EVENTS <- unique(TI_INDEX[order(!is.na(date), date, event), event])

# Engine layout per entrant per season ("V10", "V6 turbo hybrid", ...)
ENGINE_ERAS <- local({
  e <- merge(DB$ent_eng, DB$engines[, .(engineId = id, configuration, aspiration)], by = "engineId", all.x = TRUE)
  asp <- c(NATURALLY_ASPIRATED = "", SUPERCHARGED = " supercharged",
           TURBOCHARGED = " turbo", TURBOCHARGED_HYBRID = " turbo hybrid")
  e[, layout := paste0(fcoalesce(configuration, "Unknown"), fcoalesce(unname(asp[aspiration]), ""))]
  e <- unique(e[, .(year, constructorId, layout)])
  e[, .(entrants = .N), by = .(year, layout)]
})

LAST_RACE <- local({
  w <- DB$results[positionNumber == 1][order(-raceId)][1]
  r <- DB$races[id == w$raceId]
  list(year = r$year, gp = r$gpName, date = r$date, winner = drv_name[[w$driverId]],
       team = con_name[[w$constructorId]])
})

# Match each outline to the nearest F1DB circuit (for races held, winners, turns)
circuit_f1db <- function(cid) {
  c <- CIRCUITS[[cid]]
  lat <- mean(range(c$lat)); lng <- mean(range(c$lng))
  d <- (DB$circuits$latitude - lat)^2 + ((DB$circuits$longitude - lng) * cos(lat * pi / 180))^2
  i <- which.min(d)
  if (sqrt(d[i]) * 111 > 8) return(NULL)  # more than ~8 km away: no match
  DB$circuits[i]
}

# ---------- Jolpica: one race ----------
# Returns list(e = entries, laps, pits). Entries carry id, driver, code, team, grid, position,
# laps_completed, time, detail, points, colour, dash; laps and pits refer to e$id as session_entry_id.

jol_race <- function(key) if (IS_WEB) jol_race_api(key) else jol_race_local(as.integer(key))

jol_race_local <- function(sid) {
  e <- J$entry[session_id == sid]
  e <- merge(e, J$rentry[, .(round_entry_id = id, team_driver_id, car_number)], by = "round_entry_id")
  e <- merge(e, J$tdriver[, .(team_driver_id = id, driver_id, team_id)], by = "team_driver_id")
  e <- merge(e, J$driver[, .(driver_id = id, abbreviation, forename, surname)], by = "driver_id")
  e <- merge(e, J$team[, .(team_id = id, team = name, primary_color)], by = "team_id")
  e[, code := fifelse(is.na(abbreviation) | abbreviation == "", toupper(substr(surname, 1, 3)), abbreviation)]
  e[, driver := paste(forename, surname)]
  e <- add_team_colours(e[order(fifelse(is.na(position), 99L, position), driver)])
  laps <- J$lap[session_entry_id %in% e$id, .(session_entry_id, number, position, sec = hms_to_sec(time))]
  pits <- J$pit[session_entry_id %in% e$id]
  pits <- merge(pits, J$lap[, .(lap_id = id, lap = number)], by = "lap_id", all.x = TRUE)
  pits <- pits[, .(session_entry_id, lap, number, sec = hms_to_sec(duration))]
  list(e = e, laps = laps, pits = pits)
}

jol_race_api <- function(key) {
  base <- paste(JOL_API, key, sep = "/")
  races <- safe_json(paste0(base, "/results/?limit=100"), pause = 0.25)$MRData$RaceTable$Races
  if (is.null(races) || !length(races$Results)) return(list(e = data.table(), laps = data.table(), pits = data.table()))
  r <- races$Results[[1]]
  col <- function(x, n = nrow(r)) if (is.null(x)) rep(NA, n) else x
  e <- data.table(id = r$Driver$driverId, forename = r$Driver$givenName, surname = r$Driver$familyName,
                  code = col(r$Driver$code), team = r$Constructor$name, primary_color = NA_character_,
                  grid = as.integer(r$grid), position = as.integer(r$position), laps_completed = as.integer(r$laps),
                  time = col(r$Time$time), detail = r$status, points = as.numeric(r$points))
  e[, code := fifelse(is.na(code) | code == "", toupper(substr(surname, 1, 3)), code)]
  e[, driver := paste(forename, surname)]
  e <- add_team_colours(e[order(position)])

  laps <- list(); off <- 0
  repeat {
    j <- safe_json(sprintf("%s/laps/?limit=100&offset=%d", base, off), pause = 0.25)
    lp <- j$MRData$RaceTable$Races$Laps
    if (is.null(lp) || !length(lp)) break
    lp <- lp[[1]]
    laps[[length(laps) + 1]] <- rbindlist(lapply(seq_len(nrow(lp)), function(i) {
      t <- lp$Timings[[i]]
      data.table(session_entry_id = t$driverId, number = as.integer(lp$number[i]),
                 position = as.integer(t$position), sec = hms_to_sec(t$time))
    }))
    off <- off + 100
    if (off >= as.integer(j$MRData$total)) break
  }
  ps <- safe_json(paste0(base, "/pitstops/?limit=100"), pause = 0.25)$MRData$RaceTable$Races$PitStops
  pits <- if (length(ps) && is.data.frame(ps[[1]])) {
    p <- ps[[1]]
    data.table(session_entry_id = p$driverId, lap = as.integer(p$lap), number = as.integer(p$stop), sec = hms_to_sec(p$duration))
  } else data.table()
  list(e = e, laps = rbindlist(laps), pits = pits)
}

# ---------- OpenF1: 2023+ sessions ----------
# A meeting is identified by its folder (local) or its meeting_key (web).

OF1_DIR <- if (IS_WEB) "" else path("OpenF1", "meetings")

of1_meetings <- function() {
  if (IS_WEB) {
    m <- as.data.table(safe_json(paste0(OF1_API, "/meetings")))
    if (!nrow(m)) return(m)
    m <- m[!is_cancelled & of1_time(date_end) < Sys.time()]
    return(m[order(date_start), .(dir = as.character(meeting_key), meeting_key, year, name = meeting_name,
                                  location, date_start)])
  }
  dirs <- list.dirs(OF1_DIR, recursive = FALSE)
  m <- rbindlist(lapply(dirs, function(d) {
    x <- safe_json(file.path(d, "meeting.json"))
    if (is.null(x) || !file.exists(file.path(d, "sessions.json"))) return(NULL)
    data.table(dir = d, meeting_key = x$meeting_key, year = x$year, name = x$meeting_name,
               location = x$location, date_start = x$date_start)
  }), fill = TRUE)
  if (nrow(m)) m[order(date_start)] else m
}

read_of1 <- function(dir, ep) {
  # Free API tier: 3 requests a second, so web requests are spaced out
  x <- if (IS_WEB) safe_json(sprintf("%s/%s?meeting_key=%s", OF1_API, ep, dir), pause = 0.4)
       else safe_json(file.path(dir, paste0(ep, ".json")))
  if (is.null(x) || !length(x)) return(data.table())
  x <- as.data.table(x)
  drop <- names(x)[vapply(x, is.list, logical(1)) & startsWith(names(x), "segments")]
  if (length(drop)) x[, (drop) := NULL]
  x[]
}

# One endpoint for one session: local files hold the whole meeting, the web API is asked for the session only
read_of1_session <- function(dir, sk, ep) {
  if (IS_WEB) {
    x <- safe_json(sprintf("%s/%s?session_key=%d", OF1_API, ep, sk), pause = 0.4)
    if (is.null(x) || !length(x)) return(data.table())
    x <- as.data.table(x)
    drop <- names(x)[vapply(x, is.list, logical(1)) & startsWith(names(x), "segments")]
    if (length(drop)) x[, (drop) := NULL]
    return(x[])
  }
  x <- read_of1(dir, ep)
  if (nrow(x) && "session_key" %in% names(x)) x[session_key == sk] else x
}

# ---------- TracingInsights: 2026 telemetry ----------

TI_DIR <- if (IS_WEB) TI_RAW else path("TracingInsights_2026", "2026")

ti_sessions <- function(event) {
  s <- TI_INDEX$session[TI_INDEX$event == event]
  s[order(match(s, SESSION_ORDER, nomatch = 0), s)]
}

ti_laps <- function(event, sess, drv) {
  x <- safe_json(file.path(TI_DIR, event, sess, drv, "laptimes.json"))
  if (is.null(x)) return(data.table())
  keep <- c("lap", "time", "compound", "stint", "life", "pos", "pb", "del", "s1", "s2", "s3", "vst")
  x <- x[intersect(keep, names(x))]
  n <- max(lengths(x))
  d <- as.data.table(lapply(x, function(v) if (length(v) == n) v else rep(NA, n)))
  for (k in setdiff(keep, names(d))) d[, (k) := NA]
  # Missing values can arrive as the string "None", which turns numeric columns into text
  nums <- c("lap", "time", "stint", "life", "pos", "s1", "s2", "s3", "vst")
  d[, (nums) := lapply(.SD, function(v) suppressWarnings(as.numeric(v))), .SDcols = nums]
  d[, del := as.character(del) %in% c("TRUE", "true", "True")]
  d[!is.na(lap)]
}

ti_tel <- function(event, sess, drv, lap) {
  x <- safe_json(file.path(TI_DIR, event, sess, drv, paste0(lap, "_tel.json")))
  if (is.null(x)) return(NULL)
  t <- x$tel
  cols <- c("time", "speed", "throttle", "brake", "gear", "rpm", "drs", "distance", "x", "y")
  d <- as.data.table(lapply(t[cols], function(v) suppressWarnings(as.numeric(unlist(lapply(v, function(z) if (is.null(z)) NA else z))))))
  d[!is.na(distance) & !is.na(time)]
}

# ---------- TUM racing lines ----------

tum_track <- function(name) {
  if (!is.null(TUM[[name]])) return(TUM[[name]])
  tr <- fread(file.path(TUM_DIR, "tracks", paste0(name, ".csv")), skip = 1, col.names = c("x", "y", "wr", "wl"))
  rl_file <- file.path(TUM_DIR, "racelines", paste0(name, ".csv"))
  rl <- if (file.exists(rl_file)) fread(rl_file, skip = 1, col.names = c("x", "y")) else NULL
  list(track = tr, raceline = rl)
}

# ---------- FIA regulations ----------
# Local: served from FIA_documents/ under /fia; web: linked straight to fia.com

fia_src <- function(doc) if (IS_WEB) doc else paste0("fia/", utils::URLencode(doc))
