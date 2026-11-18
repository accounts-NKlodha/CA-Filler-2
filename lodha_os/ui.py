"""HTML for the app shell. NKL design language: ink on ivory, dark sidebar, brass tile, IBM Plex Sans.

Amber = waiting for a person, blue = agent working, green = done, grey = draft, red = failed."""
from html import escape as esc

ICON = {
    "home": "M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z",
    "proposals": "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h6",
    "clients": "M16 20v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1M9.5 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM21 20v-1a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8",
    "financials": "M4 20V10M10 20V4M16 20v-7M22 20H2",
    "roc": "M4 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16M16 9h2a2 2 0 0 1 2 2v10M2 21h20M8 7h4M8 11h4M8 15h4",
    "gst": "M5 3v18l3-2 2 2 2-2 2 2 2-2 3 2V3zM9 8h6M9 12h6",
    "income-tax": "M3 21h18M5 21V10M9 21V10M15 21V10M19 21V10M12 3l9 5H3z",
    "tds": "M19 5L5 19M7.5 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM16.5 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
    "other-levies": "M12 3l9 5-9 5-9-5zM3 13l9 5 9-5",
    "agents": "M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3M6 6h12v12H6zM10 10h4v4h-4z",
    "queries": "M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12zM10 10a2 2 0 1 1 2.8 1.8c-.5.3-.8.7-.8 1.2M12 16h.01",
    "inbox": "M3 13l3-8h12l3 8v6H3zM3 13h5l1 3h6l1-3h5",
    "billing": "M2 7h20v10H2zM12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM6 12h.01M18 12h.01",
    "settings": "M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M14 4v4M8 10v4M16 16v4",
}
# The menu is fixed (CLAUDE.md). (group, [(key, label, path)])
MENU = (
    ("", (("home", "Home", "/"), ("proposals", "Proposals", "/proposals"), ("clients", "Clients", "/clients"))),
    ("Professional services", (("financials", "Financials", "/financials"), ("roc", "ROC", "/roc"), ("gst", "GST", "/gst"),
                               ("income-tax", "Income tax", "/income-tax"), ("tds", "TDS", "/tds"),
                               ("other-levies", "Other levies", "/other-levies"))),
    ("AI", (("agents", "Agents at work", "/agents"), ("queries", "Queries", "/queries"))),
    ("Office", (("inbox", "Inbox", "/inbox"), ("billing", "Billing", "/billing"), ("settings", "Settings", "/settings"))),
)
LABEL = {k: lab for _, items in MENU for k, lab, _ in items}

