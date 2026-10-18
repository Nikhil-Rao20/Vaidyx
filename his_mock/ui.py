"""Shared page shell of the demo HIMS: "Vaidyx Demo Hospital", product label "DemoHIMS". The classic look of an Indian
hospital information system (e-Hospital / e-Sushrut style): a dark blue header band, a grey module bar, a patient banner,
dense bordered tables, a 13 px Verdana / Arial system font, grey buttons, blue links, small status pills. Plain Python
strings, one inline CSS block, no template engine. The SYNTHETIC DATA ribbon and the footer are on every page.
No em dashes anywhere in the UI. Clearly not Vaidyx (no teal).
"""
import html

HOSPITAL = "Vaidyx Demo Hospital"
PRODUCT = "DemoHIMS"
FOOTER = ("Vaidyx Demo Hospital (SYNTHETIC), a mock Indian hospital for the Vaidyx-TB demo. Every patient, doctor and "
          "number is invented; nothing here is a real record.")
MODULES = [("Registration", "/his"), ("OPD", "/his/opd"), ("IPD", "/his/ipd"), ("Laboratory", "/his/lab"),
           ("Radiology", "/his/radiology"), ("Pathology", "/his/pathology"), ("Exchange", "/his/exchange"),
           ("Admin", "/his/admin")]

