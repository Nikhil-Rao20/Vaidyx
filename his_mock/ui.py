"""Shared page shell for the mock hospital's human screens (the reporting desk 1.5 and the HIS screens 1.6): one CSS, one
layout, small HTML helpers. Plain Python strings, no template engine (the app venv has none). SYNTHETIC banner on every page.
No em dashes anywhere in the UI.
"""
import html

CSS = """
:root { --primary: #00c0b5; --accent: #009c94; --link: #046483; --ink: #1f2933; --body: #3e4c59; --muted: #52606d;
  --line: #d9e2ec; --bg: #f5f7fa; --panel: #ffffff; --tint: #e6f3f7; --ok: #1e6b45; --ok-s: #e5f4ec; --warn: #8a5300;
  --warn-s: #fdf1d8; --bad: #b23a2f; --bad-s: #fbe9e6; --radius: 10px; --mono: ui-monospace, "JetBrains Mono", monospace; }
* { box-sizing: border-box; }
body { margin: 0; font: 15px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: var(--body); background: var(--bg); }
header.top { background: var(--panel); border-bottom: 1px solid var(--line); padding: 10px 20px; display: flex; gap: 18px; align-items: center; flex-wrap: wrap; }
header.top .brand { font-weight: 700; color: var(--ink); font-size: 16px; }
header.top nav a { margin-right: 14px; color: var(--link); text-decoration: none; font-weight: 500; }
header.top nav a.active { color: var(--accent); border-bottom: 2px solid var(--primary); }
.synthetic { background: var(--warn-s); color: var(--warn); font-size: 12px; padding: 3px 8px; border-radius: 6px; font-weight: 600; letter-spacing: .02em; }
main { max-width: 1180px; margin: 20px auto; padding: 0 16px; overflow-x: hidden; }
.panel, main { min-width: 0; }
pre, .mono { white-space: pre-wrap; overflow-wrap: anywhere; }
h1 { font-size: 22px; color: var(--ink); margin: 0 0 14px; }
h2 { font-size: 17px; color: var(--ink); margin: 22px 0 8px; }
h3 { font-size: 15px; color: var(--ink); margin: 14px 0 6px; }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); padding: 14px 16px; margin-bottom: 14px; }
.scroll-x { overflow-x: auto; max-width: 100%; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: var(--muted); font-weight: 600; font-size: 12.5px; text-transform: uppercase; letter-spacing: .03em; }
.mono { font-family: var(--mono); font-size: 13px; }
.muted { color: var(--muted); }
.pill { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; }
.pill.ok { background: var(--ok-s); color: var(--ok); } .pill.warn { background: var(--warn-s); color: var(--warn); }
.pill.bad { background: var(--bad-s); color: var(--bad); } .pill.info { background: var(--tint); color: var(--link); }
form.inline { display: inline; }
label { display: block; font-size: 13px; color: var(--muted); margin: 8px 0 3px; }
input[type=text], input[type=date], select, textarea { width: 100%; max-width: 520px; padding: 7px 9px; border: 1px solid var(--line); border-radius: 7px; font: inherit; }
textarea { min-height: 70px; }
button, .btn { background: var(--primary); color: #0b1f24; border: 0; border-radius: 7px; padding: 7px 14px; font: inherit; font-weight: 600; cursor: pointer; text-decoration: none; display: inline-block; }
button.secondary, .btn.secondary { background: var(--tint); color: var(--link); }
button.danger, .btn.danger { background: var(--bad-s); color: var(--bad); }
.flash { padding: 10px 14px; border-radius: 8px; margin-bottom: 14px; }
.flash.ok { background: var(--ok-s); color: var(--ok); } .flash.bad { background: var(--bad-s); color: var(--bad); }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; }
dl { display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px; margin: 0; }
dt { color: var(--muted); font-size: 13px; } dd { margin: 0; }
footer { text-align: center; color: var(--muted); font-size: 12px; padding: 20px; }
@media (max-width: 640px) { header.top { padding: 8px 12px; } main { margin: 12px auto; } th, td { padding: 5px 6px; } }
"""

STATUS_PILL = {"ordered": "info", "scheduled": "info", "sample_collected": "info", "completed": "ok", "cancelled": "bad",
               "preliminary": "warn", "final": "ok", "amended": "ok", "requested": "warn", "accepted": "ok",
               "in-progress": "info", "finished": "muted", "available": "ok", "registered": "info"}


def esc(value):
    """HTML-escape any value (None -> empty)."""
    return html.escape("" if value is None else str(value), quote=True)


def page(title, body, *, nav=None, active=None, flash=None, hospital="Vaidyx Demo Hospital (SYNTHETIC)"):
    """A full HTML page: top bar with the hospital name, the SYNTHETIC pill and the navigation links [(label, href)]."""
    links = "".join(f'<a href="{esc(h)}"{" class=active" if l == active else ""}>{esc(l)}</a>' for l, h in (nav or []))
    msg = ""
    if flash:
        kind, text = flash if isinstance(flash, tuple) else ("ok", flash)
        msg = f'<div class="flash {esc(kind)}">{esc(text)}</div>'
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content=\"width=device-width, initial-scale=1\">"
            f"<title>{esc(title)} | {esc(hospital)}</title><style>{CSS}</style></head><body>"
            f"<header class=top><span class=brand>{esc(hospital)}</span><nav>{links}</nav>"
            f"<span class=synthetic>SYNTHETIC DATA</span></header><main><h1>{esc(title)}</h1>{msg}{body}</main>"
            f"<footer>Mock Indian hospital for the Vaidyx-TB demo. Every patient, doctor and number is invented; nothing here is a real record.</footer>"
            f"</body></html>")


def pill(status):
    return f'<span class="pill {STATUS_PILL.get(status, "info")}">{esc(status)}</span>'


def table(headers, rows, empty="Nothing to show."):
    """rows: lists of already-escaped HTML cells (use esc() on data)."""
    if not rows:
        return f'<p class=muted>{esc(empty)}</p>'
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    # the scroll box keeps a wide table from widening the page on a phone
    return f'<div class="scroll-x"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def dl(pairs):
    """Definition list of (label, already-escaped HTML value)."""
    return "<dl>" + "".join(f"<dt>{esc(k)}</dt><dd>{v}</dd>" for k, v in pairs) + "</dl>"


def options(items, selected=None):
    """<option> list from (value, label) pairs."""
    return "".join(f'<option value="{esc(v)}"{" selected" if v == selected else ""}>{esc(l)}</option>' for v, l in items)
