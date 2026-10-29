"""Plotly template matching the GitHub-dark CSS."""
import plotly.graph_objects as go
import plotly.io as pio

BG = "#0d1117"
FG = "#e6edf3"
MUTED = "#7d8590"
GRID = "#21262d"
BORDER = "#30363d"
ACCENT = "#4493f8"
GREEN = "#3fb950"
RED = "#f85149"
YELLOW = "#d29922"
PURPLE = "#a371f7"
Y2025 = "#58a6ff"
Y2026 = "#f0883e"
YEAR = {2025: Y2025, 2026: Y2026}
FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif'
MONO = 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace'

pio.templates["github_dark"] = go.layout.Template(
    layout=dict(
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family=FONT, color=FG, size=12),
        colorway=[Y2025, Y2026, GREEN, PURPLE, RED, YELLOW, "#39c5cf", "#8b949e"],
        xaxis=dict(gridcolor=GRID, zerolinecolor=BORDER, linecolor=BORDER, tickfont=dict(family=MONO, color=MUTED, size=11),
                   title=dict(font=dict(color=MUTED, size=12))),
        yaxis=dict(gridcolor=GRID, zerolinecolor=BORDER, linecolor=BORDER, tickfont=dict(family=MONO, color=MUTED, size=11),
                   title=dict(font=dict(color=MUTED, size=12))),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=FG, size=12), orientation="h", x=0, y=1.08),
        hoverlabel=dict(bgcolor="#161b22", bordercolor=BORDER, font=dict(family=MONO, color=FG, size=12)),
        margin=dict(l=56, r=16, t=32, b=44),
    )
)
pio.templates.default = "github_dark"

CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"]}


def rgba(hex_colour: str, alpha: float) -> str:
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"
