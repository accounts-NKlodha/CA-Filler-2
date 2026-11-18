"""Financials: "Get data" reads this year's and last year's trial balance from Tally and builds the Schedule III
workbook, for one client or several, through the shared Schedule III engine.

The engine is not copied here. It is loaded from the Form-Filler checkout named in Settings
(<form_filler_dir>/sch3/engine), so both apps always run the same reader and builder. Each client's files use the
same layout as Form Filler, inside the client folder:

    financials/config.json            mapping, approvals and Setup values, in the engine's format
    financials/<FY>/tb_cy.csv         this year's trial balance as read from Tally
    financials/<FY>/tb_py.csv         last year's
    financials/<FY>/last_build.json   checks from the built workbook and the build log
    <Client> - Schedule III FY<FY>.xlsx

Every step is written to the client's audit trail with its source (Tally company, period, ledger count).
"""
import datetime as dt
import importlib
import json
import os
import shutil
import sys
import threading
from pathlib import Path

from . import clients

DIV_KEY = "Rounding divisor (1 = Rs, 1000 = Rs '000, 100000 = Rs lakhs)"
AGENT = "agent"


class StaffNeeded(Exception):
    """The run cannot go on without a person: Tally is closed, or a company has to be picked."""

    def __init__(self, msg, pick=None):
        super().__init__(msg)
        self.pick = pick


class EngineMissing(Exception):
    pass


# ---------------------------------------------------------------- the shared engine

_ENGINES = {}


class Engine:
    def __init__(self, tally, approval, pipeline):
        self.tally, self.approval, self.pipeline = tally, approval, pipeline


def engine_dir(form_filler_dir):
    return Path(form_filler_dir or "") / "sch3" / "engine"


def load_engine(form_filler_dir):
    d = engine_dir(form_filler_dir)
    if not form_filler_dir or not (d / "pipeline.py").exists():
        raise EngineMissing("The Schedule III engine was not found. Set the Form Filler folder in Settings.")
    key = str(d.resolve())
    if key not in _ENGINES:
        if key not in sys.path:
            sys.path.insert(0, key)
        try:
            _ENGINES[key] = Engine(*(importlib.import_module(m) for m in ("tally", "approval", "pipeline")))
        except ImportError as e:
            raise EngineMissing("The Schedule III engine could not be loaded (%s). Run setup.bat once." % e)
    return _ENGINES[key]


# ---------------------------------------------------------------- paths, config

def fy_dates(fy):
    y = int(fy[:4])
    return dt.date(y, 4, 1), dt.date(y + 1, 3, 31)


def prev_fy(fy):
    y = int(fy[:4]) - 1
    return "%d-%02d" % (y, (y + 1) % 100)


def fin_dir(folder):
    return Path(folder) / "financials"


def cfg_path(folder):
    return fin_dir(folder) / "config.json"


def work_dir(folder, fy):
    d = fin_dir(folder) / fy
    d.mkdir(parents=True, exist_ok=True)
    return d


def out_name(client, fy):
    return "%s - Schedule III FY%s.xlsx" % (clients._part(client["name"]), fy)


def new_cfg(client, fy):
    y = int(fy[:4])
    co = client.get("tally_company") or client["name"]
    return {"client": client["name"], "fy": fy, "tally_company_cy": co, "tally_company_py": co,
            "groups": [], "ledgers": [], "head_labels": {}, "approvals": {}, "review_points": [],
            "setup": {"Company name": client["name"], "CIN": client.get("cin", ""),
                      "Current year - balance sheet date": "31 March %d" % (y + 1),
                      "Previous year - balance sheet date": "31 March %d" % y,
                      DIV_KEY: 1, "Amount label": "Amount in Rs",
                      "Annual return web link (or \"not hosted\")": "Not hosted"},
            "setup_notes": {}}


def load_cfg(folder, client, fy):
    p = cfg_path(folder)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return new_cfg(client, fy)


def _write_json(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, p)


def save_cfg(folder, cfg):
    _write_json(cfg_path(folder), cfg)


# ---------------------------------------------------------------- which Tally company

def norm(s):
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in (s or "")).split())


def _books_from(open_cos, company):
    for c in open_cos:
        if c["name"] == company:
            try:
                return dt.date.fromisoformat(c.get("books_from") or "")
            except ValueError:
                return None
    return None


