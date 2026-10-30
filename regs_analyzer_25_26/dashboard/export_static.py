"""Static export of the dashboard, for GitHub Pages.

GitHub Pages only serves static files, while a Dash app needs a Python server. Every chart in this
dashboard comes from the precomputed results/, though, so the pages can be rendered ahead of time:

  1. walk the same Dash layout the live app uses (app.PAGES) and write it out as plain HTML;
  2. save every figure as JSON, one file per tab, including one figure set per dropdown option
     (from app.DYNAMIC, the same table the live callbacks use);
  3. add a small script that switches tabs and dropdown options in the browser.

The result looks and reads like the live app; only the server is gone.

Usage:  python regs_analyzer_25_26/dashboard/export_static.py OUT_DIR
"""
import html as H
import json
import re
import shutil
import sys
from pathlib import Path

import plotly
import plotly.io as pio

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import app as live  # noqa: E402  (builds the layout and figures; does not start a server)
import theme  # noqa: E402

REPO_URL = "https://github.com/schneiderweisse/Shiny-F1"
BRANCH = "regs_analyzer_25_26"   # this study lives on its own branch; main holds the Shiny app
SOURCE_URL = f"{REPO_URL}/tree/{BRANCH}"
REPORT_URL = f"{REPO_URL}/blob/{BRANCH}/regs_analyzer_25_26/REPORT.md"


class Page:
    """Collects the figures of one tab while its layout is rendered."""

    def __init__(self, key):
        self.key, self.figs, self.dyn, self.n = key, {}, {}, 0


def fig_json(fig):
    return json.loads(pio.to_json(fig, validate=False))


def css_name(k):
    return re.sub(r"([A-Z])", lambda m: "-" + m.group(1).lower(), k)


def attrs(props):
    out = []
    for k, v in props.items():
        if k == "children" or v is None:
            continue
        if k == "className":
            out.append(f'class="{H.escape(v)}"')
        elif k == "style" and isinstance(v, dict):
            css = "; ".join(f"{css_name(a)}: {b}px" if isinstance(b, (int, float)) else f"{css_name(a)}: {b}" for a, b in v.items())
            out.append(f'style="{H.escape(css)}"')
        elif k in ("id", "href", "target", "rel", "title"):
            out.append(f'{k}="{H.escape(str(v))}"')
    if props.get("target") == "_blank" and "rel" not in props:
        out.append('rel="noopener"')
    return (" " + " ".join(out)) if out else ""


def markdown(text):
    """The few Markdown features the dashboard uses: paragraphs, **bold**, *italic* and `code`."""
    paras = []
    for p in re.split(r"\n\s*\n", text.strip()):
        s = H.escape(p.strip())
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"\*(\S.*?\S|\S)\*", r"<em>\1</em>", s)
        s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
        paras.append(f"<p>{s.replace(chr(10), ' ')}</p>")
    return "".join(paras)


def render(c, page, slots=None):
    """Dash component tree -> HTML string. Figures are collected on `page`."""
    if c is None or c is False:
        return ""
    if isinstance(c, (list, tuple)):
        return "".join(render(x, page, slots) for x in c)
    if isinstance(c, (str, int, float)):
        return H.escape(str(c))
    j = c.to_plotly_json()
    t, ns, props = j["type"], j["namespace"], j["props"]
    if slots and props.get("id") in slots:          # placeholders filled by the exporter (the page area)
        return slots[props["id"]]
    if ns == "dash_html_components":
        tag = t.lower()
        return f"<{tag}{attrs(props)}>{render(props.get('children'), page, slots)}</{tag}>"
    if t == "Graph":
        gid = props.get("id") or f"{page.key}-fig{page.n}"
        page.n += 1
        if props.get("figure") is not None:
            page.figs[gid] = fig_json(props["figure"])
        return f'<div class="gh-graph" id="{H.escape(gid)}"></div>'
    if t == "Dropdown":
        dd, options, value = props["id"], props["options"], props.get("value")
        graphs, build = live.DYNAMIC[dd]
        page.dyn[dd] = {"outputs": graphs, "values": {str(o["value"]): [fig_json(f) for f in build(o["value"])] for o in options}}
        opts = "".join(f'<option value="{H.escape(str(o["value"]))}"{" selected" if o["value"] == value else ""}>{H.escape(o["label"])}</option>'
                       for o in options)
        return f'<select class="gh-select" id="{H.escape(dd)}"{attrs({"style": props.get("style")})}>{opts}</select>'
    if t == "Markdown":
        return f'<div{attrs({"className": props.get("className")})}>{markdown(props.get("children") or "")}</div>'
    if t == "Tabs":
        links = "".join(f'<a class="gh-tab" href="#{tab.value}" data-page="{tab.value}">{H.escape(tab.label)}</a>' for tab in props["children"])
        return f'<nav class="gh-tabs" aria-label="Dashboard sections">{links}</nav>'
    raise ValueError(f"No static renderer for {ns}.{t}")


