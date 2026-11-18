"""The web app. `App.handle` is plain (method, path, query, form, cookie) -> (status, headers, html) so it can be
tested without a socket; `serve` wraps it in the standard library HTTP server."""
import os
import sys
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

from . import auth, clients, config, financials, services, ui
from .ui import badge, esc, field, hidden, select

COOKIE = "lodha_os"
# What each menu item will hold, in CLAUDE.md's order of work. Shown until the screen is built: no fake screens.
PLANNED = {
    "proposals": ("1a", "Proposals from Proposal Maker with their status. An executed proposal sets up the client here."),
    "roc": ("2", "Hands approved financials to Form Filler for AOC-4 and MGT-7 or MGT-7A, and shows the SRN it returns."),
    "gst": ("3", "GSTR-9 and GSTR-9C: reconciliation and the JSON file for upload on the GST portal."),
    "tds": ("4", "Monthly TDS computation, then the quarterly return file."),
    "income-tax": ("5", "Income tax return JSON for upload."),
    "other-levies": ("5", "Profession tax (Tamil Nadu first) and FSSAI."),
    "agents": ("6", "Job board and activity log for work the agents do on their own."),
    "queries": ("6", "Questions the agents could not answer, routed to the local AI, then a reviewer, then a partner."),
    "inbox": ("6", "The firm mailbox and WhatsApp number: incoming filed to client folders, outgoing sent after approval."),
    "billing": ("6", "Invoice drafts for Tally Prime from the fees agreed in the proposal."),
}


