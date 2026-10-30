# Start the regs_analyzer_25_26 dashboard (Python / Dash) from RStudio and show it in the Viewer pane.
#
# Usage: open this file in RStudio and click "Source" (or run source("regs_analyzer_25_26/run_dashboard.R")).
# The first run creates the Python environment (.venv) and installs requirements.txt; that takes a few
# minutes. Later runs start in a few seconds. The dashboard keeps running in the background while you
# use the R console; stop it with stop_dashboard(). It also stops when the R session ends.
#
# Needs Python 3.10+ and the R packages processx, rstudioapi and httpuv.

local({
  # Folder that holds dashboard/app.py: next to this script, or the working directory
  this_file <- tryCatch(normalizePath(sys.frame(1)$ofile), error = function(e) NA)
  candidates <- c(
    if (!is.na(this_file)) dirname(this_file),
    if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable())
      tryCatch(dirname(rstudioapi::getSourceEditorContext()$path), error = function(e) NULL),
    getwd(), file.path(getwd(), "regs_analyzer_25_26"))
  app_dir <- candidates[file.exists(file.path(candidates, "dashboard", "app.py"))][1]
  if (is.na(app_dir)) {
    stop("Can't find dashboard/app.py. Set the working directory to the regs_analyzer_25_26 folder ",
         "(Session > Set Working Directory) and run this script again.")
  }
  app_dir <- normalizePath(app_dir, winslash = "/")

  show <- function(url) {
    if (!getOption("regs_dashboard.open", TRUE)) return(invisible())
    if (rstudioapi::isAvailable()) rstudioapi::viewer(url) else utils::browseURL(url)
  }

  # Already running from an earlier run: just show it again
  old <- get0(".regs_dashboard", envir = globalenv())
  if (!is.null(old) && old$process$is_alive()) {
    message("Dashboard already running at ", old$url)
    show(old$url)
    return(invisible())
  }

  # Python environment: create it on the first run
  windows <- .Platform$OS.type == "windows"
  python <- file.path(app_dir, ".venv", if (windows) "Scripts/python.exe" else "bin/python")
  if (!file.exists(python)) {
    message("First run: creating the Python environment in ", app_dir, "/.venv (a few minutes)...")
    if (windows && nzchar(Sys.which("py"))) {
      cmd <- "py"; args <- c("-3", "-m", "venv", ".venv")
    } else {
      cmd <- unname(Sys.which(c("python3", "python")))
      cmd <- cmd[nzchar(cmd)][1]
      args <- c("-m", "venv", ".venv")
    }
    if (is.na(cmd)) stop("Python 3 was not found. Install it from https://www.python.org and run this script again.")
    owd <- setwd(app_dir)
    on.exit(setwd(owd), add = TRUE)
    if (system2(cmd, args) != 0 || !file.exists(python)) stop("Could not create the Python environment.")
    if (system2(python, c("-m", "pip", "install", "-q", "-r", "requirements.txt")) != 0) {
      stop("Could not install the Python packages from requirements.txt.")
    }
  }

  # Port 8050 unless something else is using it (a successful connection means it is taken)
  port_free <- function(p) {
    con <- suppressWarnings(tryCatch(socketConnection("127.0.0.1", p, open = "r+", blocking = TRUE, timeout = 1),
                                     error = function(e) NULL))
    if (is.null(con)) return(TRUE)
    close(con)
    FALSE
  }
  port <- if (port_free(8050)) 8050L else httpuv::randomPort()
  url <- sprintf("http://127.0.0.1:%d", port)

  log_file <- file.path(tempdir(), "regs_dashboard.log")
  proc <- processx::process$new(python, "dashboard/app.py", wd = app_dir,
                                env = c("current", PORT = as.character(port)),
                                stdout = log_file, stderr = "2>&1", cleanup = TRUE)

  # Wait until the app answers (it loads the results first)
  ready <- FALSE
  for (i in 1:120) {
    if (!proc$is_alive()) break
    ready <- suppressWarnings(tryCatch({ readLines(url, n = 1, warn = FALSE); TRUE }, error = function(e) FALSE))
    if (ready) break
    Sys.sleep(0.5)
  }
  if (!ready) {
    proc$kill()
    stop("The dashboard did not start. Last lines of the log:\n",
         paste(utils::tail(readLines(log_file, warn = FALSE), 15), collapse = "\n"))
  }

  assign(".regs_dashboard", list(process = proc, url = url, log = log_file), envir = globalenv())
  assign("stop_dashboard", function() {
    d <- get0(".regs_dashboard", envir = globalenv())
    if (!is.null(d) && d$process$is_alive()) d$process$kill()
    message("Dashboard stopped.")
    invisible()
  }, envir = globalenv())

  message("Dashboard running at ", url, "  (stop it with stop_dashboard())")
  show(url)
})
