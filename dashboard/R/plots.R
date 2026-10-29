# Plot styling and chart builders shared by the tabs.

AX <- list(gridcolor = "#242930", zerolinecolor = "#3a4048", linecolor = "#3a4048",
           tickfont = list(family = "Share Tech Mono, monospace", size = 11, color = "#a9b0ba"))

# legend: TRUE/FALSE to show or hide it, or a list of legend settings
pw_layout <- function(p, xtitle = NULL, ytitle = NULL, xaxis = list(), yaxis = list(), legend = TRUE,
                      margin = list(l = 55, r = 20, t = 15, b = 45), ...) {
  leg <- list(bgcolor = "rgba(0,0,0,0)", font = list(size = 12))
  if (is.list(legend)) leg <- modifyList(leg, legend)
  p |>
    layout(
      paper_bgcolor = "rgba(0,0,0,0)", plot_bgcolor = "rgba(0,0,0,0)",
      font = list(family = "Barlow Semi Condensed, Arial Narrow, sans-serif", color = "#dfe3e8", size = 13),
      xaxis = modifyList(c(AX, list(title = list(text = xtitle))), xaxis),
      yaxis = modifyList(c(AX, list(title = list(text = ytitle))), yaxis),
      showlegend = !isFALSE(legend), legend = leg,
      hoverlabel = list(bgcolor = "#000", bordercolor = "#e10600",
                        font = list(family = "Share Tech Mono, monospace", color = "#ffd200")),
      margin = margin, ...
    ) |>
    config(displaylogo = FALSE, modeBarButtonsToRemove = c("lasso2d", "select2d", "autoScale2d"))
}

empty_plot <- function(msg) {
  plot_ly(type = "scatter", mode = "markers") |>
    pw_layout(xaxis = list(visible = FALSE), yaxis = list(visible = FALSE), legend = FALSE,
              annotations = list(list(text = msg, showarrow = FALSE, xref = "paper", yref = "paper",
                                      x = 0.5, y = 0.5, font = list(family = "Share Tech Mono", color = "#8d95a1", size = 14))))
}

hbar_leaders <- function(d, label, value, unit = "") {
  d <- d[order(-get(value))][seq_len(min(15, .N))]
  d[, lab := get(label)]
  d[, val := get(value)]
  cols <- c(PODIUM, rep("#e10600", max(0, nrow(d) - 3)))[seq_len(nrow(d))]
  plot_ly(d, y = ~factor(lab, levels = rev(lab)), x = ~val, type = "bar", orientation = "h",
          marker = list(color = cols, line = list(color = "#000", width = 1)),
          text = ~format(val, big.mark = ","), textposition = "outside",
          textfont = list(family = "Share Tech Mono", color = "#ffd200"),
          hovertemplate = paste0("%{y}: %{x:,}", unit, "<extra></extra>")) |>
    pw_layout(legend = FALSE, yaxis = list(title = list(text = NULL)),
              xaxis = list(title = list(text = NULL), showgrid = FALSE, showticklabels = FALSE),
              margin = list(l = 150, r = 50, t = 10, b = 10))
}

# Stacked bars of counts per year, keeping the top n groups and lumping the rest into "Other"
stacked_years <- function(d, group, value, top_n = 9, ytitle = NULL, labeller = identity) {
  d <- copy(d)
  setnames(d, c(group, value), c("g", "v"))
  top <- d[, .(t = sum(v)), by = g][order(-t)][seq_len(min(top_n, .N)), g]
  d[, g := fifelse(g %in% top, labeller(g), "Other")]
  d <- d[, .(v = sum(v)), by = .(year, g)]
  lv <- c(labeller(top), "Other")
  p <- plot_ly()
  for (i in seq_along(lv)) {
    dd <- d[g == lv[i]]
    if (!nrow(dd)) next
    p <- add_bars(p, data = dd, x = ~year, y = ~v, name = lv[i],
                  marker = list(color = if (lv[i] == "Other") "#4a5059" else PAL[(i - 1) %% length(PAL) + 1]),
                  hovertemplate = paste0("<b>", lv[i], "</b> %{x}: %{y}<extra></extra>"))
  }
  pw_layout(p, ytitle = ytitle, barmode = "stack", bargap = 0.12)
}

