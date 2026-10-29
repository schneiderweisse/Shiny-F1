# F1 Data Pit Wall: a Shiny dashboard over Formula 1 data from F1DB, Jolpica, OpenF1, TracingInsights,
# f1-circuits, the TUM racetrack database and the FIA.
# Run from the repo folder after scripts/fetch_data.R:   Rscript -e "shiny::runApp('dashboard')"
# R/data.R loads the packages and data (local folders or, on GitHub Pages, live APIs); R/plots.R holds the charts.

if (!IS_WEB) addResourcePath("fia", path("FIA_documents"))

# ---------- UI helpers ----------

controls <- function(...) div(class = "pw-controls", ...)

pw_card <- function(title, ..., sub = NULL, full_screen = TRUE) {
  card(full_screen = full_screen,
       card_header(title, if (!is.null(sub)) span(class = "pw-sub", sub)),
       card_body(..., class = "p-2"))
}

tile <- function(value, label) div(class = "pw-tile", div(class = "val", value), div(class = "lab", label))

num <- function(x) format(x, big.mark = ",")

source_card <- function(n, name, tab, text, meta) {
  div(class = "pw-source",
      div(class = "pw-source-head", span(class = "num", n), name),
      p(text),
      div(class = "meta", span("Tab: ", tags$b(tab)), lapply(meta, span)))
}

tyre_legend <- div(class = "pw-tyres", lapply(names(TYRE_COL)[1:5], function(c)
  span(class = "pw-tyre", style = sprintf("color:%s", TYRE_COL[[c]]), tags$i(), tools::toTitleCase(tolower(c)))))

pw_dt <- function(d, pos_col = 1, mono_cols = NULL, page = 20) {
  defs <- list()
  if (!is.null(pos_col)) defs <- c(defs, list(list(className = "pw-pos", targets = pos_col - 1)))
  if (length(mono_cols)) defs <- c(defs, list(list(className = "pw-mono", targets = mono_cols - 1)))
  datatable(d, rownames = FALSE, selection = "none", class = "compact",
            options = list(dom = if (nrow(d) > page) "tip" else "t", pageLength = page,
                           ordering = FALSE, autoWidth = FALSE, columnDefs = defs))
}

# ---------- Tabs ----------

welcome_tab <- nav_panel(
  "Pit Wall",
  div(class = "pw-hero",
      div(class = "pw-eyebrow", "Pit wall online · data through ", LAST_RACE$date),
      h1(HTML("Every lap since <em>1950</em>,<br>on one pit wall")),
      p("77 seasons of results, lap-by-lap race charts, live-timing feeds since 2023, 2026 car telemetry,",
        "circuit maps and the rulebook, from seven open Formula 1 data sources.",
        "Pick a tab above. Every chart is interactive: hover for values, drag to zoom, double-click to reset."),
      if (IS_WEB) p(class = "pw-webnote",
                    "Web edition: this app runs entirely in your browser. Race Replay, Timing Screen and Telemetry",
                    "fetch their data live from Jolpica, OpenF1 and TracingInsights, so each new selection takes a few seconds."),
      div(class = "pw-lastrace", span(class = "flag"), "Last chequered flag:",
          tags$b(paste(LAST_RACE$year, LAST_RACE$gp)), "won by", tags$b(LAST_RACE$winner), paste0("(", LAST_RACE$team, ")"))),
  div(class = "pw-tiles",
      tile(length(unique(DB$races$year)), "Seasons"),
      tile(num(DB$races[date <= Sys.Date(), .N]), "Grands Prix run"),
      tile(num(nrow(DB$drivers)), "Drivers"),
      tile(num(STATS$laps), "Race laps timed"),
      tile(num(STATS$pits), "Pit stops logged"),
      tile(textOutput("tile_of1", inline = TRUE), "OpenF1 meetings"),
      tile(nrow(TI_INDEX), "2026 telemetry sessions"),
      tile(length(CIRCUITS), "Circuit maps")),
  h2(class = "pw-section-title", "What's in the garage"),
  div(class = "pw-sources",
      source_card(1, "F1DB", "Hall of Fame · Engine Room",
                  "Every championship race since 1950: results, standings, drivers, constructors, chassis, engines and tyre suppliers.",
                  list("CSV · JSON · SQLite", "1950–2026")),
      source_card(2, "Jolpica", "Race Replay",
                  "The Ergast-format database with lap-by-lap times and positions, pit stop durations and full classifications.",
                  list("CSV · SQL", sprintf("Laps from %d", min(JOL_RACES$year)))),
      source_card(3, "OpenF1", "Timing Screen",
                  "Live-timing data for every session since 2023: tyre stints, lap times, running order, weather, race control and team radio.",
                  list("JSON per meeting", "2023–2026")),
      source_card(4, "TracingInsights", "Telemetry",
                  "Car telemetry for every lap of 2026: speed, throttle, brake, gear, RPM and position on track, about four samples a second.",
                  list("JSON per lap", "2026 season")),
      source_card(5, "f1-circuits", "Circuits",
                  "GeoJSON outlines of 40 circuit layouts, from Monza 1922 to Madrid 2026, drawn on a world map.",
                  list("GeoJSON", "40 layouts")),
      source_card(6, "TUM racetrack database", "Circuits",
                  "Track centre lines and widths with computed minimum-curvature racing lines, from TU Munich.",
                  list("CSV, metres", sprintf("%d tracks", length(TUM_TRACKS)))),
      source_card(7, "FIA regulations", "Rulebook",
                  "The 2026 Formula 1 regulations, sections A to F, plus the 2027 drafts, readable in the app.",
                  list("PDF", sprintf("%d documents", length(FIA_PDFS)))))
)