def resolve_company(want, open_cos, start=None):
    """The open Tally company for `want`: the exact name, else the single open company whose name starts the
    same way ('X Ltd - Audited' for 'X Ltd'). When several start the same way, the one whose books begin latest
    on or before `start` (the first day of the year being read) is used. Returns (name, note), or (None, "")
    when staff must pick."""
    names = [c["name"] for c in open_cos]
    if want in names:
        return want, ""
    low = [n for n in names if n.lower() == want.lower()]
    if len(low) == 1:
        return low[0], ""
    near = [c for c in open_cos if norm(c["name"]).startswith(norm(want)) or norm(want).startswith(norm(c["name"]))] if norm(want) else []
    if len(near) > 1 and start:
        dated = []
        for c in near:
            try:
                bf = dt.date.fromisoformat(c.get("books_from") or "")
            except ValueError:
                continue
            if bf <= start:
                dated.append((bf, c))
        dated.sort(key=lambda x: x[0])
        near = [dated[-1][1]] if dated and (len(dated) == 1 or dated[-1][0] != dated[-2][0]) else []
    if len(near) == 1:
        return near[0]["name"], "'%s' is not open in Tally; using '%s', the open company with the same name" % (want, near[0]["name"])
    return None, ""


def sibling_for(open_cos, company, start):
    """Another open company of the same client whose books cover `start`. The latest such company wins."""
    base = norm(company.split(" - ")[0])
    best = None
    for c in open_cos:
        if c["name"] == company or not norm(c["name"]).startswith(base):
            continue
        try:
            bf = dt.date.fromisoformat(c.get("books_from") or "")
        except ValueError:
            continue
        if bf <= start and (best is None or bf > best[1]):
            best = (c["name"], bf)
    return best[0] if best else None


def _tally_problem(e, company, port):
    s = str(e)
    low = s.lower()
    if "did not answer within" in low:
        return StaffNeeded(s)
    if "10061" in s or "refused" in low or "timed out" in low or "unreachable" in low:
        return StaffNeeded("Tally is not answering on port %s: start Tally with the XML server on" % port)
    if "no ledgers" in low:
        return StaffNeeded("Open '%s' in Tally" % company)
    return e


# ---------------------------------------------------------------- the run

def get_data(client, root, settings, user=AGENT, say=None, picks=None, engine=None):
    """Read both years from Tally, then build. Returns the state dict that is also saved as last_build.json.
    picks: {"tb_cy": company, "tb_py": company} chosen by staff from the open companies."""
    say = say or (lambda m: None)
    picks = picks or {}
    eng = engine or load_engine(settings["form_filler_dir"])
    fy = settings["financial_year"]
    host, port = settings["tally_host"], int(settings["tally_port"])
    folder = clients.ensure_folder(root, client)
    cfg = load_cfg(folder, client, fy)
    cfg["fy"] = fy
    d = work_dir(folder, fy)

    def log(text, **data):
        clients.trail(root, client, "financials", text, user, **data)

    say("Checking which companies are open in Tally")
    try:
        open_cos = eng.tally.companies(host, port)
    except Exception as e:  # noqa: BLE001
        raise _tally_problem(e, "", port)
    names = [c["name"] for c in open_cos]
    if not names:
        raise StaffNeeded("No company is open in Tally: open the client's company")

    for which, label, year in (("tb_cy", "this year", fy), ("tb_py", "last year", prev_fy(fy))):
        key = "tally_company_cy" if which == "tb_cy" else "tally_company_py"
        frm, to = fy_dates(year)
        stored = (d / "tb_py.csv").exists() and which == "tb_py"
        want = picks.get(which) or cfg.get(key) or client.get("tally_company") or client["name"]
        company, note = resolve_company(want, open_cos, frm)
        if company and which == "tb_py" and not picks.get(which):
            bf = _books_from(open_cos, company)
            if bf and bf > frm:
                alt = sibling_for(open_cos, company, frm)
                if alt:
                    note = ("'%s' has books only from %s; last year is read from '%s', the open company with the same name "
                            "that covers %s" % (company, bf.strftime("%d-%b-%Y"), alt, frm.strftime("%d-%b-%Y")))
                    company = alt
                else:
                    company = None
        if not company:
            if stored:
                log("Last year's company is not open in Tally; the stored copy is used")
                continue
            raise StaffNeeded("Pick the Tally company for %s: '%s' is not open" % (label, want),
                              pick={"which": which, "want": want, "open": names})
        if note:
            log(note, which=which, company=company)
        say("Reading %s from Tally ('%s')" % (label, company))
        try:
            rows = eng.tally.trial_balance(company, frm, to, host, port)
            if not rows:
                raise ValueError("Tally returned no ledgers for '%s'" % company)
        except Exception as e:  # noqa: BLE001
            if stored:
                log("Last year's company was not read (%s); the stored copy is used" % e)
                continue
            raise _tally_problem(e, company, port)
        eng.tally.write_csv(rows, str(d / (which + ".csv")))
        np_key = "Net profit as per Tally P&L - " + ("current year" if which == "tb_cy" else "previous year")
        cfg[key] = company
        cfg["setup"][np_key] = eng.tally.net_profit(rows)
        cfg.setdefault("setup_notes", {})[np_key] = "Tally '%s', %s to %s, pulled %s" % (
            company, frm.strftime("%d-%b-%y"), to.strftime("%d-%b-%y"), dt.date.today().strftime("%d-%b-%y"))
        save_cfg(folder, cfg)
        log("%s year's trial balance read from Tally '%s' (%d ledgers, %s to %s)" % (
            label.split()[0].capitalize(), company, len(rows), frm.strftime("%d-%b-%Y"), to.strftime("%d-%b-%Y")),
            which=which, company=company, ledgers=len(rows), file="financials/%s/%s.csv" % (fy, which))
        say("Read %d ledgers for %s" % (len(rows), label))
    return build(client, root, settings, user=user, say=say, engine=eng)