CSS = """
:root { --band: #1f4e79; --band-ink: #ffffff; --bar: #d9dde3; --bar-line: #9aa5b1; --link: #0b3d91; --ink: #1b1b1b;
  --muted: #5b6770; --line: #b9c2cc; --line-soft: #d5dbe2; --head: #dfe6ee; --stripe: #f4f6f9; --page: #e9ecef;
  --paper: #ffffff; --banner: #fff6d5; --banner-line: #c9b458; --btn: #e8e8e8; --btn-line: #8c8c8c;
  --ok: #1f6f3a; --ok-s: #e3f2df; --warn: #8a5300; --warn-s: #fff1cf; --bad: #a4261a; --bad-s: #fde2e1; --info: #1f4e79;
  --info-s: #e1ecf7; --mono: "Courier New", Courier, monospace; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body { font: 13px/1.4 Verdana, Arial, Helvetica, sans-serif; color: var(--ink); background: var(--page); min-width: 320px; }
a { color: var(--link); }
header.top { background: var(--band); color: var(--band-ink); padding: 6px 12px; display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
header.top .brand { font-size: 18px; font-weight: bold; letter-spacing: .01em; }
header.top .product { font-size: 11px; background: #ffffff; color: var(--band); padding: 1px 6px; border-radius: 2px; margin-left: 8px; vertical-align: middle; font-weight: bold; }
header.top .who { margin-left: auto; font-size: 12px; }
header.top .who a { color: #ffffff; margin-left: 10px; }
.synthetic { background: #ffcc00; color: #3b2a00; font-size: 11px; font-weight: bold; padding: 2px 8px; border: 1px solid #b38f00; letter-spacing: .04em; }
nav.modules { background: var(--bar); border-bottom: 1px solid var(--bar-line); padding: 0 8px; display: flex; flex-wrap: wrap; }
nav.modules a { display: inline-block; padding: 5px 12px; color: var(--link); text-decoration: none; font-size: 12.5px; font-weight: bold; border-right: 1px solid var(--bar-line); }
nav.modules a.active { background: #ffffff; text-decoration: underline; text-underline-offset: 3px; color: var(--band); }
nav.modules a:hover { background: #eef1f5; }
main { padding: 8px 10px 16px; max-width: 1400px; margin: 0 auto; min-width: 0; }
h1 { font-size: 16px; color: var(--band); margin: 8px 0 8px; border-bottom: 2px solid var(--band); padding-bottom: 3px; }
h2 { font-size: 13.5px; color: var(--band); margin: 12px 0 5px; }
h3 { font-size: 13px; color: var(--ink); margin: 8px 0 4px; }
.panel { background: var(--paper); border: 1px solid var(--line); padding: 8px 10px; margin-bottom: 10px; min-width: 0; }
.panel h2:first-child { margin-top: 0; }
.banner { background: var(--banner); border: 1px solid var(--banner-line); padding: 5px 10px; margin: 6px 0 8px; display: flex; flex-wrap: wrap; gap: 4px 22px; font-size: 12.5px; }
.banner span b { color: var(--band); }
.scroll-x { overflow-x: auto; max-width: 100%; }
table { border-collapse: collapse; width: 100%; font-size: 12.5px; background: var(--paper); }
th, td { text-align: left; padding: 3px 6px; border: 1px solid var(--line-soft); vertical-align: top; }
th { background: var(--head); color: var(--ink); font-weight: bold; font-size: 12px; border-color: var(--line); white-space: nowrap; }
tbody tr:nth-child(even) td { background: var(--stripe); }
.mono { font-family: var(--mono); font-size: 12.5px; }
.muted { color: var(--muted); }
.small { font-size: 11.5px; }
.pill { display: inline-block; padding: 0 6px; border: 1px solid; font-size: 11px; font-weight: bold; line-height: 16px; white-space: nowrap; }
.pill.ok { background: var(--ok-s); color: var(--ok); border-color: var(--ok); }
.pill.warn { background: var(--warn-s); color: var(--warn); border-color: var(--warn); }
.pill.bad { background: var(--bad-s); color: var(--bad); border-color: var(--bad); }
.pill.info { background: var(--info-s); color: var(--info); border-color: var(--info); }
.pill.muted { background: #f0f0f0; color: var(--muted); border-color: var(--muted); }
form.inline { display: inline; }
.row { display: grid; grid-template-columns: 190px minmax(0, 1fr); gap: 2px 10px; align-items: start; margin: 4px 0; }
.row label, label.lbl { font-size: 12px; color: #333; padding-top: 4px; }
.row .ctl { min-width: 0; }
.help { color: var(--muted); font-size: 11px; display: block; margin-top: 1px; }
.field-error { color: var(--bad); font-size: 11.5px; font-weight: bold; display: block; margin-top: 1px; }
.has-error input, .has-error select, .has-error textarea { border-color: var(--bad); background: #fff7f7; }
input[type=text], input[type=password], input[type=date], input[type=time], input[type=number], select, textarea {
  width: 100%; max-width: 480px; padding: 3px 5px; border: 1px solid #7f8c99; font: inherit; font-size: 12.5px; background: #ffffff; }
input[type=text].short, input[type=number].short, select.short { max-width: 160px; }
textarea { min-height: 56px; }
button, .btn { background: var(--btn); color: #111; border: 1px solid var(--btn-line); padding: 3px 11px; font: inherit; font-size: 12px; cursor: pointer; text-decoration: none; display: inline-block; }
button:hover, .btn:hover { background: #dcdcdc; }
button:active, .btn:active { background: #c9c9c9; box-shadow: inset 0 1px 2px rgba(0, 0, 0, .3); }
button:disabled, .btn[aria-disabled=true] { opacity: .55; cursor: not-allowed; background: var(--btn); box-shadow: none; }
button.busy, .btn.busy { cursor: progress; opacity: .75; }
button.busy::after { content: " (working)"; font-weight: normal; }
a:focus-visible, button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible, summary:focus-visible {
  outline: 2px solid var(--band); outline-offset: 1px; }
button.primary, .btn.primary { font-weight: bold; background: #d6e0ec; border-color: #4f6f91; }
button.primary:hover, .btn.primary:hover { background: #c4d3e4; }
button.primary:active, .btn.primary:active { background: #b2c5db; }
button.danger, .btn.danger { color: var(--bad); border-color: var(--bad); }
button.linklike { background: none; border: 0; color: var(--link); text-decoration: underline; padding: 0; font-size: inherit; cursor: pointer; }
.flash { padding: 6px 10px; border: 1px solid; margin: 6px 0 10px; font-size: 12.5px; }
.flash.ok { background: var(--ok-s); color: var(--ok); border-color: var(--ok); }
.flash.bad { background: var(--bad-s); color: var(--bad); border-color: var(--bad); }
.flash.warn { background: var(--warn-s); color: var(--warn); border-color: var(--warn); }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 10px; }
.grid > .panel { margin-bottom: 0; }
dl { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 2px 12px; margin: 0; }
dt { color: var(--muted); font-size: 12px; } dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }
.tabs { margin: 6px 0; border-bottom: 1px solid var(--line); }
.tabs a { display: inline-block; padding: 3px 10px; border: 1px solid var(--line); border-bottom: 0; margin-right: 2px; background: #f0f2f5; text-decoration: none; font-size: 12px; }
.tabs a.active { background: #ffffff; font-weight: bold; }
.checks { columns: 2; column-gap: 20px; }
.checks label { display: block; break-inside: avoid; font-size: 12.5px; padding: 1px 0; }
.checks h3 { column-span: all; }
pre, .mono { white-space: pre-wrap; overflow-wrap: anywhere; }
td .mono, td a.mono, .banner .mono { white-space: nowrap; overflow-wrap: normal; }   /* identifiers never break mid-number */
pre.hl7 { background: #f7f7f7; border: 1px solid var(--line-soft); padding: 6px; font-size: 11.5px; max-height: 320px; overflow: auto; }
.label-print { font-family: var(--mono); font-size: 13px; border: 1px dashed #666; padding: 6px 8px; display: inline-block; background: #fff; }
.login { max-width: 420px; margin: 40px auto; }
footer { text-align: center; color: var(--muted); font-size: 11px; padding: 14px; }
@media (max-width: 760px) { .row { grid-template-columns: 1fr; } .checks { columns: 1; } header.top .who { margin-left: 0; } main { padding: 6px; } }
"""