DRIVER_METRICS <- c("Race wins" = "totalRaceWins", "Pole positions" = "totalPolePositions",
                    "Podiums" = "totalPodiums", "World titles" = "totalChampionshipWins",
                    "Fastest laps" = "totalFastestLaps", "Race starts" = "totalRaceStarts",
                    "Grand slams" = "totalGrandSlams", "Career points" = "totalPoints")
CON_METRICS <- c("Race wins" = "totalRaceWins", "Constructors' titles" = "totalChampionshipWins",
                 "Pole positions" = "totalPolePositions", "1-2 finishes" = "total1And2Finishes",
                 "Podiums" = "totalPodiums", "Race starts" = "totalRaceStarts")

hof_tab <- nav_panel(
  "Hall of Fame",
  controls(selectInput("hof_year", "Season", F1DB_YEARS, selected = 2004, width = "140px"),
           selectInput("hof_metric", "All-time ranking", DRIVER_METRICS, width = "200px")),
  layout_columns(col_widths = c(8, 4),
                 pw_card("Championship battle", sub = "points after each round, top 8",
                         plotlyOutput("hof_battle", height = "430px")),
                 pw_card("Drivers' standings", DTOutput("hof_stand"))),
  layout_columns(col_widths = c(6, 6),
                 pw_card("All-time leaders", sub = "drivers, 1950 to today", plotlyOutput("hof_leaders", height = "460px")),
                 pw_card("Constructors' championship", DTOutput("hof_cstand")))
)

engine_tab <- nav_panel(
  "Engine Room",
  controls(sliderInput("er_years", "Seasons", min = min(F1DB_YEARS), max = max(F1DB_YEARS),
                       value = c(1980, max(F1DB_YEARS)), sep = "", step = 1, width = "340px"),
           selectInput("er_metric", "Constructor ranking", CON_METRICS, width = "200px")),
  pw_card("Engine layouts on the grid", sub = "constructors entered per season, by engine layout",
          plotlyOutput("er_layouts", height = "380px")),
  layout_columns(col_widths = c(6, 6),
                 pw_card("Wins by engine maker", plotlyOutput("er_engwins", height = "380px")),
                 pw_card("The tyre wars", sub = "race wins by tyre supplier", plotlyOutput("er_tyrewins", height = "380px"))),
  pw_card("Constructors, all time", plotlyOutput("er_cons", height = "440px"))
)

race_tab <- nav_panel(
  "Race Replay",
  controls(selectInput("rr_year", "Season", JOL_YEARS, selected = 2005, width = "120px"),
           selectInput("rr_race", "Grand Prix", NULL, width = "300px"),
           selectizeInput("rr_drivers", "Lap times for", NULL, multiple = TRUE, width = "420px",
                          options = list(maxItems = 6, placeholder = "Pick up to 6 drivers")),
           checkboxInput("rr_clean", "Hide pit and safety car laps", TRUE)),
  pw_card("Lap chart", sub = "position at the end of every lap; lap 0 is the grid",
          plotlyOutput("rr_poschart", height = "520px")),
  layout_columns(col_widths = c(7, 5),
                 pw_card("Lap times", plotlyOutput("rr_laptimes", height = "380px")),
                 pw_card("Pit stops", sub = "bubble size = time in the pit lane", plotlyOutput("rr_pits", height = "380px"))),
  pw_card("Classification", DTOutput("rr_class"))
)

timing_tab <- nav_panel(
  "Timing Screen",
  controls(selectInput("of_year", "Season", NULL, width = "110px"),
           selectInput("of_meeting", "Meeting", NULL, width = "300px"),
           selectInput("of_session", "Session", NULL, width = "180px"),
           checkboxInput("of_clean", "Hide slow and out laps", TRUE)),
  layout_columns(col_widths = c(6, 6),
                 pw_card("Tyre strategy", plotlyOutput("of_tyres", height = "470px"), tyre_legend),
                 pw_card("Lap times", plotlyOutput("of_laps", height = "500px"))),
  layout_columns(col_widths = c(8, 4),
                 pw_card("Running order", plotlyOutput("of_pos", height = "430px")),
                 pw_card("Session result", DTOutput("of_result"))),
  layout_columns(col_widths = c(7, 5),
                 pw_card("Weather", plotlyOutput("of_weather", height = "360px")),
                 pw_card("Team radio",
                         div(class = "pw-controls", style = "margin-bottom:8px",
                             selectInput("of_radio_drv", "Driver", c("All drivers" = "all"), width = "200px")),
                         uiOutput("of_radio"))),
  pw_card("Race control messages", DTOutput("of_rc"))
)

telemetry_tab <- nav_panel(
  "Telemetry",
  controls(selectInput("ti_event", "Event (2026)", TI_EVENTS, selected = tail(TI_EVENTS, 1), width = "230px"),
           selectInput("ti_session", "Session", NULL, width = "150px"),
           selectInput("ti_drvA", "Driver A", NULL, width = "230px"),
           selectInput("ti_lapA", "Lap A", NULL, width = "230px"),
           selectInput("ti_drvB", "Driver B", NULL, width = "230px"),
           selectInput("ti_lapB", "Lap B", NULL, width = "230px"),
           radioButtons("ti_map", "Track map", c("Faster per mini-sector" = "delta", "Speed of driver A" = "speed"),
                        inline = TRUE)),
  layout_columns(col_widths = c(7, 5),
                 pw_card("Telemetry trace", sub = "A against B over one lap", plotlyOutput("ti_trace", height = "800px")),
                 div(pw_card("Track map", plotlyOutput("ti_map_plot", height = "430px")),
                     pw_card("Lap times this session", sub = "markers in tyre colours",
                             plotlyOutput("ti_lapplot", height = "300px"))))
)