STATIC_CSS = """
/* Additions for the static export (the live app gets these from Dash components) */
.gh-graph { width: 100%; min-height: 120px; }
a.gh-tab { display: inline-block; text-decoration: none !important; }
select.gh-select { background: var(--bg-subtle); color: var(--fg); border: 1px solid var(--border); border-radius: 6px;
                   padding: 5px 28px 5px 12px; font: inherit; max-width: 100%; }
select.gh-select:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.gh-links { display: flex; flex-wrap: wrap; gap: 4px 16px; font-size: 12px; color: var(--fg-muted); margin: -4px 0 12px; }
.page[hidden] { display: none !important; }
.gh-loading { color: var(--fg-muted); font-size: 12px; padding: 24px; }
"""

APP_JS = """// Static version of the regs_analyzer_25_26 dashboard: tab switching, per-tab figure loading, dropdowns.
const CONFIG = Object.assign(%CONFIG%, { responsive: true });
const cache = {};

function load(key) {
  if (!cache[key]) cache[key] = fetch(`data/${key}.json`).then(r => r.json());
  return cache[key];
}

function draw(id, fig) {
  const el = document.getElementById(id);
  if (el) Plotly.react(el, fig.data, fig.layout, CONFIG);
}

async function show(key) {
  document.querySelectorAll('.page').forEach(s => { s.hidden = s.dataset.page !== key; });
  document.querySelectorAll('.gh-tab').forEach(a => a.classList.toggle('gh-tab--selected', a.dataset.page === key));
  const d = await load(key);
  for (const [id, fig] of Object.entries(d.figs)) draw(id, fig);
  for (const [dd, spec] of Object.entries(d.dyn)) {
    const sel = document.getElementById(dd);
    const update = () => spec.values[sel.value].forEach((fig, i) => draw(spec.outputs[i], fig));
    sel.onchange = update;
    update();
  }
}

const keys = [...document.querySelectorAll('.page')].map(s => s.dataset.page);
const route = () => { const k = location.hash.slice(1); show(keys.includes(k) ? k : keys[0]); };
window.addEventListener('hashchange', route);
route();
"""


def main(out: Path) -> None:
    out = out.resolve()
    if out.exists():
        shutil.rmtree(out)
    (out / "data").mkdir(parents=True)

    sections = []
    for key, (label, build) in live.PAGES.items():
        page = Page(key)
        body = render(build(), page)
        sections.append(f'<section class="page" id="page-{key}" data-page="{key}" hidden aria-label="{H.escape(label)}">{body}</section>')
        (out / "data" / f"{key}.json").write_text(json.dumps({"figs": page.figs, "dyn": page.dyn}, separators=(",", ":")), encoding="utf-8")
        print(f"{label:<16} {len(page.figs):>2} figures, {sum(len(v['values']) * len(v['outputs']) for v in page.dyn.values()):>3} dropdown figures")

    body = render(live.app.layout, Page("layout"), slots={"page": "".join(sections)})
    links = (f'<p class="gh-links"><a href="{SOURCE_URL}">Source code</a><a href="{REPORT_URL}">Full report</a>'
             '<span>Static export of the Dash app: every chart is precomputed.</span></p>')
    body = body.replace('<nav class="gh-tabs"', links + '<nav class="gh-tabs"', 1)
    (out / "index.html").write_text(
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>regs_analyzer_25_26</title>\n"
        '<meta name="description" content="How the 2026 Formula 1 rules changed the cars: 2025 vs 2026 on seven circuits.">\n'
        '<link rel="stylesheet" href="github.css">\n<link rel="stylesheet" href="static.css">\n'
        '<script src="plotly.min.js"></script>\n</head>\n<body>\n' + body +
        '\n<script src="app.js"></script>\n</body>\n</html>\n', encoding="utf-8")
    shutil.copy(HERE / "assets" / "github.css", out / "github.css")
    (out / "static.css").write_text(STATIC_CSS, encoding="utf-8")
    (out / "app.js").write_text(APP_JS.replace("%CONFIG%", json.dumps(theme.CONFIG)), encoding="utf-8")
    shutil.copy(Path(plotly.__file__).parent / "package_data" / "plotly.min.js", out / "plotly.min.js")
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) / 1e6
    print(f"Wrote {out} ({size:.1f} MB)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python export_static.py OUT_DIR")
    main(Path(sys.argv[1]))