# One small script on every page: a form is sent once (a second click while the first is on its way does nothing, so a
# report is never signed twice) and the pressed button shows that it is working. Going back to a page resets it.
SCRIPT = """
document.addEventListener('submit', function (e) {
  var f = e.target;
  if (f.dataset.sent) { e.preventDefault(); return; }
  f.dataset.sent = '1';
  var b = e.submitter || f.querySelector('button[type=submit]');
  if (b) { b.classList.add('busy'); b.setAttribute('aria-busy', 'true'); }
}, true);
window.addEventListener('pageshow', function () {
  document.querySelectorAll('form[data-sent]').forEach(function (f) { delete f.dataset.sent; });
  document.querySelectorAll('button.busy').forEach(function (b) { b.classList.remove('busy'); b.removeAttribute('aria-busy'); });
});
"""

STATUS_PILL = {"ordered": "info", "scheduled": "info", "sample_collected": "info", "completed": "ok", "cancelled": "bad",
               "preliminary": "warn", "final": "ok", "amended": "ok", "requested": "warn", "accepted": "ok",
               "in-progress": "info", "finished": "muted", "available": "ok", "registered": "info", "signed": "ok",
               "verified": "ok", "received": "info", "permanent": "ok", "temporary": "warn", "duplicate": "bad"}


def esc(value):
    """HTML-escape any value (None -> empty)."""
    return html.escape("" if value is None else str(value), quote=True)