CSS = """
*{box-sizing:border-box}
body{margin:0;--bg:oklch(0.985 0.004 95);--fg:oklch(0.235 0.014 260);--surface:oklch(0.972 0.005 95);--card:oklch(1 0 0);--pri:oklch(0.285 0.038 258);--prifg:oklch(0.985 0.004 95);--muted:oklch(0.957 0.005 95);--mfg:oklch(0.53 0.014 258);--brass:oklch(0.62 0.086 76);--bd:oklch(0.905 0.006 95);--bds:oklch(0.84 0.008 95);--inp:oklch(0.888 0.007 95);--ok:oklch(0.49 0.088 158);--warnfg:oklch(0.24 0.03 72);--bad:oklch(0.52 0.176 27);--info:oklch(0.5 0.07 245);--sb:oklch(0.256 0.024 258);--sbac:oklch(0.31 0.026 258);--sbbd:oklch(0.34 0.022 258);
background:var(--bg);color:var(--fg);font:400 14px/20px "IBM Plex Sans",ui-sans-serif,system-ui,sans-serif;font-feature-settings:"cv05","ss01";-webkit-font-smoothing:antialiased}
a{color:var(--pri)}a:hover{color:var(--fg)}
h1{margin:0;font-size:28px;line-height:36px;font-weight:600;letter-spacing:-.014em}
h2{margin:0;font-size:16px;line-height:24px;font-weight:600;letter-spacing:-.014em}
:focus-visible{outline:2px solid var(--brass);outline-offset:2px}
.os{display:flex;min-height:100vh}
.num{font-variant-numeric:tabular-nums;font-feature-settings:"tnum";text-align:right}
.mono{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:13px}
.mut{color:var(--mfg)}
.cap{font-size:12px;line-height:16px;color:var(--mfg)}
.sb{width:240px;flex:none;background:var(--sb);color:oklch(0.87 0.01 95);display:flex;flex-direction:column;position:sticky;top:0;height:100vh;overflow-y:auto}
.brand{height:64px;flex:none;display:flex;align-items:center;gap:12px;padding:0 16px;border-bottom:1px solid var(--sbbd)}
.tile{width:32px;height:32px;border-radius:6px;background:var(--brass);color:oklch(0.99 0.004 95);display:flex;align-items:center;justify-content:center;font-weight:600;font-size:16px}
.nav{padding:12px;display:flex;flex-direction:column;gap:2px}
.nv{display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:7px;color:oklch(0.87 0.01 95 / .78);text-decoration:none}
.nv:hover{color:oklch(0.97 0.005 95)}
.nv svg{width:16px;height:16px;flex:none;fill:none;stroke:currentColor;stroke-width:1.75;stroke-linecap:round;stroke-linejoin:round}
.nv.on{background:var(--sbac);color:oklch(0.97 0.005 95);font-weight:500}
.grp{font-size:11px;line-height:16px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:oklch(0.87 0.01 95 / .68);padding:16px 12px 6px}
.col{flex:1;min-width:0;display:flex;flex-direction:column}
.top{height:64px;flex:none;border-bottom:1px solid var(--bd);display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 32px}
.in,.sel{height:36px;border:1px solid var(--inp);border-radius:7px;background:var(--card);padding:0 12px;font:inherit;color:var(--fg);box-shadow:0 1px 2px rgb(0 0 0/.05);width:100%}
.av{width:32px;height:32px;border-radius:9999px;background:var(--muted);border:1px solid var(--bd);display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:600}
.main{padding:32px;display:flex;flex-direction:column;gap:24px;max-width:1400px;width:100%}
.ph{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;flex-wrap:wrap;padding-bottom:24px;border-bottom:1px solid var(--bd)}
.btn{height:36px;padding:0 16px;border-radius:7px;border:1px solid var(--inp);background:var(--card);font:500 14px/20px "IBM Plex Sans",sans-serif;color:var(--fg);box-shadow:0 1px 2px rgb(0 0 0/.05);display:inline-flex;align-items:center;gap:8px;text-decoration:none;cursor:pointer;white-space:nowrap}
.btn:hover{background:var(--muted);color:var(--fg)}
.btn.p{background:var(--pri);border-color:var(--pri);color:var(--prifg)}
.btn.p:hover{background:var(--fg)}
.btn.link{border:none;box-shadow:none;background:none;padding:0;height:auto;color:var(--pri);text-decoration:underline}
.g{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:24px}
.s4{grid-column:span 4}.s5{grid-column:span 5}.s6{grid-column:span 6}.s7{grid-column:span 7}.s8{grid-column:span 8}.s12{grid-column:span 12}
.card{background:var(--card);border:1px solid var(--bd);border-radius:8px;overflow:hidden}
.ch{padding:14px 20px;display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}
.cb{padding:20px;border-top:1px solid var(--bd)}
.tr{display:grid;gap:16px;align-items:center;padding:10px 20px;border-top:1px solid var(--bd)}
a.tr{text-decoration:none;color:inherit}a.tr:hover{background:var(--muted)}
.th{font-size:11px;line-height:16px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:var(--mfg);background:var(--surface)}
.kv{display:grid;grid-template-columns:130px 1fr;gap:16px;padding:10px 20px;border-top:1px solid var(--bd)}
.b{display:inline-flex;align-items:center;height:22px;padding:0 8px;border-radius:6px;font-size:12px;font-weight:500;border:1px solid var(--bds);color:var(--mfg);background:var(--muted);white-space:nowrap}
.b.ok{color:var(--ok);background:oklch(0.49 0.088 158/.08);border-color:oklch(0.49 0.088 158/.3)}
.b.in{color:var(--info);background:oklch(0.5 0.07 245/.08);border-color:oklch(0.5 0.07 245/.3)}
.b.wa{color:var(--warnfg);background:oklch(0.68 0.126 72/.16);border-color:oklch(0.68 0.126 72/.5)}
.b.no{color:var(--bad);background:oklch(0.52 0.176 27/.07);border-color:oklch(0.52 0.176 27/.3)}
.tabs{display:flex;gap:28px;border-bottom:1px solid var(--bd);flex-wrap:wrap}
.tab{padding:10px 0;color:var(--mfg);text-decoration:none}
.tab.on{color:var(--fg);font-weight:500;box-shadow:inset 0 -2px 0 var(--pri)}
.form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px 24px}
.fld{display:flex;flex-direction:column;gap:6px}
.fld label,.lbl{font-weight:500}
.err{color:var(--bad);font-size:12px;line-height:16px}
.in.bad{border-color:var(--bad)}
.note{padding:12px 16px;border-radius:8px;border:1px solid oklch(0.68 0.126 72/.5);background:oklch(0.68 0.126 72/.12);color:var(--warnfg)}
.note.ok{border-color:oklch(0.49 0.088 158/.3);background:oklch(0.49 0.088 158/.08);color:var(--fg)}
.empty{padding:40px 20px;text-align:center;color:var(--mfg);border-top:1px solid var(--bd)}
.chk{display:flex;gap:8px;align-items:center;padding:4px 0}
.auth{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}
@media (max-width:1023px){.sb{position:static;height:auto;width:100%}.os{flex-direction:column}.g>*{grid-column:span 12}.form{grid-template-columns:1fr}.main,.top{padding-left:16px;padding-right:16px}.tr{overflow-x:auto}}
"""
HEAD = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>{{TITLE}} · Lodha OS</title><link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous">'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">'
        '<style>' + CSS + '</style></head><body>')