circuits_tab <- nav_panel(
  "Circuits",
  controls(selectInput("circ_id", "Circuit", CIRCUIT_CHOICES, selected = "it-1922", width = "300px"),
           selectInput("tum_track", "Racing line lab", TUM_TRACKS, selected = "Monza", width = "180px"),
           div(class = "pw-note", "Click a yellow dot on the map to pick a circuit; the map flies to its outline.")),
  layout_columns(col_widths = c(8, 4),
                 pw_card("World map", leafletOutput("circ_map", height = "560px")),
                 pw_card("Circuit file", uiOutput("circ_info"), DTOutput("circ_winners"))),
  pw_card("Racing line lab", sub = "TU Munich: track edges and the minimum-curvature racing line",
          plotlyOutput("tum_plot", height = "600px"))
)

FIA_SECTIONS <- list(
  A = c("General provisions", "Definitions, how the regulations are structured and how they apply."),
  B = c("Sporting", "Race weekend format, points, penalties, tyre and power unit allocations."),
  C = c("Technical", "The car: dimensions, aerodynamics, weight, safety and the power unit."),
  D = c("Financial, F1 teams", "The team cost cap and what must be reported."),
  E = c("Financial, PU makers", "The power unit manufacturers' cost cap."),
  F = c("Operational", "Operational rules for teams; see each document's contents page."))

rules_tab <- nav_panel(
  "Rulebook",
  controls(selectInput("fia_doc", "Document", FIA_PDFS,
                       selected = c(FIA_PDFS[grepl("^2026 · Section C", names(FIA_PDFS))], FIA_PDFS)[1], width = "560px")),
  layout_columns(col_widths = c(3, 9),
                 pw_card("The six sections", full_screen = FALSE,
                         div(class = "pw-sections", lapply(names(FIA_SECTIONS), function(k)
                           div(class = "pw-sec", div(class = "l", k),
                               div(class = "x", tags$b(FIA_SECTIONS[[k]][1]), div(FIA_SECTIONS[[k]][2]))))),
                         p(style = "margin-top:14px;color:#8d95a1;font-size:.88rem",
                           "Source: fia.com, latest issues as of 29 Oct 2026.")),
                 pw_card("Document", uiOutput("fia_view")))
)

ui <- page_navbar(
  title = span(class = "pw-brand", span(class = "pw-brand-f1", "F1"), "DATA PIT WALL"),
  window_title = "F1 Data Pit Wall",
  theme = bs_theme(version = 5, bg = "#0b0d10", fg = "#dfe3e8", primary = "#e10600", secondary = "#2b3038",
                   base_font = "Barlow Semi Condensed", heading_font = "Exo 2", code_font = "Share Tech Mono"),
  header = tags$head(
    tags$link(rel = "preconnect", href = "https://fonts.googleapis.com"),
    tags$link(rel = "stylesheet", href = "https://fonts.googleapis.com/css2?family=Exo+2:ital,wght@0,700;0,800;1,700;1,800;1,900&family=Barlow+Semi+Condensed:wght@400;500;600;700&family=Share+Tech+Mono&display=swap"),
    tags$link(rel = "stylesheet", href = "pitwall.css")),
  fillable = FALSE,
  welcome_tab, hof_tab, engine_tab, race_tab, timing_tab, telemetry_tab, circuits_tab, rules_tab
)

# ---------- Server ----------