def page(title, body, *, active=None, flash=None, user=None, banner=None, hospital=HOSPITAL, modules=None, nav=None):
    """A full HTML page: the header band (hospital name, product label, signed-in user with role and Logout), the module bar
    with the active module underlined, the optional patient banner, the title, the flash message and the body.
    `user` is the session dict (label, roles) or None (login page). `nav` is accepted for old callers and ignored."""
    links = "".join(f'<a href="{esc(h)}"{" class=active" if l == active else ""}>{esc(l)}</a>'
                    for l, h in (modules if modules is not None else MODULES))
    if user:
        roles = ", ".join(user.get("roles") or [])
        who = (f'<div class=who>Signed in: <b>{esc(user.get("label"))}</b> ({esc(roles)})'
               f' <a href="/his/logout">Logout</a></div>')
    else:
        who = '<div class=who>Not signed in <a href="/his/login">Login</a></div>'
    msg = ""
    if flash:
        kind, text = flash if isinstance(flash, tuple) else ("ok", flash)
        msg = f'<div class="flash {esc(kind)}">{esc(text)}</div>'
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
            f"<meta name=viewport content=\"width=device-width, initial-scale=1\">"
            f"<title>{esc(title)} | {esc(PRODUCT)} | {esc(hospital)}</title><style>{CSS}</style></head><body>"
            f"<header class=top><span class=brand>{esc(hospital)}<span class=product>{esc(PRODUCT)}</span></span>"
            f"{who}<span class=synthetic>SYNTHETIC DATA</span></header>"
            f"{f'<nav class=modules>{links}</nav>' if user else ''}<main>{banner or ''}<h1>{esc(title)}</h1>{msg}{body}</main>"
            f"<footer>{esc(FOOTER)}</footer><script>{SCRIPT}</script></body></html>")


def pill(status):
    return f'<span class="pill {STATUS_PILL.get(status, "info")}">{esc(str(status).replace("_", " "))}</span>'


def table(headers, rows, empty="Nothing to show."):
    """rows: lists of already-escaped HTML cells (use esc() on data). Every list has an empty-state line."""
    if not rows:
        return f'<p class=muted>{esc(empty)}</p>'
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="scroll-x"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def dl(pairs):
    """Definition list of (label, already-escaped HTML value)."""
    return "<dl>" + "".join(f"<dt>{esc(k)}</dt><dd>{v}</dd>" for k, v in pairs) + "</dl>"


def options(items, selected=None):
    """<option> list from (value, label) pairs."""
    return "".join(f'<option value="{esc(v)}"{" selected" if v == selected else ""}>{esc(l)}</option>' for v, l in items)


def field(name, label, control, error=None, help=None):
    """One form row: label, control, the validation error next to the field and an optional help line."""
    err = f'<span class=field-error>{esc(error)}</span>' if error else ""
    hlp = f'<span class=help>{esc(help)}</span>' if help else ""
    return (f'<div class="row{" has-error" if error else ""}"><label for="f-{esc(name)}">{esc(label)}</label>'
            f'<div class=ctl>{control}{err}{hlp}</div></div>')


def text_input(name, value="", *, required=False, placeholder="", short=False, kind="text", extra=""):
    req = " required" if required else ""
    cls = ' class=short' if short else ""
    ph = f' placeholder="{esc(placeholder)}"' if placeholder else ""
    return f'<input type={kind} id="f-{esc(name)}" name="{esc(name)}" value="{esc(value)}"{req}{cls}{ph}{extra}>'


def select(name, items, selected=None, *, short=False, required=False):
    cls = ' class=short' if short else ""
    req = " required" if required else ""
    return f'<select id="f-{esc(name)}" name="{esc(name)}"{cls}{req}>{options(items, selected)}</select>'


def textarea(name, value="", *, rows=4, required=False, placeholder=""):
    req = " required" if required else ""
    ph = f' placeholder="{esc(placeholder)}"' if placeholder else ""
    return f'<textarea id="f-{esc(name)}" name="{esc(name)}" rows={rows}{req}{ph}>{esc(value)}</textarea>'


def hidden(name, value):
    return f'<input type=hidden name="{esc(name)}" value="{esc(value)}">'


def tabs(items, active, base):
    """Tab bar: items [(key, label, count or None)], links to base?tab=key (other query parts are kept by the caller)."""
    out = []
    for key, label, count in items:
        n = f" ({count})" if count is not None else ""
        sep = "&" if "?" in base else "?"
        out.append(f'<a href="{esc(base)}{sep}tab={esc(key)}"{" class=active" if key == active else ""}>{esc(label)}{n}</a>')
    return f'<div class=tabs>{"".join(out)}</div>'