def build(client, root, settings, user=AGENT, say=None, engine=None):
    """Build the Schedule III workbook from the stored trial balances (30 seconds to 3 minutes)."""
    say = say or (lambda m: None)
    eng = engine or load_engine(settings["form_filler_dir"])
    fy = settings["financial_year"]
    folder = clients.ensure_folder(root, client)
    d = work_dir(folder, fy)
    st = {"state": "running", "fy": fy, "log": [], "started": _now()}

    def keep(m):
        for line in str(m or "").splitlines():
            if line.strip():
                st["log"].append(line.strip())
    try:
        cy, py = d / "tb_cy.csv", d / "tb_py.csv"
        if not cy.exists():
            raise ValueError("No trial balance for this year yet: get data from Tally first")
        cfg = load_cfg(folder, client, fy)
        cfg["fy"] = fy
        if client.get("cin") and not cfg["setup"].get("CIN"):
            cfg["setup"]["CIN"] = client["cin"]
        save_cfg(folder, cfg)
        say("Building Schedule III (about a minute)")
        tmp_out = d / out_name(client, fy)
        eng.pipeline.build_workbook(str(cfg_path(folder)), str(cy), str(py) if py.exists() else None, str(tmp_out), log=keep)
        final = Path(folder) / out_name(client, fy)
        try:
            shutil.copyfile(tmp_out, final)
        except PermissionError:
            raise StaffNeeded("%s is open in Excel: close it and run again" % final.name)
        st["out"] = final.name
        st["checks"] = read_checks(final)
        rows = eng.approval.analyse(eng.tally.read_tb(str(cy)), eng.tally.read_tb(str(py)) if py.exists() else [], cfg)
        st["ledgers"] = len(rows)
        st["unapproved"] = [r["ledger"] for r in rows if not r.get("approved")]
        st["has_py"] = py.exists()
        st["state"] = "done"
        _write_json(review_path(folder, fy), {"cleared": {}, "verified": None})
        clients.trail(root, client, "financials", "Schedule III workbook built: %s" % final.name, user, file=final.name,
                      ledgers=len(rows), source="financials/%s/tb_cy.csv" % fy, mapping="financials/config.json")
    except StaffNeeded:
        raise
    except Exception as e:  # noqa: BLE001
        st["state"] = "error"
        st["error"] = str(e)
        clients.trail(root, client, "financials", "Schedule III build failed: %s" % str(e)[:300], user)
    st["finished"] = _now()
    st["by"] = user
    _write_json(d / "last_build.json", st)
    if st["state"] == "error":
        raise RuntimeError(st["error"])
    return st


def read_checks(path):
    """Rows of the workbook's own Checks sheet as lists of text."""
    import openpyxl  # needed by the engine anyway
    wb = openpyxl.load_workbook(path, data_only=True)
    if "Checks" not in wb.sheetnames:
        return []
    return [[str(c) if c is not None else "" for c in row[:4]] for row in wb["Checks"].iter_rows(values_only=True)
            if any(c not in (None, "") for c in row[:4])]


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- what the screen shows

def failed_checks(checks):
    """Names of the checks in the workbook's Checks sheet whose Status is not OK. The sheet has one row per check
    (name, current year, previous year, status), then a note starting 'Tolerance' and the roll-forward table."""
    bad = []
    for row in checks or []:
        if row and row[0].startswith("Tolerance"):
            break
        status = row[3].strip().upper() if len(row) > 3 else ""
        if status and status not in ("OK", "STATUS"):
            bad.append(row[0])
    return bad