def day(iso, time=False):
    """'2026-11-18T17:13:00' -> '18 Nov 2026' (with ', 17:13' when time is asked)."""
    import datetime as dt
    try:
        d = dt.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    return "%d %s" % (d.day, d.strftime("%b %Y")) + (d.strftime(", %H:%M") if time else "")


def icon(k):
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="%s"/></svg>' % ICON[k]


def badge(text, kind=""):
    return '<span class="b %s">%s</span>' % (kind, esc(text))


def initials(name):
    parts = [p for p in name.split() if p]
    return esc("".join(p[0] for p in parts[:2]).upper() or "?")


def page(user, active, title, body, sub="", actions="", csrf="", q="", fy=""):
    nav = []
    for grp, items in MENU:
        if grp:
            nav.append('<div class="grp">%s</div>' % esc(grp))
        for k, lab, path in items:
            cur = ' aria-current="page"' if k == active else ""
            nav.append('<a class="nv%s" href="%s"%s>%s%s</a>' % (" on" if k == active else "", path, cur, icon(k), esc(lab)))
    return HEAD.replace('{{TITLE}}', esc(title)) + (
        '<div class="os"><nav class="sb" aria-label="Main"><div class="brand"><div class="tile">L</div><div>'
        '<div style="color:oklch(0.97 0.005 95);font-weight:600">Lodha OS</div>'
        '<div style="font-size:11px;line-height:16px;color:oklch(0.87 0.01 95 / .7)">N K Lodha &amp; Co</div></div></div>'
        '<div class="nav">' + "".join(nav) + '</div></nav>'
        '<div class="col"><div class="top"><form action="/clients" method="get" style="width:288px;max-width:50%">'
        '<input class="in" name="q" aria-label="Search clients" placeholder="Search client, PAN, CIN, GSTIN" value="' + esc(q) + '"></form>'
        '<div style="display:flex;align-items:center;gap:10px"><span class="cap">FY ' + esc(fy) + '</span>'
        '<div class="av">' + initials(user["name"]) + '</div><span style="font-weight:500">' + esc(user["name"]) + '</span>'
        '<form method="post" action="/logout"><input type="hidden" name="csrf" value="' + esc(csrf) + '">'
        '<button class="btn link" type="submit">Sign out</button></form></div></div>'
        '<main class="main"><div class="ph"><div>' + ('<div class="cap">%s</div>' % sub if sub else "") +
        '<h1>' + esc(title) + '</h1></div><div style="display:flex;gap:12px;flex-wrap:wrap">' + actions + '</div></div>' +
        body + '</main></div></div></body></html>')


def bare(title, body):
    """Sign-in and first-run pages: no menu."""
    return HEAD.replace('{{TITLE}}', esc(title)) + '<div class="auth"><div class="card" style="width:400px;max-width:100%">' \
        '<div class="ch" style="justify-content:flex-start"><div class="tile">L</div><div><h2>Lodha OS</h2>' \
        '<div class="cap">N K Lodha &amp; Co</div></div></div><div class="cb">' + body + '</div></div></div></body></html>'


def field(label, name, value="", err="", typ="text", hint="", mono=False, required=False, auto=""):
    eid = "e-" + name
    cls = "in" + (" bad" if err else "") + (" mono" if mono else "")
    return ('<div class="fld"><label for="f-%s">%s</label><input class="%s" id="f-%s" name="%s" type="%s" value="%s"%s%s%s>%s%s</div>' % (
        name, esc(label), cls, name, name, typ, esc(value), " required" if required else "",
        ' aria-describedby="%s" aria-invalid="true"' % eid if err else "", ' autocomplete="%s"' % auto if auto else "",
        '<span class="cap">%s</span>' % esc(hint) if hint and not err else "",
        '<span class="err" id="%s">%s</span>' % (eid, esc(err)) if err else ""))


def select(label, name, options, value="", err=""):
    opts = "".join('<option value="%s"%s>%s</option>' % (esc(v), " selected" if v == value else "", esc(t)) for v, t in options)
    return ('<div class="fld"><label for="f-%s">%s</label><select class="sel%s" id="f-%s" name="%s">%s</select>%s</div>' % (
        name, esc(label), " bad" if err else "", name, name, opts, '<span class="err">%s</span>' % esc(err) if err else ""))


def hidden(csrf):
    return '<input type="hidden" name="csrf" value="%s">' % esc(csrf)