# Telemetry comparison: gap, speed, throttle, brake, gear, RPM against lap distance
telemetry_plot <- function(A, B, la, lb, colA, colB) {
  grid <- seq(0, min(max(A$distance), max(B$distance)), by = 5)
  ta <- approx(A$distance, A$time, grid, ties = mean, rule = 2)$y
  tb <- approx(B$distance, B$time, grid, ties = mean, rule = 2)$y
  panels <- list(
    list(v = "speed",    t = "Speed km/h"), list(v = "throttle", t = "Throttle %"),
    list(v = "brake",    t = "Brake"),      list(v = "gear",     t = "Gear"),
    list(v = "rpm",      t = "RPM"))
  plots <- list(
    plot_ly(x = grid, y = tb - ta, type = "scatter", mode = "lines", fill = "tozeroy",
            fillcolor = "rgba(255,210,0,0.12)", line = list(color = "#ffd200", width = 2), showlegend = FALSE,
            hovertemplate = paste0(lb, " vs ", la, ": %{y:+.3f}s<extra></extra>"))
  )
  for (i in seq_along(panels)) {
    v <- panels[[i]]$v
    shape <- if (v %in% c("gear", "brake")) "hv" else "linear"
    plots[[i + 1]] <- plot_ly() |>
      add_lines(data = A, x = ~distance, y = A[[v]], name = la, legendgroup = "A", showlegend = i == 1,
                line = list(color = colA, width = 2, shape = shape),
                hovertemplate = paste0(la, " %{y}<extra></extra>")) |>
      add_lines(data = B, x = ~distance, y = B[[v]], name = lb, legendgroup = "B", showlegend = i == 1,
                line = list(color = colB, width = 2, shape = shape, dash = if (colA == colB) "dot" else "solid"),
                hovertemplate = paste0(lb, " %{y}<extra></extra>"))
  }
  titles <- c(paste0("Gap s (+ = ", lb, " behind)"), vapply(panels, `[[`, "", "t"))
  s <- subplot(plots, nrows = 6, shareX = TRUE, heights = c(0.15, 0.27, 0.16, 0.1, 0.14, 0.18))
  axes <- list()
  for (k in 1:6) {
    nm <- if (k == 1) "" else k
    axes[[paste0("yaxis", nm)]] <- c(AX, list(title = list(text = titles[k], font = list(size = 10.5))))
    axes[[paste0("xaxis", nm)]] <- c(AX, list(title = list(text = if (k == 6) "Distance (m)" else NULL)))
  }
  s <- do.call(layout, c(list(s), axes))
  s |> layout(paper_bgcolor = "rgba(0,0,0,0)", plot_bgcolor = "rgba(0,0,0,0)", hovermode = "x unified",
              font = list(family = "Barlow Semi Condensed, sans-serif", color = "#dfe3e8"),
              legend = list(orientation = "h", x = 0, y = 1.06, bgcolor = "rgba(0,0,0,0)"),
              hoverlabel = list(bgcolor = "#000", font = list(family = "Share Tech Mono", color = "#ffd200")),
              margin = list(l = 70, r = 15, t = 30, b = 45)) |>
    config(displaylogo = FALSE)
}

rotate_xy <- function(x, y, deg) {
  a <- deg / 180 * pi
  list(x = x * cos(a) - y * sin(a), y = x * sin(a) + y * cos(a))
}

# Track map of driver A's lap, coloured by speed or by who was faster in each of n mini-sectors
track_map <- function(A, B, la, lb, colA, colB, rot, corners, mode = "delta", n = 25) {
  r <- rotate_xy(A$x, A$y, rot)
  A <- copy(A)[, `:=`(rx = r$x, ry = r$y)]
  p <- plot_ly()
  if (mode == "speed") {
    p <- add_trace(p, data = A, x = ~rx, y = ~ry, type = "scatter", mode = "markers",
                   marker = list(color = ~speed, size = 6,
                                 colorscale = list(c(0, "#2a7fff"), c(0.5, "#ffd200"), c(1, "#e10600")),
                                 colorbar = list(title = list(text = "km/h"), tickfont = list(color = "#a9b0ba"))),
                   hovertemplate = "%{marker.color:.0f} km/h<extra></extra>", showlegend = FALSE)
  } else {
    edges <- seq(0, min(max(A$distance), max(B$distance)), length.out = n + 1)
    da <- diff(approx(A$distance, A$time, edges, ties = mean, rule = 2)$y)
    db <- diff(approx(B$distance, B$time, edges, ties = mean, rule = 2)$y)
    A[, seg := findInterval(distance, edges, all.inside = TRUE)]
    shown <- c(A = FALSE, B = FALSE)
    for (k in seq_len(n)) {
      idx <- which(A$seg == k)
      if (!length(idx)) next
      idx <- c(idx, min(max(idx) + 1, nrow(A)))
      w <- if (da[k] <= db[k]) "A" else "B"
      p <- add_trace(p, x = A$rx[idx], y = A$ry[idx], type = "scatter", mode = "lines",
                     line = list(color = if (w == "A") colA else colB, width = 7),
                     name = if (w == "A") la else lb, legendgroup = w, showlegend = !shown[[w]],
                     hovertemplate = sprintf("Mini-sector %d: %s faster by %.3fs<extra></extra>",
                                             k, if (w == "A") la else lb, abs(da[k] - db[k])))
      shown[[w]] <- TRUE
    }
  }
  if (!is.null(corners) && length(corners$X)) {
    cr <- rotate_xy(corners$X, corners$Y, rot)
    p <- add_trace(p, x = cr$x, y = cr$y, type = "scatter", mode = "text",
                   text = paste0(corners$CornerNumber, fcoalesce(as.character(corners$CornerLetter), "")),
                   textfont = list(family = "Share Tech Mono", color = "#ffffff", size = 11),
                   hoverinfo = "skip", showlegend = FALSE)
  }
  pw_layout(p, xaxis = list(visible = FALSE), yaxis = list(visible = FALSE, scaleanchor = "x"),
            legend = list(orientation = "h", x = 0, y = 1.02))
}