def _slug(text):
    return "-".join("".join(ch.lower() if ch.isalnum() else " " for ch in text).split())[:60]


def review_path(folder, fy):
    return fin_dir(folder) / fy / "review.json"


def load_review(folder, fy):
    p = review_path(folder, fy)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"cleared": {}, "verified": None}


def status(client, root, fy):
    """What the screens show for one client and year.
    points: [{"id", "kind", "text", "cleared": {"by", "at", "note"} | None}]. A mapping point is never cleared by
    hand: it goes when a reviewer approves the heads and the workbook is rebuilt."""
    out = {"tb_cy": None, "tb_py": None, "build": None, "workbook": None, "points": [], "open": 0, "verified": None, "stale": False}
    if not root:
        return out
    folder = clients.folder_path(root, client)
    d = fin_dir(folder) / fy
    cfg = {}
    if cfg_path(folder).exists():
        try:
            cfg = json.loads(cfg_path(folder).read_text(encoding="utf-8"))
        except ValueError:
            cfg = {}
    for which, key in (("tb_cy", "tally_company_cy"), ("tb_py", "tally_company_py")):
        p = d / (which + ".csv")
        if p.exists():
            out[which] = {"company": cfg.get(key, ""), "at": dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")}
    lb = d / "last_build.json"
    if lb.exists():
        try:
            out["build"] = json.loads(lb.read_text(encoding="utf-8"))
        except ValueError:
            pass
    wb = Path(folder) / out_name(client, fy)
    if wb.exists():
        out["workbook"] = wb
    b = out["build"]
    rv = load_review(folder, fy)
    if b and b.get("state") == "done":
        pts = [("check:" + _slug(c), "check", c) for c in failed_checks(b.get("checks"))]
        n = len(b.get("unapproved") or [])
        if n:
            pts.append(("mapping", "mapping", "%d ledgers mapped by the agent: a reviewer confirms the heads" % n))
        if not b.get("has_py"):
            pts.append(("no-last-year", "data", "Last year's trial balance is missing: comparatives are blank"))
        for pid, kind, text in pts:
            out["points"].append({"id": pid, "kind": kind, "text": text, "cleared": None if kind == "mapping" else rv["cleared"].get(pid)})
        out["stale"] = bool(rv.get("stale"))
        out["verified"] = rv.get("verified")
    out["open"] = sum(1 for p in out["points"] if not p["cleared"])
    return out


# ---------------------------------------------------------------- the reviewer's part

def mapping_rows(client, root, fy, eng):
    """Every ledger with its Tally default and proposed Schedule III head (the engine's analysis)."""
    folder = clients.folder_path(root, client)
    d = fin_dir(folder) / fy
    cy, py = d / "tb_cy.csv", d / "tb_py.csv"
    if not cy.exists():
        return []
    return eng.approval.analyse(eng.tally.read_tb(str(cy)), eng.tally.read_tb(str(py)) if py.exists() else [], load_cfg(folder, client, fy))


def approve_heads(client, root, fy, decisions, user, eng):
    """decisions: {ledger: head code}. Records the approver on each ledger in config.json and in the trail.
    The workbook is then out of date until it is rebuilt, and any earlier tick is withdrawn."""
    codes = {o["code"]: o["label"] for o in eng.approval.head_options()}
    decisions = {l: c for l, c in decisions.items() if c in codes}
    if not decisions:
        return 0
    folder = clients.folder_path(root, client)
    cfg = load_cfg(folder, client, fy)
    rows = mapping_rows(client, root, fy, eng)
    known = {r["ledger"]: r for r in rows}
    decisions = {l: c for l, c in decisions.items() if l in known}
    eng.approval.apply_decisions(cfg, rows, decisions, user, fy)
    save_cfg(folder, cfg)
    for led, code in decisions.items():
        was = (known[led].get("proposed") or {}).get("code", "")
        clients.trail(root, client, "financials", "Ledger '%s' mapped to %s%s" % (led, codes[code], "" if was == code else " (reviewer changed the proposed head)"),
                      user, ledger=led, code=code, proposed=was, override=was != code)
    rv = load_review(folder, fy)
    rv.update(verified=None, stale=True)
    _write_json(review_path(folder, fy), rv)
    return len(decisions)


def clear_point(client, root, fy, pid, user, note):
    """A reviewer accepts one review point, with the reason. Mapping points cannot be cleared this way."""
    note = " ".join((note or "").split())
    st = status(client, root, fy)
    pt = next((p for p in st["points"] if p["id"] == pid), None)
    if not pt:
        raise ValueError("This review point is no longer open")
    if pt["kind"] == "mapping":
        raise ValueError("Confirm the ledger heads to clear this point")
    if len(note) < 5:
        raise ValueError("Write why this point is acceptable: the reason is kept in the audit trail")
    folder = clients.folder_path(root, client)
    rv = load_review(folder, fy)
    rv["cleared"][pid] = {"by": user, "at": _now(), "note": note}
    _write_json(review_path(folder, fy), rv)
    clients.trail(root, client, "financials", "Review point cleared: %s. Reason: %s" % (pt["text"], note), user, point=pid)


def verify(client, root, fy, user):
    """The reviewer's tick: financials verified. Only with a current workbook and no open point."""
    st = status(client, root, fy)
    if not st["workbook"]:
        raise ValueError("There is no Schedule III workbook yet")
    if st["stale"]:
        raise ValueError("Heads were changed after the workbook was built: rebuild it first")
    if st["open"]:
        raise ValueError("%d review points are still open" % st["open"])
    folder = clients.folder_path(root, client)
    rv = load_review(folder, fy)
    rv["verified"] = {"by": user, "at": _now(), "workbook": st["workbook"].name}
    _write_json(review_path(folder, fy), rv)
    clients.trail(root, client, "financials", "Financials verified: %s" % st["workbook"].name, user, file=st["workbook"].name)


def unverify(client, root, fy, user):
    folder = clients.folder_path(root, client)
    rv = load_review(folder, fy)
    if rv.get("verified"):
        rv["verified"] = None
        _write_json(review_path(folder, fy), rv)
        clients.trail(root, client, "financials", "Verified tick withdrawn", user)


# ---------------------------------------------------------------- job board: one client at a time, Tally is single

class Jobs:
    """Runs Get data for the chosen clients one after another on a worker thread. The latest job per client is
    kept in the store so the screen survives a refresh; a job left running by a restart is marked failed."""

    def __init__(self, st, runner=get_data, builder=build):
        self.st, self.runner, self.builder = st, runner, builder
        self.lock = threading.RLock()
        self.queue = []
        self.thread = None
        jobs = self.st.read("fin_jobs", {}) or {}
        for j in jobs.values():
            if j["state"] in ("queued", "running"):
                j.update(state="failed", note="The OS was restarted while this was running: run it again")
        self.st.write("fin_jobs", jobs)

    def all(self):
        return self.st.read("fin_jobs", {}) or {}

    def get(self, cid):
        return self.all().get(cid)

    def _set(self, cid, **kw):
        with self.lock:
            jobs = self.all()
            jobs.setdefault(cid, {}).update(kw)
            self.st.write("fin_jobs", jobs)

    def busy(self):
        return any(j["state"] in ("queued", "running") for j in self.all().values())

    def start(self, rows, root, settings, user, picks=None, wait=False, rebuild=False):
        """rows: client dicts. picks: {client id: {"tb_cy"|"tb_py": company}}.
        rebuild: build again from the stored trial balances without reading Tally."""
        with self.lock:
            for c in rows:
                j = self.get(c["id"])
                if j and j["state"] in ("queued", "running"):
                    continue
                self._set(c["id"], state="queued", note="Waiting for its turn", pick=None, by=user, at=_now(), fy=settings["financial_year"])
                self.queue.append((c, root, dict(settings), user, (picks or {}).get(c["id"]), rebuild))
            if not self.thread or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._work, daemon=True)
                self.thread.start()
        if wait:
            self.thread.join()

    def _work(self):
        while True:
            with self.lock:
                if not self.queue:
                    return
                c, root, settings, user, picks, rebuild = self.queue.pop(0)
            cid = c["id"]
            self._set(cid, state="running", note="Starting")
            try:
                say = lambda m: self._set(cid, note=m)
                if rebuild:
                    st = self.builder(c, root, settings, user=AGENT, say=say)
                else:
                    st = self.runner(c, root, settings, user=AGENT, say=say, picks=picks)
                pts = status(c, root, settings["financial_year"])["open"]
                self._set(cid, state="review" if pts else "done", done=_now(),
                          note="%d review points for the reviewer" % pts if pts else "Schedule III ready, no open points")
                clients.trail(root, c, "financials", "%s finished: %s (started by %s)" % ("Rebuild" if rebuild else "Get data", st.get("out", ""), user), AGENT)
            except StaffNeeded as e:
                self._set(cid, state="staff", note=str(e), pick=e.pick, done=_now())
            except Exception as e:  # noqa: BLE001
                self._set(cid, state="failed", note=str(e)[:400], done=_now())