server <- function(input, output, session) {

  # ---- Pit Wall ----
  # Locally, pick up meetings as fetch_data.R adds them; on the web, ask the API once
  of1_list <- if (IS_WEB) reactive(of1_meetings()) else
    reactivePoll(60000, session, function() length(list.dirs(OF1_DIR, recursive = FALSE)), of1_meetings)
  output$tile_of1 <- renderText(nrow(of1_list()))

  # ---- Hall of Fame (F1DB) ----
  output$hof_battle <- renderPlotly({
    yr <- as.integer(input$hof_year)
    st <- DB$race_dstand[year == yr]
    validate(need(nrow(st) > 0, "No standings for this season"))
    top <- DB$season_dstand[year == yr][order(positionDisplayOrder)][seq_len(min(8, .N)), driverId]
    d <- merge(st[driverId %in% top], DB$races[, .(raceId = id, gpName)], by = "raceId", all.x = TRUE)[order(round)]
    p <- plot_ly()
    for (i in seq_along(top)) {
      dd <- d[driverId == top[i]]
      p <- add_trace(p, x = dd$round, y = dd$points, type = "scatter", mode = "lines+markers",
                     name = paste0("P", i, " ", drv_name[[top[i]]]),
                     line = list(color = PAL[i], width = if (i == 1) 4 else 2), marker = list(size = 6, color = PAL[i]),
                     text = sprintf("<b>%s</b><br>R%d %s<br>%s pts", drv_name[[top[i]]], dd$round, dd$gpName, dd$points),
                     hoverinfo = "text")
    }
    pw_layout(p, xtitle = "Round", ytitle = "Championship points")
  })

  output$hof_stand <- renderDT({
    yr <- as.integer(input$hof_year)
    s <- DB$season_dstand[year == yr][order(positionDisplayOrder)]
    r <- DB$results[year == yr]
    w <- r[positionNumber == 1, .N, by = driverId]
    pod <- r[positionNumber <= 3, .N, by = driverId]
    d <- s[, .(Pos = positionText, Driver = unname(drv_name[driverId]),
               Wins = fcoalesce(w$N[match(driverId, w$driverId)], 0L),
               Podiums = fcoalesce(pod$N[match(driverId, pod$driverId)], 0L),
               Points = points)]
    pw_dt(d, mono_cols = 5, page = 12)
  })

  output$hof_leaders <- renderPlotly(hbar_leaders(DB$drivers, "name", input$hof_metric))

  output$hof_cstand <- renderDT({
    yr <- as.integer(input$hof_year)
    s <- DB$season_cstand[year == yr][order(positionDisplayOrder)]
    validate(need(nrow(s) > 0, "The constructors' championship started in 1958"))
    d <- s[, .(Pos = positionText, Constructor = unname(con_name[constructorId]),
               Engine = unname(eng_name[engineManufacturerId]), Points = points)]
    pw_dt(d, mono_cols = 4, page = 12)
  })

  # ---- Engine Room (F1DB) ----
  output$er_layouts <- renderPlotly({
    y <- input$er_years
    stacked_years(ENGINE_ERAS[year %between% y], "layout", "entrants", top_n = 10, ytitle = "Constructors")
  })
  output$er_engwins <- renderPlotly({
    y <- input$er_years
    d <- DB$results[positionNumber == 1 & year %between% y, .(wins = .N), by = .(year, engineManufacturerId)]
    stacked_years(d, "engineManufacturerId", "wins", 9, "Race wins", labeller = function(x) unname(eng_name[x]))
  })
  output$er_tyrewins <- renderPlotly({
    y <- input$er_years
    d <- DB$results[positionNumber == 1 & year %between% y, .(wins = .N), by = .(year, tyreManufacturerId)]
    stacked_years(d, "tyreManufacturerId", "wins", 6, "Race wins", labeller = function(x) unname(tyre_name[x]))
  })
  output$er_cons <- renderPlotly(hbar_leaders(DB$constructors, "name", input$er_metric))

  # ---- Race Replay (Jolpica) ----
  observeEvent(input$rr_year, {
    r <- JOL_RACES[year == as.integer(input$rr_year)]
    updateSelectInput(session, "rr_race", choices = setNames(r$key, sprintf("R%02d · %s", r$number, r$name)),
                      selected = tail(r$key, 1))
  })
  rr_d <- reactive({
    req(input$rr_race)
    jol_race(input$rr_race)
  })
  rr_e <- reactive(rr_d()$e)
  rr_laps <- reactive({
    d <- rr_d()
    req(nrow(d$e))
    L <- merge(d$laps, d$e[, .(session_entry_id = id, driver, code, team, colour, dash)], by = "session_entry_id")
    L[order(driver, number)]
  })
  observeEvent(rr_e(), {
    e <- rr_e()
    updateSelectizeInput(session, "rr_drivers", choices = e$driver, selected = head(e$driver, 4))
  })

  output$rr_poschart <- renderPlotly({
    e <- rr_e()
    L <- rr_laps()
    validate(need(nrow(L) > 0, "No lap data for this race"))
    p <- plot_ly()
    for (i in seq_len(nrow(e))) {
      d <- L[session_entry_id == e$id[i], .(number, position)]
      if (!nrow(d)) next
      g <- e$grid[i]
      if (!is.na(g) && g > 0) d <- rbind(data.table(number = 0L, position = g), d)
      p <- add_trace(p, x = d$number, y = d$position, type = "scatter", mode = "lines", name = e$code[i],
                     line = list(color = e$colour[i], width = 2.2, dash = e$dash[i]),
                     hovertemplate = sprintf("<b>%s</b> (%s)<br>Lap %%{x}: P%%{y}<extra></extra>", e$driver[i], e$team[i]))
    }
    pw_layout(p, xtitle = "Lap", ytitle = "Position", yaxis = list(autorange = "reversed", dtick = 1))
  })

  output$rr_laptimes <- renderPlotly({
    all <- rr_laps()
    L <- all[driver %in% input$rr_drivers]
    validate(need(nrow(L) > 0, "Pick drivers in the bar above"))
    if (isTRUE(input$rr_clean)) L <- L[sec <= median(all$sec, na.rm = TRUE) * 1.08]
    p <- plot_ly()
    for (dn in input$rr_drivers) {
      x <- L[driver == dn]
      if (!nrow(x)) next
      p <- add_trace(p, x = x$number, y = x$sec, type = "scatter", mode = "lines+markers", name = x$code[1],
                     line = list(color = x$colour[1], dash = x$dash[1], width = 2),
                     marker = list(size = 5, color = x$colour[1]), text = fmt_lap(x$sec),
                     hovertemplate = paste0("<b>", dn, "</b><br>Lap %{x}: %{text}<extra></extra>"))
    }
    pw_layout(p, xtitle = "Lap", ytitle = "Lap time (s)")
  })

  output$rr_pits <- renderPlotly({
    e <- rr_e()
    P <- rr_d()$pits
    validate(need(nrow(P) > 0, "No pit stop data for this race (pit stops are recorded from 2011)"))
    P <- merge(P, e[, .(session_entry_id = id, code, driver, colour)], by = "session_entry_id")
    ord <- e$code[e$code %in% P$code]
    plot_ly(P, x = ~lap, y = ~factor(code, levels = rev(ord)), type = "scatter", mode = "markers",
            marker = list(size = ~pmin(pmax(sec, 15), 45) / 1.5, color = ~colour, opacity = 0.9,
                          line = list(color = "#000", width = 1)),
            text = ~sprintf("%s · stop %d · %.3f s", driver, number, sec),
            hovertemplate = "%{text}<br>Lap %{x}<extra></extra>") |>
      pw_layout(xtitle = "Lap", legend = FALSE, yaxis = list(title = list(text = NULL)))
  })

  output$rr_class <- renderDT({
    e <- rr_e()
    d <- e[, .(Pos = fifelse(is.na(position), "–", as.character(position)), Driver = driver, Team = team,
               Grid = grid, Laps = laps_completed,
               `Time / status` = fifelse(is.na(time) | time == "", fcoalesce(detail, ""), time),
               Points = points)]
    pw_dt(d, mono_cols = c(6, 7), page = 30)
  })

  # ---- Timing Screen (OpenF1) ----
  observe({
    m <- of1_list()
    yrs <- sort(unique(m$year), decreasing = TRUE)
    sel <- isolate(input$of_year)
    if (is.null(sel) || !sel %in% yrs) sel <- yrs[1]
    updateSelectInput(session, "of_year", choices = yrs, selected = sel)
  })
  observe({
    req(input$of_year)
    m <- of1_list()[year == as.integer(input$of_year)]
    sel <- isolate(input$of_meeting)
    if (is.null(sel) || !sel %in% m$dir) sel <- tail(m$dir[!grepl("Testing", m$name)], 1)
    lab <- paste(format(as.Date(substr(m$date_start, 1, 10)), "%d %b"), "·", m$name)
    updateSelectInput(session, "of_meeting", choices = setNames(m$dir, lab), selected = sel)
  })
  of_sessions <- reactive({
    req(input$of_meeting)
    read_of1(input$of_meeting, "sessions")
  })
  observeEvent(of_sessions(), {
    s <- of_sessions()
    req(nrow(s) > 0)
    sel <- if ("Race" %in% s$session_name) s$session_key[s$session_name == "Race"] else tail(s$session_key, 1)
    updateSelectInput(session, "of_session", choices = setNames(s$session_key, s$session_name), selected = sel)
  })
  of_s <- reactive({
    req(input$of_session)
    sk <- as.integer(input$of_session)
    req(sk %in% of_sessions()$session_key)
    eps <- c("drivers", "laps", "stints", "weather", "race_control", "team_radio", "position", "session_result")
    out <- setNames(lapply(eps, function(e) read_of1_session(input$of_meeting, sk, e)), eps)
    drv <- unique(out$drivers, by = "driver_number")
    validate(need(nrow(drv) > 0, "No driver list for this session yet"))
    drv[, colour := hex(team_colour)]
    res <- out$session_result
    drv[, ord := if (nrow(res)) res$position[match(driver_number, res$driver_number)] else NA_integer_]
    out$drv <- drv[order(fcoalesce(as.numeric(ord), 99), driver_number)]
    out
  })
  acr <- function(drv, n) drv$name_acronym[match(n, drv$driver_number)]

  output$of_tyres <- renderPlotly({
    S <- of_s()
    st <- copy(S$stints)
    validate(need(nrow(st) > 0, "No tyre stint data for this session"))
    st[, comp := compound(compound)]
    maxlap <- max(c(st$lap_end, S$laps$lap_number, 1), na.rm = TRUE)
    st[is.na(lap_end), lap_end := maxlap]
    st[is.na(lap_start), lap_start := 1L]
    st[, who := acr(S$drv, driver_number)]
    st <- st[!is.na(who)]
    p <- plot_ly()
    for (cp in names(TYRE_COL)) {
      d <- st[comp == cp]
      if (!nrow(d)) next
      p <- add_bars(p, y = d$who, x = d$lap_end - d$lap_start + 1, base = d$lap_start - 1, orientation = "h",
                    name = tools::toTitleCase(tolower(cp)), textposition = "none",
                    marker = list(color = TYRE_COL[[cp]], line = list(color = "#0b0d10", width = 2)),
                    text = sprintf("%s · laps %d–%d · %s (%s laps old at start)", d$who, d$lap_start, d$lap_end,
                                   tolower(cp), d$tyre_age_at_start),
                    hoverinfo = "text")
    }
    pw_layout(p, xtitle = "Lap", barmode = "overlay", legend = FALSE,
              yaxis = list(categoryorder = "array", categoryarray = rev(S$drv$name_acronym), title = list(text = NULL)),
              margin = list(l = 45, r = 10, t = 10, b = 40))
  })

  output$of_laps <- renderPlotly({
    S <- of_s()
    L <- S$laps
    validate(need(nrow(L) > 0 && "lap_duration" %in% names(L), "No lap times for this session"))
    L <- L[!is.na(lap_duration)]
    if (isTRUE(input$of_clean)) L <- L[lap_duration <= 1.07 * min(lap_duration) & !(is_pit_out_lap %in% TRUE)]
    p <- plot_ly()
    for (i in seq_len(nrow(S$drv))) {
      d <- L[driver_number == S$drv$driver_number[i]]
      if (!nrow(d)) next
      p <- add_trace(p, x = d$lap_number, y = d$lap_duration, type = "scatter", mode = "markers",
                     name = S$drv$name_acronym[i], text = fmt_lap(d$lap_duration),
                     marker = list(color = S$drv$colour[i], size = 7, line = list(color = "#000", width = 1)),
                     hovertemplate = paste0("<b>", S$drv$name_acronym[i], "</b> lap %{x}: %{text}<extra></extra>"))
    }
    pw_layout(p, xtitle = "Lap", ytitle = "Lap time (s)")
  })

  output$of_pos <- renderPlotly({
    S <- of_s()
    P <- copy(S$position)
    validate(need(nrow(P) > 0, "No running order data for this session"))
    P[, t := of1_time(date)]
    end <- max(P$t, na.rm = TRUE)
    p <- plot_ly()
    for (i in seq_len(nrow(S$drv))) {
      d <- P[driver_number == S$drv$driver_number[i]][order(t)]
      if (!nrow(d)) next
      d <- rbind(d, copy(d[.N])[, t := end])
      p <- add_trace(p, x = d$t, y = d$position, type = "scatter", mode = "lines", name = S$drv$name_acronym[i],
                     line = list(shape = "hv", color = S$drv$colour[i], width = 2),
                     hovertemplate = paste0("<b>", S$drv$name_acronym[i], "</b> P%{y}<extra></extra>"))
    }
    pw_layout(p, xtitle = "Session time (UTC)", ytitle = "Position", yaxis = list(autorange = "reversed", dtick = 1))
  })

  output$of_result <- renderDT({
    S <- of_s()
    R <- S$session_result
    validate(need(nrow(R) > 0, "No result for this session"))
    fmt_time <- function(v) {
      if (is.list(v)) return(vapply(v, function(z) paste(ifelse(is.na(z), "–", fmt_lap(as.numeric(z))), collapse = " / "), ""))
      fmt_lap(as.numeric(v))
    }
    fmt_gap <- function(v) {
      one <- function(z) {
        n <- suppressWarnings(as.numeric(z))
        ifelse(is.na(z), "–", ifelse(is.na(n), as.character(z), ifelse(n == 0, "", sprintf("+%.3f", n))))
      }
      if (is.list(v)) vapply(v, function(z) paste(one(z), collapse = " / "), "") else one(v)
    }
    flag <- function(col) if (col %in% names(R)) R[[col]] %in% TRUE else rep(FALSE, nrow(R))
    d <- data.table(Pos = R$position, Driver = acr(S$drv, R$driver_number),
                    Laps = R$number_of_laps, Time = fmt_time(R$duration), Gap = fmt_gap(R$gap_to_leader),
                    Status = fifelse(flag("dsq"), "DSQ", fifelse(flag("dns"), "DNS", fifelse(flag("dnf"), "DNF", ""))))
    d <- d[order(is.na(Pos), Pos)]
    d[, Pos := fifelse(is.na(Pos), "–", as.character(Pos))]
    pw_dt(d, mono_cols = c(4, 5), page = 25)
  })

  output$of_weather <- renderPlotly({
    W <- copy(of_s()$weather)
    validate(need(nrow(W) > 0, "No weather data for this session"))
    W[, t := of1_time(date)]
    W <- W[order(t)]
    p <- plot_ly(W, x = ~t) |>
      add_lines(y = ~track_temperature, name = "Track °C", line = list(color = "#e10600", width = 2.5)) |>
      add_lines(y = ~air_temperature, name = "Air °C", line = list(color = "#ffd200", width = 2)) |>
      add_lines(y = ~humidity, name = "Humidity %", yaxis = "y2", line = list(color = "#2a7fff", width = 1.5, dash = "dot"))
    rain <- W[rainfall > 0]
    if (nrow(rain)) p <- add_markers(p, data = rain, x = ~t, y = ~track_temperature, name = "Rain",
                                     marker = list(color = "#2a7fff", symbol = "triangle-down", size = 9))
    pw_layout(p, xtitle = "Time (UTC)", ytitle = "°C", legend = list(orientation = "h", y = 1.12),
              yaxis2 = c(AX, list(overlaying = "y", side = "right", showgrid = FALSE, title = list(text = "Humidity %"))),
              margin = list(l = 50, r = 55, t = 30, b = 40))
  })

  observeEvent(of_s(), {
    d <- of_s()$drv
    updateSelectInput(session, "of_radio_drv", choices = c("All drivers" = "all", setNames(d$driver_number, d$name_acronym)))
  })
  output$of_radio <- renderUI({
    S <- of_s()
    R <- copy(S$team_radio)
    if (!nrow(R)) return(div(class = "pw-empty", "No team radio for this session"))
    sel <- input$of_radio_drv
    if (!is.null(sel) && sel != "all") R <- R[driver_number == as.integer(sel)]
    R <- tail(R[order(date)], 60)
    if (!nrow(R)) return(div(class = "pw-empty", "No team radio for this driver"))
    div(class = "pw-radio-list", lapply(seq_len(nrow(R)), function(i) {
      n <- R$driver_number[i]
      div(class = "pw-radio", style = sprintf("--tc:%s", fcoalesce(S$drv$colour[match(n, S$drv$driver_number)], "#e10600")),
          span(class = "t", substr(R$date[i], 12, 19)), span(class = "d", acr(S$drv, n)),
          tags$audio(src = R$recording_url[i], controls = NA, preload = "none"))
    }))
  })

  output$of_rc <- renderDT({
    R <- of_s()$race_control
    validate(need(nrow(R) > 0, "No race control messages for this session"))
    d <- R[order(date), .(Time = substr(date, 12, 19), Lap = lap_number, Category = category, Flag = flag, Message = message)]
    flags <- c("GREEN", "YELLOW", "DOUBLE YELLOW", "RED", "BLUE", "CHEQUERED", "CLEAR", "BLACK AND WHITE")
    cols <- c("#2fb84a", "#ffd200", "#ffd200", "#ff2a2a", "#2a7fff", "#ffffff", "#2fb84a", "#ffffff")
    pw_dt(d, pos_col = NULL, mono_cols = 1, page = 10) |>
      formatStyle("Flag", color = styleEqual(flags, cols), fontWeight = "bold")
  })

  # ---- Telemetry (TracingInsights) ----
  observeEvent(input$ti_event, {
    s <- ti_sessions(input$ti_event)
    updateSelectInput(session, "ti_session", choices = s, selected = if ("Qualifying" %in% s) "Qualifying" else tail(s, 1))
  })
  ti_drivers <- reactive({
    req(input$ti_event, input$ti_session)
    base <- file.path(TI_DIR, input$ti_event, input$ti_session)
    x <- safe_json(file.path(base, "drivers.json"))
    validate(need(!is.null(x), "No driver list for this session"))
    d <- as.data.table(x$drivers)
    d <- d[exists_dir(file.path(base, driver))]
    d[, best := vapply(driver, function(v) suppressWarnings(min(ti_laps(input$ti_event, input$ti_session, v)$time, na.rm = TRUE)), 0)]
    d[, colour := hex(tc)]
    d[order(best)]
  })
  observeEvent(ti_drivers(), {
    d <- ti_drivers()
    ch <- setNames(d$driver, sprintf("%s · %s %s", d$driver, d$fn, d$ln))
    updateSelectInput(session, "ti_drvA", choices = ch, selected = d$driver[1])
    updateSelectInput(session, "ti_drvB", choices = ch, selected = d$driver[min(2, nrow(d))])
  })
  lap_choices <- function(drv) {
    ev <- input$ti_event; s <- input$ti_session
    L <- ti_laps(ev, s, drv)
    if (!nrow(L)) return(NULL)
    L <- L[!is.na(time) & exists_file(file.path(TI_DIR, ev, s, drv, paste0(lap, "_tel.json")))]
    if (!nrow(L)) return(NULL)
    ok <- L[!(del %in% TRUE)]
    best <- if (nrow(ok)) ok[which.min(time), lap] else L[which.min(time), lap]
    lab <- sprintf("Lap %d · %s · %s%s", L$lap, fmt_lap(L$time), tolower(compound(L$compound)),
                   ifelse(L$lap == best, "  ★ fastest", ""))
    list(choices = setNames(L$lap, lab), best = best)
  }
  observeEvent(list(input$ti_drvA, input$ti_session), {
    req(input$ti_drvA)
    lc <- lap_choices(input$ti_drvA)
    updateSelectInput(session, "ti_lapA", choices = lc$choices, selected = lc$best)
  })
  observeEvent(list(input$ti_drvB, input$ti_session), {
    req(input$ti_drvB)
    lc <- lap_choices(input$ti_drvB)
    updateSelectInput(session, "ti_lapB", choices = lc$choices, selected = lc$best)
  })

  ti_pair <- reactive({
    req(input$ti_drvA, input$ti_drvB, input$ti_lapA, input$ti_lapB)
    A <- ti_tel(input$ti_event, input$ti_session, input$ti_drvA, input$ti_lapA)
    B <- ti_tel(input$ti_event, input$ti_session, input$ti_drvB, input$ti_lapB)
    validate(need(!is.null(A) && !is.null(B) && nrow(A) > 10 && nrow(B) > 10, "No telemetry for this lap"))
    d <- ti_drivers()
    colA <- fcoalesce(d$colour[d$driver == input$ti_drvA][1], "#e10600")
    colB <- fcoalesce(d$colour[d$driver == input$ti_drvB][1], "#ffd200")
    if (colA == colB) colB <- "#ffffff"
    list(A = A, B = B, colA = colA, colB = colB,
         la = paste0(input$ti_drvA, " L", input$ti_lapA), lb = paste0(input$ti_drvB, " L", input$ti_lapB))
  })

  output$ti_trace <- renderPlotly({
    x <- ti_pair()
    telemetry_plot(x$A, x$B, x$la, x$lb, x$colA, if (input$ti_drvA == input$ti_drvB) x$colA else x$colB)
  })

  output$ti_map_plot <- renderPlotly({
    x <- ti_pair()
    cor <- safe_json(file.path(TI_DIR, input$ti_event, input$ti_session, "corners.json"))
    rot <- if (!is.null(cor$Rotation)) as.numeric(cor$Rotation[1]) else 0
    track_map(x$A, x$B, x$la, x$lb, x$colA, x$colB, rot, cor, mode = input$ti_map)
  })

  output$ti_lapplot <- renderPlotly({
    x <- ti_pair()
    p <- plot_ly()
    for (w in c("A", "B")) {
      drv <- input[[paste0("ti_drv", w)]]
      if (w == "B" && drv == input$ti_drvA) next
      L <- ti_laps(input$ti_event, input$ti_session, drv)[!is.na(time)]
      if (!nrow(L)) next
      L <- L[time <= min(time) * 1.12]
      col <- if (w == "A") x$colA else x$colB
      p <- add_trace(p, x = L$lap, y = L$time, type = "scatter", mode = "lines+markers", name = drv,
                     line = list(color = col, width = 1.5),
                     marker = list(color = unname(TYRE_COL[compound(L$compound)]), size = 8, line = list(color = col, width = 2)),
                     text = sprintf("%s · %s", fmt_lap(L$time), tolower(compound(L$compound))),
                     hovertemplate = paste0("<b>", drv, "</b> lap %{x}: %{text}<extra></extra>"))
    }
    pw_layout(p, xtitle = "Lap", ytitle = "Lap time (s)", margin = list(l = 55, r = 10, t = 10, b = 40))
  })

  # ---- Circuits ----
  output$circ_map <- renderLeaflet({
    cen <- rbindlist(lapply(CIRCUITS, function(c) data.table(id = c$id, name = c$name, location = c$location,
                                                              lng = mean(range(c$lng)), lat = mean(range(c$lat)),
                                                              firstgp = c$firstgp, len = c$length)))
    # Esri dark grey canvas: no API key needed (CARTO's dark tiles now require one)
    m <- leaflet(options = leafletOptions(worldCopyJump = TRUE)) |>
      addTiles("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
               attribution = "Tiles &copy; Esri", options = tileOptions(maxZoom = 16)) |>
      addTiles("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
               options = tileOptions(maxZoom = 16))
    for (c in CIRCUITS) m <- addPolylines(m, lng = c$lng, lat = c$lat, color = "#e10600", weight = 3, opacity = 0.95,
                                          layerId = c$id, label = c$name)
    m |>
      addCircleMarkers(data = cen, lng = ~lng, lat = ~lat, layerId = ~paste0("m_", id), radius = 5,
                       color = "#000", weight = 1, fillColor = "#ffd200", fillOpacity = 0.95, label = ~name,
                       popup = ~sprintf("<b>%s</b><br>%s<br>First GP: %s<br>Lap: %s m", name, location, firstgp, num(len))) |>
      setView(lng = 15, lat = 30, zoom = 2)
  })
  observeEvent(input$circ_map_marker_click, {
    updateSelectInput(session, "circ_id", selected = sub("^m_", "", input$circ_map_marker_click$id))
  })
  observeEvent(input$circ_map_shape_click, {
    updateSelectInput(session, "circ_id", selected = input$circ_map_shape_click$id)
  })
  observeEvent(input$circ_id, {
    c <- CIRCUITS[[input$circ_id]]
    leafletProxy("circ_map") |> flyToBounds(min(c$lng), min(c$lat), max(c$lng), max(c$lat))
  }, ignoreInit = TRUE)

  output$circ_info <- renderUI({
    c <- CIRCUITS[[req(input$circ_id)]]
    f <- circuit_f1db(input$circ_id)
    kv <- function(k, v) if (length(v) && !is.na(v)) tagList(tags$dt(k), tags$dd(v))
    tagList(
      h3(class = "pw-circuit-name", c$name),
      tags$dl(class = "pw-kv",
              kv("Location", c$location), kv("Opened", c$opened), kv("First GP", c$firstgp),
              kv("Lap length", if (length(c$length)) paste(num(c$length), "m")),
              kv("Altitude", if (length(c$altitude)) paste(c$altitude, "m")),
              if (!is.null(f)) tagList(kv("Races held", f$totalRacesHeld), kv("Turns", f$turns),
                                       kv("Type", tools::toTitleCase(tolower(f$type))),
                                       kv("Direction", tolower(gsub("_", " ", f$direction))))),
      if (!is.null(f)) h4(style = "font-size:.85rem;color:#8d95a1;margin:4px 0 6px", "Winners here"))
  })
  output$circ_winners <- renderDT({
    f <- circuit_f1db(req(input$circ_id))
    validate(need(!is.null(f), "No race history matched for this circuit"))
    w <- DB$results[raceId %in% DB$races[circuitId == f$id, id] & positionNumber == 1][order(-year)]
    d <- w[, .(Year = year, Winner = unname(drv_name[driverId]), Team = unname(con_name[constructorId]))]
    pw_dt(d, pos_col = NULL, mono_cols = 1, page = 8)
  })

  output$tum_plot <- renderPlotly({
    req(input$tum_track)
    t <- tum_track(input$tum_track)
    tr <- t$track
    n <- nrow(tr)
    dx <- c(tr$x[-1], tr$x[1]) - c(tr$x[n], tr$x[-n])
    dy <- c(tr$y[-1], tr$y[1]) - c(tr$y[n], tr$y[-n])
    len <- sqrt(dx^2 + dy^2)
    tx <- dx / len; ty <- dy / len
    loop <- function(v) c(v, v[1])
    p <- plot_ly() |>
      add_lines(x = loop(tr$x - ty * tr$wl), y = loop(tr$y + tx * tr$wl), name = "Track edges", legendgroup = "e",
                line = list(color = "#d9dde3", width = 1.5), hoverinfo = "skip") |>
      add_lines(x = loop(tr$x + ty * tr$wr), y = loop(tr$y - tx * tr$wr), name = "Track edges", legendgroup = "e",
                showlegend = FALSE, line = list(color = "#d9dde3", width = 1.5), hoverinfo = "skip") |>
      add_lines(x = loop(tr$x), y = loop(tr$y), name = "Centre line",
                line = list(color = "#4a5059", width = 1, dash = "dot"), hoverinfo = "skip")
    if (!is.null(t$raceline)) {
      rl <- t$raceline
      p <- add_lines(p, x = loop(rl$x), y = loop(rl$y), name = "Minimum-curvature racing line",
                     line = list(color = "#e10600", width = 2.5), hoverinfo = "skip")
    }
    pw_layout(p, xaxis = list(visible = FALSE), yaxis = list(visible = FALSE, scaleanchor = "x"),
              legend = list(orientation = "h", x = 0, y = 1.04))
  })

  # ---- Rulebook ----
  output$fia_view <- renderUI({
    req(input$fia_doc)
    src <- fia_src(input$fia_doc)
    # The web edition runs in a sandboxed frame that cannot show another site's PDF, so it links out
    if (IS_WEB) {
      return(div(class = "pw-doclinks",
                 p("These documents open on fia.com in a new tab."),
                 lapply(names(FIA_PDFS), function(lab)
                   a(class = if (FIA_PDFS[[lab]] == input$fia_doc) "pw-doc active" else "pw-doc",
                     href = FIA_PDFS[[lab]], target = "_blank", rel = "noopener", lab))))
    }
    tagList(tags$iframe(class = "pw-pdf", src = src),
            p(style = "margin:8px 0 0", a(href = src, target = "_blank", "Open the PDF in a new tab")))
  })
}

shinyApp(ui, server)
