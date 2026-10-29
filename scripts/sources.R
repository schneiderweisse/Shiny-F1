# Shared helpers for scripts/fetch_data.R and scripts/build_web.R: HTTP downloads and source listings.

UA <- "Shiny-F1 data fetcher (https://github.com/schneiderweisse/Shiny-F1)"

# Download a URL to a file. Returns list(path, error): path is NULL when the request failed.
http_get <- function(url, dest = tempfile(), token = Sys.getenv("GITHUB_TOKEN")) {
  h <- c("User-Agent" = UA)
  if (nzchar(token) && grepl("^https://api\\.github\\.com/", url)) h <- c(h, Authorization = paste("Bearer", token))
  # Keep every message: the HTTP status ("404 Not Found") is in the warning, not in the final error
  err <- character()
  ok <- withCallingHandlers(
    tryCatch({
      utils::download.file(url, dest, mode = "wb", quiet = TRUE, method = "libcurl", headers = h)
      TRUE
    }, error = function(e) { err <<- c(err, conditionMessage(e)); FALSE }),
    warning = function(w) { err <<- c(err, conditionMessage(w)); invokeRestart("muffleWarning") })
  if (!ok) { unlink(dest); return(list(path = NULL, error = paste(err, collapse = " | "))) }
  list(path = dest, error = NULL)
}

get_json <- function(url, ...) {
  r <- http_get(url)
  if (is.null(r$path)) return(NULL)
  tryCatch(jsonlite::fromJSON(r$path, ...), error = function(e) NULL)
}

sha256_ok <- function(file, expected) {
  if (!requireNamespace("openssl", quietly = TRUE)) return(NA)
  got <- paste(as.character(openssl::sha256(file(file))), collapse = "")
  isTRUE(tolower(got) == tolower(trimws(expected)))
}

# Latest issue of each FIA Formula 1 regulation section, for seasons >= min_year.
# Returns a data.frame with url, file, year, section, topic, issue, date, label.
fia_latest_regulations <- function(min_year = as.integer(format(Sys.Date(), "%Y"))) {
  r <- http_get("https://www.fia.com/regulation/category/110")
  if (is.null(r$path)) stop("Could not read the FIA regulations page: ", r$error)
  html <- paste(readLines(r$path, warn = FALSE, encoding = "UTF-8"), collapse = "\n")
  hrefs <- unique(regmatches(html, gregexpr("/system/files/documents/fia_\\d{4}_f1_regulations_-_section_[a-f]_[^\"]+?\\.pdf", html))[[1]])
  f <- basename(hrefs)
  m <- regmatches(f, regexec("fia_(\\d{4})_f1_regulations_-_section_([a-f])_(.+?)_-_iss_(\\d+)_-_(\\d{4}-\\d{2}-\\d{2})", f))
  pick <- function(i) vapply(m, function(x) if (length(x) >= 6) x[i] else NA_character_, "")
  d <- data.frame(url = paste0("https://www.fia.com", hrefs), file = f, year = as.integer(pick(2)),
                  section = pick(3), topic = pick(4), issue = as.integer(pick(5)), date = pick(6))
  d <- d[!is.na(d$year) & d$year >= min_year, ]
  d <- d[order(d$year, d$section, -d$issue, d$date), ]
  d <- d[!duplicated(d[c("year", "section")]), ]
  d$label <- sprintf("%d · Section %s · %s · Issue %d (%s)", d$year, toupper(d$section),
                     tools::toTitleCase(gsub("_", " ", gsub("_-_", " / ", d$topic))), d$issue, d$date)
  d
}

# Events and sessions in the TracingInsights telemetry repo, found through the GitHub API.
# A session counts when its drivers.json exists. Dates come from the OpenF1 calendar.
ti_index_github <- function(repo = "TracingInsights/2026", year = 2026) {
  root <- get_json(sprintf("https://api.github.com/repos/%s/contents/", repo))
  if (is.null(root)) stop("Could not list ", repo, " on GitHub")
  events <- root$name[root$type == "dir" & !startsWith(root$name, ".")]
  raw <- sprintf("https://raw.githubusercontent.com/%s/main", repo)
  rows <- lapply(events, function(e) {
    s <- get_json(sprintf("https://api.github.com/repos/%s/contents/%s", repo, utils::URLencode(e)))
    if (is.null(s) || !is.data.frame(s)) return(NULL)
    s <- s$name[s$type == "dir"]
    has <- vapply(s, function(x) {
      h <- tryCatch(curlGetHeaders(utils::URLencode(paste(raw, e, x, "drivers.json", sep = "/"))), error = function(err) NULL)
      !is.null(h) && attr(h, "status") == 200
    }, logical(1))
    if (any(has)) data.frame(event = e, session = s[has]) else NULL
  })
  idx <- do.call(rbind, rows)
  cal <- get_json(sprintf("https://api.openf1.org/v1/meetings?year=%d", year))
  idx$date <- if (!is.null(cal)) cal$date_start[match(idx$event, cal$meeting_name)] else NA_character_
  idx
}