class App:
    def __init__(self, st=None):
        self.st = st or config.store()
        self.users = auth.Users(self.st)
        self.clients = clients.Clients(self.st)
        self.sessions = auth.Sessions()
        self.fin_jobs = financials.Jobs(self.st)
        self.fin_engine = None  # tests put a stand-in here; otherwise loaded from the Form Filler folder

    # ------------------------------------------------------------------ plumbing
    def handle(self, method, path, query=None, form=None, cookie=""):
        query, form = query or {}, form or {}
        tok = cookie
        sess = self.sessions.get(tok)
        user = self.users.get(sess["uid"]) if sess else None
        if user and not user.get("active", True):
            user = None
        if not self.users.all():
            return self.setup(method, form) if path == "/setup" else redirect("/setup")
        if path == "/setup":
            return redirect("/")
        if path == "/login":
            return self.login(method, form, query)
        if not user:
            return redirect("/login" + ("?next=" + quote(path) if path not in ("/", "/logout") else ""))
        if method == "POST" and form.get("csrf") != sess["csrf"]:
            return 403, {}, ui.bare("Not allowed", '<p>This form has expired. <a href="/">Go back</a> and try again.</p>')
        self.s = settings = config.settings(self.st)
        ctx = dict(user=user, csrf=sess["csrf"], fy=settings["financial_year"])
        if path == "/logout" and method == "POST":
            self.sessions.end(tok)
            return redirect("/login", {"Set-Cookie": COOKIE + "=; Path=/; Max-Age=0"})
        parts = [p for p in path.split("/") if p]
        if not parts:
            return ok(self.home(ctx))
        head, rest = parts[0], parts[1:]
        if head == "clients":
            return self.clients_route(method, rest, query, form, ctx)
        if head == "settings":
            return self.settings_route(method, rest, form, ctx)
        if head == "financials":
            return self.financials_route(method, rest, form, ctx)
        if head in PLANNED and not rest:
            return ok(self.planned(head, ctx))
        return 404, {}, self.page(ctx, "", "Page not found", '<p>There is nothing at this address. <a href="/">Go to Home</a>.</p>')

    def page(self, ctx, active, title, body, **kw):
        return ui.page(ctx["user"], active, title, body, csrf=ctx["csrf"], fy=ctx["fy"], **kw)

    # ------------------------------------------------------------------ first run and sign-in
    def setup(self, method, form):
        e = {}
        if method == "POST":
            e = self.users.validate(form.get("name"), form.get("login"), "partner", form.get("password"))
            if not e:
                self.users.add(form["name"], form["login"], "partner", form["password"])
                return redirect("/login")
        body = ('<p style="margin-top:0">First run. Create the partner account that manages people and settings.</p>'
                '<form method="post" action="/setup" style="display:flex;flex-direction:column;gap:16px">' +
                field("Your name", "name", form.get("name", ""), e.get("name", ""), required=True, auto="name") +
                field("Sign-in name", "login", form.get("login", ""), e.get("login", ""), required=True, auto="username") +
                field("Password", "password", "", e.get("password", ""), typ="password", hint="At least 8 characters.", required=True, auto="new-password") +
                '<button class="btn p" type="submit" style="justify-content:center">Create account</button></form>')
        return ok(ui.bare("Set up", body))

    def login(self, method, form, query):
        err = ""
        nxt = form.get("next") or query.get("next") or "/"
        if not nxt.startswith("/") or nxt.startswith("//"):
            nxt = "/"
        if method == "POST":
            u = self.users.login(form.get("login"), form.get("password"))
            if u:
                tok = self.sessions.start(u["id"])
                return redirect(nxt, {"Set-Cookie": "%s=%s; Path=/; HttpOnly; SameSite=Lax" % (COOKIE, tok)})
            err = "The sign-in name or password is not right."
        body = ('<form method="post" action="/login" style="display:flex;flex-direction:column;gap:16px">' +
                '<input type="hidden" name="next" value="%s">' % esc(nxt) +
                ('<div class="err" role="alert">%s</div>' % err if err else "") +
                field("Sign-in name", "login", form.get("login", ""), required=True, auto="username") +
                field("Password", "password", "", typ="password", required=True, auto="current-password") +
                '<button class="btn p" type="submit" style="justify-content:center">Sign in</button></form>')
        return (401 if err else 200), {}, ui.bare("Sign in", body)

    # ------------------------------------------------------------------ home
    def checks(self):
        """What must be set before the OS can do real work. Each: (label, done, detail)."""
        s = self.s
        root, ff = s["clients_root"], s["form_filler_dir"]
        return [
            ("Client folders location", bool(root) and os.path.isdir(root), root or "Not set"),
            ("Form Filler (shared Schedule III engine)", bool(ff) and os.path.isdir(os.path.join(ff, "sch3", "engine")), ff or "Not set"),
        ]

    def home(self, ctx):
        rows = self.clients.all()
        todo = [c for c in self.checks() if not c[1]]
        out = []
        if todo and auth.can(ctx["user"], "change_settings"):
            out.append('<div class="note">Before the OS can work on client files: %s. <a href="/settings">Open Settings</a></div>'
                       % esc(" and ".join(c[0] + " is not set" for c in todo)))
        elif todo:
            out.append('<div class="note">A partner needs to finish Settings before work can start here.</div>')
        if not rows:
            out.append('<div class="card"><div class="empty"><p style="margin:0 0 16px">No clients yet. Add the first one to start.</p>'
                       '<a class="btn p" href="/clients/new">Add client</a></div></div>')
            return self.page(ctx, "home", "Today", "".join(out))
        by = {l: sum(1 for c in rows if l in services.lines_of(c.get("services"))) for l in services.LINES}
        line_rows = "".join('<a class="tr" style="grid-template-columns:1fr auto" href="/clients?line=%s"><span>%s</span><span class="num">%d</span></a>'
                            % (quote(l), esc(l), n) for l, n in by.items() if n)
        recent = sorted(rows, key=lambda c: c.get("created", ""), reverse=True)[:6]
        rec = "".join('<a class="tr" style="grid-template-columns:1fr auto" href="/clients/%s"><span><span style="font-weight:500">%s</span>%s</span><span class="cap">%s</span></a>'
                      % (c["id"], esc(c["name"]), ' <span class="mut">· %s</span>' % esc(c["group"]) if c.get("group") else "", esc(ui.day(c.get("created", "")))) for c in recent)
        out.append('<div class="g"><div class="card s5"><div class="ch"><h2>Clients by service</h2><span class="cap">%d clients</span></div>%s</div>'
                   '<div class="card s7"><div class="ch"><h2>Recently added</h2><a href="/clients">All clients</a></div>%s</div></div>'
                   % (len(rows), line_rows or '<div class="empty">No services are switched on for any client yet.</div>', rec))
        out.append('<p class="cap" style="margin:0">Due dates, your work queue and agent activity appear here as each service is built.</p>')
        return self.page(ctx, "home", "Today", "".join(out), actions='<a class="btn p" href="/clients/new">Add client</a>')

    def planned(self, key, ctx):
        step, text = PLANNED[key]
        body = ('<div class="card"><div class="ch"><h2>Not built yet</h2>%s</div><div class="cb"><p style="margin:0 0 8px">%s</p>'
                '<p class="cap" style="margin:0">Nothing on this screen works today. It is listed so the menu matches the agreed design.</p></div></div>'
                % (badge("Step %s in the build order" % step), esc(text)))
        return self.page(ctx, key, ui.LABEL[key], body)

    # ------------------------------------------------------------------ clients
    def clients_route(self, method, rest, query, form, ctx):
        if not rest:
            return ok(self.client_list(query, ctx))
        if rest == ["new"]:
            return self.client_form(method, None, form, ctx)
        c = self.clients.get(rest[0])
        if not c:
            return 404, {}, self.page(ctx, "clients", "Client not found", '<p><a href="/clients">Back to clients</a></p>')
        if rest[1:] == ["edit"]:
            return self.client_form(method, c, form, ctx)
        if len(rest) == 1:
            return ok(self.client_view(c, query, ctx))
        return 404, {}, self.page(ctx, "clients", "Page not found", '<p><a href="/clients">Back to clients</a></p>')

    def client_list(self, query, ctx):
        q, line = (query.get("q") or "").strip(), query.get("line") or ""
        rows = self.clients.all()
        total = len(rows)
        if q:
            n = q.lower().replace(" ", "")
            rows = [c for c in rows if n in "".join([c["name"], c.get("group", ""), c.get("pan", ""), c.get("gstin", ""), c.get("cin", "")]).lower().replace(" ", "")]
        if line in services.LINES:
            rows = [c for c in rows if line in services.lines_of(c.get("services"))]
        chips = '<a class="b %s" href="/clients" style="text-decoration:none">All %d</a>' % ("wa" if not line else "", total)
        for l in services.LINES:
            chips += '<a class="b %s" href="/clients?line=%s" style="text-decoration:none">%s</a>' % ("wa" if l == line else "", quote(l), esc(l))
        cols = "grid-template-columns:1.5fr 1fr 1.3fr 1.3fr 1.4fr"
        body = '<div class="card"><div class="ch"><div style="display:flex;gap:8px;flex-wrap:wrap">%s</div><span class="cap">%s</span></div>' % (
            chips, esc("%d shown" % len(rows) + (' for "%s"' % q if q else "")))
        if rows:
            body += '<div class="tr th" style="%s"><span>Client</span><span>Group</span><span>PAN and GSTIN</span><span>Constitution</span><span>Services</span></div>' % cols
            for c in rows:
                ids = "<br>".join(esc(x) for x in (c.get("pan"), c.get("gstin")) if x) or '<span class="mut">Not entered</span>'
                ls = " ".join(badge(l) for l in services.lines_of(c.get("services"))) or '<span class="mut">None yet</span>'
                body += ('<a class="tr" style="%s" href="/clients/%s"><span style="font-weight:500">%s</span><span class="mut">%s</span>'
                         '<span class="mono">%s</span><span>%s</span><span style="display:flex;gap:4px;flex-wrap:wrap">%s</span></a>'
                         % (cols, c["id"], esc(c["name"]), esc(c.get("group", "")), ids, esc(c["constitution"]), ls))
        else:
            body += '<div class="empty">%s</div>' % ("No client matches this search." if total else "No clients yet.")
        body += "</div>"
        return self.page(ctx, "clients", "Clients", body, q=q, actions='<a class="btn p" href="/clients/new">Add client</a>')

    def client_form(self, method, c, form, ctx):
        e, data = {}, dict(c or {})
        if method == "POST":
            data = dict(form, services=form.get("_services", []))
            row, e = self.clients.save(data, ctx["user"]["name"], cid=c["id"] if c else None, root=self.root())
            if not e:
                return redirect("/clients/%s?saved=1" % row["id"])
            data = dict(row)
        v = lambda k: data.get(k, "") or ""
        chosen = set(data.get("services") or [])
        svc = ""
        for line, names in services.by_line().items():
            svc += '<fieldset style="border:none;margin:0;padding:0"><legend class="lbl" style="padding:0 0 4px">%s</legend>%s</fieldset>' % (
                esc(line), "".join('<label class="chk"><input type="checkbox" name="services" value="%s"%s> %s</label>'
                                   % (esc(n), " checked" if n in chosen else "", esc(n)) for n in names))
        act = "/clients/%s/edit" % c["id"] if c else "/clients/new"
        folder = ('<p class="cap" style="margin:16px 0 0">Folder: <span class="mono">%s</span>. The folder keeps this name even if the client name changes.</p>' % esc(c["folder"])
                  if c else '<p class="cap" style="margin:16px 0 0">Saving creates the client folder as "Group name - Client name" under the client folders location.</p>')
        body = ('<form method="post" action="%s">%s<div class="g"><div class="card s8"><div class="ch"><h2>Client details</h2></div><div class="cb"><div class="form">'
                % (act, hidden(ctx["csrf"])) +
                field("Legal name", "name", v("name"), e.get("name", ""), required=True) +
                field("Group name", "group", v("group"), hint="Leave blank if the client is not part of a group.") +
                select("Constitution", "constitution", [("", "Choose")] + [(x, x) for x in clients.CONSTITUTIONS], v("constitution"), e.get("constitution", "")) +
                field("PAN", "pan", v("pan"), e.get("pan", ""), mono=True) +
                field("GSTIN", "gstin", v("gstin"), e.get("gstin", ""), mono=True) +
                field("CIN or LLPIN", "cin", v("cin"), e.get("cin", ""), mono=True) +
                field("Contact person", "contact", v("contact")) +
                field("Mobile", "mobile", v("mobile"), e.get("mobile", ""), typ="tel", mono=True) +
                field("E-mail", "email", v("email"), e.get("email", ""), typ="email") +
                field("Tally company name", "tally_company", v("tally_company"), hint="Exactly as it shows in Tally. Leave blank for Excel clients.") +
                '</div>' + folder + '</div></div><div class="card s4"><div class="ch"><h2>Services</h2></div>'
                '<div class="cb" style="display:flex;flex-direction:column;gap:12px">' + svc + '</div></div></div>'
                '<div style="display:flex;gap:12px;margin-top:24px"><button class="btn p" type="submit">Save client</button>'
                '<a class="btn" href="%s">Cancel</a></div></form>' % ("/clients/" + c["id"] if c else "/clients"))
        status = 422 if e else 200
        return status, {}, self.page(ctx, "clients", "Edit client" if c else "Add client", body, sub=esc(c["name"]) if c else "")

    def root(self):
        r = self.s["clients_root"]
        return r if r and os.path.isdir(r) else ""

    def client_view(self, c, query, ctx):
        root = self.root()
        ids = " · ".join('<span class="mono">%s %s</span>' % (k, esc(c[f])) for k, f in (("CIN", "cin"), ("PAN", "pan"), ("GSTIN", "gstin")) if c.get(f))
        sub = " · ".join(x for x in (esc(c.get("group", "")), ids) if x)
        lines = services.lines_of(c.get("services"))
        tab = query.get("tab") if query.get("tab") in lines else ""
        tabs = '<a class="tab %s" href="/clients/%s">Overview</a>' % ("" if tab else "on", c["id"])
        for l in lines:
            tabs += '<a class="tab %s" href="/clients/%s?tab=%s">%s</a>' % ("on" if l == tab else "", c["id"], quote(l), esc(l))
        out = ['<div class="note ok" role="status">Saved.</div>' if query.get("saved") else "", '<nav class="tabs" aria-label="Client sections">%s</nav>' % tabs]
        if tab:
            key = tab.lower().replace(" ", "-")
            if tab == "Financials":
                return redirect("/financials/" + c["id"])
            step, text = PLANNED.get(key, ("", "Work for this service is tracked outside the OS for now."))
            mine = [s for s in c["services"] if services.SERVICES[s] == tab]
            out.append('<div class="card"><div class="ch"><h2>%s</h2>%s</div><div class="cb"><p style="margin:0 0 8px">Services engaged: %s.</p>'
                       '<p class="cap" style="margin:0">%s</p></div></div>' % (esc(tab), badge("Step %s in the build order" % step) if step else "", esc(", ".join(mine)), esc(text)))
        else:
            kv = lambda k, val, mono=False: '<div class="kv"><span class="mut">%s</span><span%s>%s</span></div>' % (
                k, ' class="mono"' if mono and val else "", esc(val) if val else '<span class="mut">Not entered</span>')
            fp = str(clients.folder_path(root, c)) if root else ""
            fstate = badge("Folder exists", "ok") if fp and os.path.isdir(fp) else badge("Folder not created", "wa")
            details = (kv("Constitution", c["constitution"]) + kv("Contact", c.get("contact")) + kv("Mobile", c.get("mobile"), True) +
                       kv("E-mail", c.get("email")) + kv("Tally company", c.get("tally_company")) +
                       '<div class="kv"><span class="mut">Folder</span><span><span class="mono">%s</span> %s</span></div>' % (esc(fp or c["folder"]), fstate) +
                       kv("Services", ", ".join(c.get("services") or [])))
            tr = clients.read_trail(root, c, 12) if root else []
            trail = "".join('<div class="tr" style="grid-template-columns:150px 1fr 120px"><span class="mono mut">%s</span><span>%s</span><span class="mut">%s</span></div>'
                            % (esc(ui.day(t["at"], True)), esc(t["text"]), esc(t.get("by", ""))) for t in tr)
            if not trail:
                trail = '<div class="empty">%s</div>' % ("Nothing recorded yet." if root else "The client folders location is not set, so no trail is kept yet.")
            out.append('<div class="g"><div class="card s6"><div class="ch"><h2>Details</h2></div>%s</div>'
                       '<div class="card s6"><div class="ch"><h2>Audit trail</h2><span class="cap">Kept in the client folder</span></div>%s</div></div>' % (details, trail))
        return self.page(ctx, "clients", c["name"], "".join(out), sub=sub, actions='<a class="btn" href="/clients/%s/edit">Edit client</a>' % c["id"])

    # ------------------------------------------------------------------ financials
    FIN_LINES = ("Financials", "ROC")
    JOB = {"queued": ("Queued", ""), "running": ("Agent working", "in"), "staff": ("Waiting for staff", "wa"),
           "review": ("Review points", "wa"), "done": ("Ready", "ok"), "failed": ("Failed", "no")}

    def fin_clients(self):
        return [c for c in self.clients.all() if set(services.lines_of(c.get("services"))) & set(self.FIN_LINES)]

    def fin_ready(self):
        """Why Get data cannot run yet, or ''."""
        if not self.root():
            return "The client folders location is not set."
        if not os.path.isfile(str(financials.engine_dir(self.s["form_filler_dir"]) / "pipeline.py")):
            return "The Form Filler folder is not set, so the shared Schedule III engine cannot be found."
        return ""

    def financials_route(self, method, rest, form, ctx):
        user = ctx["user"]
        if method == "POST" and rest == ["get-data"]:
            ids = set(form.get("_clients") or [])
            rows = [c for c in self.fin_clients() if c["id"] in ids]
            if rows and not self.fin_ready():
                picks = {}
                if form.get("pick_which") in ("tb_cy", "tb_py") and form.get("pick_company") and len(rows) == 1:
                    picks[rows[0]["id"]] = {form["pick_which"]: form["pick_company"]}
                self.fin_jobs.start(rows, self.root(), self.s, user["name"], picks)
            return redirect(form.get("back") if str(form.get("back", "")).startswith("/financials") else "/financials")
        if not rest:
            return ok(self.fin_list(ctx))
        c = self.clients.get(rest[0])
        if not c or c not in self.fin_clients():
            return 404, {}, self.page(ctx, "financials", "Client not found", '<p><a href="/financials">Back to Financials</a></p>')
        root, fy, cid = self.root(), ctx["fy"], c["id"]
        if rest[1:] == ["mapping"]:
            return self.fin_mapping(method, c, form, ctx)
        if method == "POST" and rest[1:] and rest[1] in ("clear", "verify", "unverify", "rebuild"):
            if not auth.can(user, "review"):
                return 403, {}, self.page(ctx, "financials", "Not allowed", "<p>Only a reviewer or a partner can do this.</p>")
            err = ""
            try:
                if rest[1] == "clear":
                    financials.clear_point(c, root, fy, form.get("pid", ""), user["name"], form.get("note", ""))
                elif rest[1] == "verify":
                    financials.verify(c, root, fy, user["name"])
                elif rest[1] == "unverify":
                    financials.unverify(c, root, fy, user["name"])
                elif not self.fin_ready():
                    self.fin_jobs.start([c], root, self.s, user["name"], rebuild=True)
            except ValueError as e:
                err = str(e)
            return ok(self.fin_view(c, ctx, err)) if err else redirect("/financials/" + cid)
        if rest[1:] == ["workbook"]:
            wb = financials.status(c, self.root(), ctx["fy"])["workbook"]
            if not wb:
                return redirect("/financials/" + c["id"])
            clients.trail(self.root(), c, "financials", "Schedule III workbook downloaded: %s" % wb.name, user["name"])
            return 200, {"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         "Content-Disposition": 'attachment; filename="%s"' % wb.name.replace('"', "")}, wb.read_bytes()
        return ok(self.fin_view(c, ctx))

    def fin_list(self, ctx):
        rows, why, root, fy = self.fin_clients(), self.fin_ready(), self.root(), ctx["fy"]
        out = []
        if why:
            out.append('<div class="note">%s %s</div>' % (esc(why), '<a href="/settings">Open Settings</a>' if auth.can(ctx["user"], "change_settings") else "A partner sets this in Settings."))
        if not rows:
            out.append('<div class="card"><div class="empty">No client has Accounting, Statutory audit or MCA annual compliance switched on yet. '
                       'Switch the service on in the client to see it here.</div></div>')
            return self.page(ctx, "financials", "Financials", "".join(out), sub="Professional Services")
        cols = "grid-template-columns:32px 1.6fr 1.2fr 1.2fr 1fr 1.6fr"
        busy = self.fin_jobs.busy()
        body = ('<form method="post" action="/financials/get-data" id="gd">%s<div class="card"><div class="ch"><h2>Schedule III, FY %s</h2>'
                '<span class="cap">Open the client companies in Tally, tick the clients, then Get data</span></div>'
                '<div class="tr th" style="%s"><span></span><span>Client</span><span>This year from Tally</span><span>Last year from Tally</span>'
                '<span>Schedule III</span><span>Where it stands</span></div>' % (hidden(ctx["csrf"]), esc(fy), cols))
        for c in rows:
            st = financials.status(c, root, fy)
            job = self.fin_jobs.get(c["id"])
            if job and job.get("fy", fy) != fy:
                job = None
            tb = lambda t: ('%s<br><span class="cap">%s</span>' % (esc(t["company"]), esc(ui.day(t["at"], True)))) if t else '<span class="mut">Not read</span>'
            if job and (job["state"] not in ("review", "done") or not st["workbook"]):
                lab, kind = self.JOB[job["state"]]
                where = "%s <span class=\"cap\">%s</span>" % (badge(lab, kind), esc(job.get("note", "")))
            elif st["verified"]:
                where = '%s <span class="cap">%s, %s</span>' % (badge("Verified", "ok"), esc(st["verified"]["by"]), esc(ui.day(st["verified"]["at"])))
            elif st["workbook"]:
                n = st["open"]
                where = badge("%d review points" % n, "wa") if n else badge("Ready for the tick", "wa")
            else:
                where = '<span class="mut">Not started</span>'
            wb = '<a href="/financials/%s">Open</a>' % c["id"] if st["workbook"] else '<span class="mut">Not built</span>'
            body += ('<div class="tr" style="%s"><span><input type="checkbox" name="client" value="%s" aria-label="Select %s"></span>'
                     '<span><a href="/financials/%s" style="font-weight:500">%s</a>%s</span><span>%s</span><span>%s</span><span>%s</span><span>%s</span></div>'
                     % (cols, c["id"], esc(c["name"]), c["id"], esc(c["name"]),
                        '<br><span class="cap">%s</span>' % esc(c["group"]) if c.get("group") else "", tb(st["tb_cy"]), tb(st["tb_py"]), wb, where))
        body += '</div></form>'
        body += ('<p class="cap" style="margin:0">Get data reads this year and last year from Tally, maps every ledger to its Schedule III head and builds the workbook, '
                 'one client after another. A reviewer clears the review points. Nothing is filed from here.</p>')
        if busy:
            body += '<script>setTimeout(function(){location.reload()},4000)</script>'
        act = '<button class="btn p" type="submit" form="gd"%s>Get data</button>' % (" disabled" if why else "")
        return self.page(ctx, "financials", "Financials", "".join(out) + body, sub="Professional Services", actions=act)

    def fin_eng(self):
        return self.fin_engine or financials.load_engine(self.s["form_filler_dir"])

    def fin_mapping(self, method, c, form, ctx):
        root, fy, user = self.root(), ctx["fy"], ctx["user"]
        can = auth.can(user, "review")
        try:
            eng = self.fin_eng()
        except financials.EngineMissing as e:
            return ok(self.page(ctx, "financials", "Ledger heads", '<div class="note">%s</div>' % esc(str(e))))
        rows = financials.mapping_rows(c, root, fy, eng) if root else []
        pend = [r for r in rows if not r["approved"]]
        if method == "POST":
            if not can:
                return 403, {}, self.page(ctx, "financials", "Not allowed", "<p>Only a reviewer or a partner can confirm ledger heads.</p>")
            dec = {}
            for i in range(int(form.get("n") or 0)):
                led, code = form.get("led_%d" % i), form.get("head_%d" % i)
                if led and code:
                    dec[led] = code
            if financials.approve_heads(c, root, fy, dec, user["name"], eng) and not self.fin_ready():
                self.fin_jobs.start([c], root, self.s, user["name"], rebuild=True)
            return redirect("/financials/" + c["id"])
        sub = '<a href="/financials">Financials</a> · <a href="/financials/%s">%s</a> · FY %s' % (c["id"], esc(c["name"]), esc(fy))
        if not pend:
            body = '<div class="card"><div class="empty">%s</div></div>' % (
                "Every ledger's Schedule III head is approved." if rows else "There is no trial balance yet. Run Get data first.")
            return ok(self.page(ctx, "financials", "Ledger heads", body, sub=sub))
        opts = eng.approval.head_options()
        cols = "grid-template-columns:1.4fr 1fr 110px 110px 1.8fr"
        amt = lambda x: esc("{:,.2f}".format(abs(x)) + (" Dr" if x < 0 else " Cr" if x > 0 else ""))
        body = ('<form method="post" id="mp">%s<input type="hidden" name="n" value="%d"><div class="card"><div class="ch"><h2>%d ledgers to confirm</h2>'
                '<span class="cap">Balances as read from Tally. The head shown is the agent\'s proposal: change it where it is wrong.</span></div>'
                '<div class="tr th" style="%s"><span>Ledger</span><span>Tally group</span><span class="num">This year</span><span class="num">Last year</span><span>Schedule III head</span></div>'
                % (hidden(ctx["csrf"]), len(pend), len(pend), cols))
        for i, r in enumerate(pend):
            cur = (r.get("proposed") or {}).get("code", "")
            sel = '<option value="">Pick a head</option>' + "".join('<option value="%s"%s>%s</option>' % (esc(o["code"]), " selected" if o["code"] == cur else "", esc(o["label"])) for o in opts)
            why = " · ".join(x for x in (r.get("reason"), r.get("warn")) if x)
            body += ('<div class="tr" style="%s"><span><span style="font-weight:500">%s</span>%s</span><span class="mut">%s</span><span class="num">%s</span><span class="num">%s</span>'
                     '<span><input type="hidden" name="led_%d" value="%s"><select class="sel" name="head_%d" aria-label="Head for %s"%s>%s</select></span></div>'
                     % (cols, esc(r["ledger"]), '<br><span class="cap">%s</span>' % esc(why) if why else "", esc(r["group"]), amt(r["cy"]), amt(r["py"]),
                        i, esc(r["ledger"]), i, esc(r["ledger"]), "" if can else " disabled", sel))
        body += '</div></form><p class="cap" style="margin:0">Confirming records your name against each ledger and rebuilds the workbook. The heads are remembered for next year.</p>'
        act = '<button class="btn p" type="submit" form="mp">Confirm heads and rebuild</button>' if can else ""
        return ok(self.page(ctx, "financials", "Ledger heads", body, sub=sub, actions=act))

    def fin_view(self, c, ctx, err=""):
        root, fy = self.root(), ctx["fy"]
        st = financials.status(c, root, fy)
        job = self.fin_jobs.get(c["id"])
        if job and job.get("fy", fy) != fy:
            job = None
        why = self.fin_ready()
        can = auth.can(ctx["user"], "review")
        out = []
        if why:
            out.append('<div class="note">%s</div>' % esc(why))
        if err:
            out.append('<div class="note" role="alert">%s</div>' % esc(err))
        if job and job["state"] in ("queued", "running"):
            out.append('<div class="note" role="status">%s %s</div><script>setTimeout(function(){location.reload()},4000)</script>'
                       % (badge("Agent working", "in"), esc(job.get("note", ""))))
        elif job and job["state"] == "failed":
            out.append('<div class="note" role="alert">%s %s</div>' % (badge("Failed", "no"), esc(job.get("note", ""))))
        elif job and job["state"] == "staff":
            pick = job.get("pick")
            form = ""
            if pick:
                form = ('<form method="post" action="/financials/get-data" style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;margin-top:12px">%s'
                        '<input type="hidden" name="client" value="%s"><input type="hidden" name="pick_which" value="%s">'
                        '<input type="hidden" name="back" value="/financials/%s">%s<button class="btn" type="submit">Use this company</button></form>'
                        % (hidden(ctx["csrf"]), c["id"], esc(pick["which"]), c["id"],
                           select("Companies open in Tally now", "pick_company", [(n, n) for n in pick["open"]])))
            out.append('<div class="note" role="alert">%s %s%s</div>' % (badge("Waiting for staff", "wa"), esc(job.get("note", "")), form))
        kv = lambda k, v: '<div class="kv"><span class="mut">%s</span><span>%s</span></div>' % (k, v)
        tb = lambda t: ('%s <span class="cap">read %s</span>' % (esc(t["company"]), esc(ui.day(t["at"], True)))) if t else '<span class="mut">Not read yet</span>'
        b = st["build"] or {}
        wb = st["workbook"]
        data = (kv("This year, %s" % esc(fy), tb(st["tb_cy"])) + kv("Last year, %s" % esc(financials.prev_fy(fy)), tb(st["tb_py"])) +
                kv("Ledgers", str(b["ledgers"]) if b.get("ledgers") else '<span class="mut">None yet</span>') +
                kv("Workbook", ('<a href="/financials/%s/workbook">%s</a> <span class="cap">built %s</span>' % (c["id"], esc(wb.name), esc(ui.day(b.get("finished", ""), True))))
                   if wb else '<span class="mut">Not built yet</span>') +
                kv("Kept in", '<span class="mono">%s</span>' % esc(str(clients.folder_path(root, c))) if root else '<span class="mut">Not set</span>'))
        kinds = {"check": "Check", "mapping": "Mapping", "data": "Data"}
        post = lambda action, inner: '<form method="post" action="/financials/%s/%s" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">%s%s</form>' % (c["id"], action, hidden(ctx["csrf"]), inner)
        pts = ""
        for p in st["points"]:
            if p["cleared"]:
                right = '%s <span class="cap">%s, %s: %s</span>' % (badge("Cleared", "ok"), esc(p["cleared"]["by"]), esc(ui.day(p["cleared"]["at"])), esc(p["cleared"]["note"]))
            elif p["kind"] == "mapping":
                right = '<a href="/financials/%s/mapping">Confirm the heads</a>' % c["id"]
            elif can:
                right = post("clear", '<input type="hidden" name="pid" value="%s"><input class="in" name="note" aria-label="Why this point is acceptable" placeholder="Why this is acceptable" style="width:220px" required><button class="btn" type="submit">Clear</button>' % esc(p["id"]))
            else:
                right = '<span class="cap">For the reviewer</span>'
            pts += '<div class="tr" style="grid-template-columns:84px 1fr"><span>%s</span><span>%s<div style="margin-top:6px">%s</div></span></div>' % (
                badge(kinds[p["kind"]], "ok" if p["cleared"] else "wa"), esc(p["text"]), right)
        if not pts:
            pts = '<div class="empty">%s</div>' % ("No open points: every check in the workbook reads OK and every ledger head is approved." if wb else "Review points appear here after Get data.")
        head = "%d open" % st["open"] if wb else ""
        if st["stale"]:
            out.append('<div class="note">Ledger heads were changed after this workbook was built. %s</div>' % (post("rebuild", '<button class="btn" type="submit">Rebuild now</button>') if can else "A reviewer rebuilds it."))
        if st["verified"]:
            v = st["verified"]
            out.append('<div class="note ok" role="status" style="display:flex;justify-content:space-between;gap:16px;align-items:center;flex-wrap:wrap"><span>%s Verified by %s on %s. These financials can go to ROC filing.</span>%s</div>'
                       % (badge("Verified", "ok"), esc(v["by"]), esc(ui.day(v["at"], True)), post("unverify", '<button class="btn link" type="submit">Withdraw the tick</button>') if can else ""))
        out.append('<div class="g"><div class="card s6"><div class="ch"><h2>Data and workbook</h2></div>%s</div>'
                   '<div class="card s6"><div class="ch"><h2>Review points</h2><span class="cap">%s</span></div>%s</div></div>'
                   % (data, head, pts))
        checks = [r for r in (b.get("checks") or [])]
        rows, started = "", False
        for r in checks:
            if r[0].startswith("Tolerance"):
                break
            if r[0] == "Check":
                started = True
                continue
            if started and len(r) > 3:
                rows += ('<div class="tr" style="grid-template-columns:2.4fr 1fr 1fr 90px"><span>%s</span><span class="num">%s</span><span class="num">%s</span><span>%s</span></div>'
                         % (esc(r[0]), esc(r[1]), esc(r[2]), badge(r[3], "ok" if r[3].strip().upper() == "OK" else "wa")))
        if rows:
            out.append('<div class="card"><div class="ch"><h2>Checks in the workbook</h2><span class="cap">Read from the Checks sheet, in rupees</span></div>'
                       '<div class="tr th" style="grid-template-columns:2.4fr 1fr 1fr 90px"><span>Check</span><span class="num">This year</span><span class="num">Last year</span><span>Status</span></div>%s</div>' % rows)
        tr = [t for t in (clients.read_trail(root, c, 200) if root else []) if t.get("kind") == "financials"][:15]
        trail = "".join('<div class="tr" style="grid-template-columns:150px 1fr 120px"><span class="mono mut">%s</span><span>%s</span><span class="mut">%s</span></div>'
                        % (esc(ui.day(t["at"], True)), esc(t["text"]), esc(t.get("by", ""))) for t in tr) or '<div class="empty">Nothing recorded yet.</div>'
        out.append('<div class="card"><div class="ch"><h2>Audit trail</h2><span class="cap">Source, period and file for every step, kept in the client folder</span></div>%s</div>' % trail)
        running = job and job["state"] in ("queued", "running")
        tick = bool(wb) and can and not st["open"] and not st["stale"] and not st["verified"] and not running
        act = ('<form method="post" action="/financials/get-data">%s<input type="hidden" name="client" value="%s"><input type="hidden" name="back" value="/financials/%s">'
               '<button class="btn%s" type="submit"%s>Get data</button></form>' % (hidden(ctx["csrf"]), c["id"], c["id"], "" if tick else " p", " disabled" if why or running else ""))
        if tick:
            act += post("verify", '<button class="btn p" type="submit">Verified, OK to file</button>')
        return self.page(ctx, "financials", c["name"], "".join(out), sub='<a href="/financials">Financials</a> · FY %s' % esc(fy), actions=act)

    # ------------------------------------------------------------------ settings and people
    def settings_route(self, method, rest, form, ctx):
        if not auth.can(ctx["user"], "change_settings"):
            return 403, {}, self.page(ctx, "settings", "Settings", '<div class="note">Only a partner can open Settings.</div>')
        if rest[:1] == ["people"]:
            return self.person_form(method, rest[1:], form, ctx)
        if rest:
            return 404, {}, self.page(ctx, "settings", "Page not found", '<p><a href="/settings">Back to Settings</a></p>')
        e, msg, s = {}, "", self.s
        if method == "POST":
            vals = {k: form.get(k, "") for k in config.DEFAULTS}
            for k, lab in (("clients_root", "client folders location"), ("form_filler_dir", "Form Filler folder")):
                if vals[k] and not os.path.isdir(vals[k]):
                    e[k] = "This folder does not exist on this computer."
            if vals["form_filler_dir"] and "form_filler_dir" not in e and not os.path.isdir(os.path.join(vals["form_filler_dir"], "sch3", "engine")):
                e["form_filler_dir"] = "This folder has no sch3\\engine inside it, so it is not the Form Filler."
            if not vals["tally_port"].isdigit() or not 0 < int(vals["tally_port"]) < 65536:
                e["tally_port"] = "Enter a port number, usually 9000."
            if not (len(vals["financial_year"]) == 7 and vals["financial_year"][4] == "-" and vals["financial_year"].replace("-", "").isdigit()):
                e["financial_year"] = "Write it like 2025-26."
            if e:
                s = dict(s, **vals)
            else:
                self.s = s = config.save_settings(self.st, vals)
                ctx["fy"] = s["financial_year"]
                msg = '<div class="note ok" role="status">Saved.</div>'
        checks = "".join('<div class="tr" style="grid-template-columns:1fr 1.4fr auto"><span style="font-weight:500">%s</span><span class="mono mut">%s</span>%s</div>'
                         % (esc(a), esc(d), badge("Ready", "ok") if done else badge("Needs setting", "wa")) for a, done, d in self.checks())
        people = "".join('<a class="tr" style="grid-template-columns:1.2fr 1fr 1fr auto" href="/settings/people/%s"><span style="font-weight:500">%s</span><span class="mono">%s</span><span>%s</span>%s</a>'
                         % (u["id"], esc(u["name"]), esc(u["login"]), esc(u["role"].capitalize()), badge("Active", "ok") if u.get("active", True) else badge("Switched off"))
                         for u in self.users.all())
        body = (msg + '<div class="g"><div class="card s7"><div class="ch"><h2>This office</h2></div><div class="cb">'
                '<form method="post" action="/settings" style="display:flex;flex-direction:column;gap:16px">' + hidden(ctx["csrf"]) +
                field("Client folders location", "clients_root", s["clients_root"], e.get("clients_root", ""), mono=True, hint="For example D:\\Clients. One folder per client is kept here.") +
                field("Form Filler folder", "form_filler_dir", s["form_filler_dir"], e.get("form_filler_dir", ""), mono=True, hint="The Form-Filler checkout. Its Schedule III engine is used, not copied.") +
                '<div class="form">' + field("Tally computer", "tally_host", s["tally_host"], mono=True) +
                field("Tally port", "tally_port", str(s["tally_port"]), e.get("tally_port", ""), mono=True) + '</div>' +
                field("Financial year", "financial_year", s["financial_year"], e.get("financial_year", ""), mono=True) +
                '<div><button class="btn p" type="submit">Save settings</button></div></form></div></div>'
                '<div class="card s5"><div class="ch"><h2>Ready to work</h2></div>' + checks +
                '<div class="cb cap">Agents can never submit, pay, attach a DSC or approve an invoice, whatever is set here.</div></div>'
                '<div class="card s12"><div class="ch"><h2>People</h2><a class="btn" href="/settings/people/new">Add person</a></div>'
                '<div class="tr th" style="grid-template-columns:1.2fr 1fr 1fr auto"><span>Name</span><span>Sign-in name</span><span>Role</span><span>State</span></div>' + people +
                '<div class="cb cap">Partner: everything. Reviewer: prepare, review, see portal passwords. Staff: prepare. Fees are visible to partners only.</div></div></div>')
        return (422 if e else 200), {}, self.page(ctx, "settings", "Settings", body, sub="Office")

    def person_form(self, method, rest, form, ctx):
        u = None if rest == ["new"] else self.users.get(rest[0]) if len(rest) == 1 else None
        if rest != ["new"] and not u:
            return 404, {}, self.page(ctx, "settings", "Person not found", '<p><a href="/settings">Back to Settings</a></p>')
        e, data = {}, dict(u or {"role": "staff", "active": True})
        if method == "POST":
            active = form.get("active") == "1"
            data = dict(data, name=form.get("name", ""), login=form.get("login", data.get("login", "")), role=form.get("role", ""), active=active)
            e = self.users.validate(data["name"], data["login"], data["role"], form.get("password", ""), editing=u["id"] if u else None)
            if u and u["role"] == "partner" and (data["role"] != "partner" or not active) and len(self.users.partners()) <= 1 and not e:
                e["role"] = "This is the only partner. Make another person a partner first."
            if not e:
                if u:
                    self.users.update(u["id"], name=data["name"].strip(), role=data["role"], active=active, password=form.get("password", ""))
                else:
                    self.users.add(data["name"], data["login"], data["role"], form["password"])
                return redirect("/settings")
        body = ('<div class="card" style="max-width:560px"><div class="cb" style="border-top:none"><form method="post" action="/settings/people/%s" style="display:flex;flex-direction:column;gap:16px">'
                % (u["id"] if u else "new") + hidden(ctx["csrf"]) +
                field("Name", "name", data.get("name", ""), e.get("name", ""), required=True) +
                (('<div class="fld"><span class="lbl">Sign-in name</span><span class="mono">%s</span></div>' % esc(u["login"])) if u else
                 field("Sign-in name", "login", data.get("login", ""), e.get("login", ""), required=True, mono=True)) +
                select("Role", "role", [(r, r.capitalize()) for r in auth.ROLES], data.get("role", ""), e.get("role", "")) +
                field("New password" if u else "Password", "password", "", e.get("password", ""), typ="password",
                      hint="Leave blank to keep the current password." if u else "At least 8 characters.", auto="new-password") +
                ('<label class="chk"><input type="checkbox" name="active" value="1"%s> Can sign in</label>' % (" checked" if data.get("active", True) else "") if u
                 else '<input type="hidden" name="active" value="1">') +
                '<div style="display:flex;gap:12px"><button class="btn p" type="submit">Save</button><a class="btn" href="/settings">Cancel</a></div></form></div></div>')
        return (422 if e else 200), {}, self.page(ctx, "settings", "Edit person" if u else "Add person", body, sub="Settings")


def ok(html):
    return 200, {}, html


def redirect(to, headers=None):
    return 303, dict(headers or {}, Location=to), ""


class Handler(BaseHTTPRequestHandler):
    app = None
    server_version = "LodhaOS"

    def _go(self, method):
        u = urlsplit(self.path)
        query = {k: v[-1] for k, v in parse_qs(u.query).items()}
        form = {}
        if method == "POST":
            n = min(int(self.headers.get("Content-Length") or 0), 1_000_000)
            raw = parse_qs(self.rfile.read(n).decode("utf-8", "replace"), keep_blank_values=True)
            form = {k: v[-1] for k, v in raw.items()}
            form["_services"] = raw.get("services", [])
            form["_clients"] = raw.get("client", [])
        ck = SimpleCookie(self.headers.get("Cookie") or "")
        tok = ck[COOKIE].value if COOKIE in ck else ""
        try:
            status, headers, body = self.app.handle(method, u.path, query, form, tok)
        except Exception:
            import traceback
            traceback.print_exc()
            status, headers, body = 500, {}, ui.bare("Something went wrong", '<p>The OS hit an error on this page. It has been written to the server window. <a href="/">Go to Home</a>.</p>')
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(status)
        if "Content-Type" not in headers:
            self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._go("GET")

    def do_POST(self):
        self._go("POST")

    def log_message(self, fmt, *args):
        pass


def serve(host="127.0.0.1", port=config.PORT):
    Handler.app = App()
    srv = ThreadingHTTPServer((host, port), Handler)
    print("Lodha OS is running. Open http://%s:%d in Chrome. Close this window to stop it." % ("localhost" if host == "127.0.0.1" else host, port))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    serve(host="0.0.0.0" if "--lan" in sys.argv else "127.0.0.1")
