"""Financials: company choice, the Get data run, review points and the screens. Synthetic data only.
The fast tests use a stand-in engine. Set LODHA_OS_FORM_FILLER to a Form-Filler checkout to also run one real build."""
import csv
import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path

import openpyxl

from lodha_os import financials as F
from lodha_os.server import App
from lodha_os.store import Store

FIELDS = ["ledger_name", "group_name", "primary_group", "opening_balance", "net_debit", "net_credit", "closing_balance"]


def led(name, group, opening, closing):
    mv = closing - opening
    return dict(ledger_name=name, group_name=group, primary_group=group, opening_balance=opening,
                net_debit=mv if mv < 0 else 0, net_credit=mv if mv > 0 else 0, closing_balance=closing)


# Credit positive, debit negative, as Tally gives it. Profit for the year = sum of closing balances.
PY = [led("Share Capital", "Capital Account", 100000, 100000), led("Profit & Loss A/c", "Primary", 0, 0),
      led("Sample Bank", "Bank Accounts", -100000, -90000), led("Debtor One", "Sundry Debtors", 0, -80000),
      led("Creditor One", "Sundry Creditors", 0, 30000), led("Sales", "Sales Accounts", 0, 500000),
      led("Purchases", "Purchase Accounts", 0, -400000), led("Salaries", "Indirect Expenses", 0, -60000)]
CY = [led("Share Capital", "Capital Account", 100000, 100000), led("Profit & Loss A/c", "Primary", 40000, 40000),
      led("Sample Bank", "Bank Accounts", -90000, -215000), led("Debtor One", "Sundry Debtors", -80000, -120000),
      led("Creditor One", "Sundry Creditors", 30000, 45000), led("Sales", "Sales Accounts", 0, 900000),
      led("Purchases", "Purchase Accounts", 0, -600000), led("Salaries", "Indirect Expenses", 0, -120000),
      led("Rent", "Indirect Expenses", 0, -30000)]


class FakeTally:
    def __init__(self, open_cos, down=False):
        self.open, self.down, self.asked = open_cos, down, []

    def companies(self, host, port):
        if self.down:
            raise OSError("[WinError 10061] connection refused")
        return self.open

    def trial_balance(self, company, frm, to, host, port):
        self.asked.append((company, frm, to))
        return CY if frm.year == 2025 else PY

    @staticmethod
    def write_csv(rows, path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)

    @staticmethod
    def read_tb(path):
        with open(path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            for k in FIELDS[3:]:
                r[k] = float(r[k])
        return rows

    @staticmethod
    def net_profit(rows):
        return round(sum(r["closing_balance"] for r in rows), 2)


class FakeApproval:
    @staticmethod
    def analyse(cy, py, cfg):
        done = cfg.get("approvals", {})
        return [dict(ledger=r["ledger_name"], approved=r["ledger_name"] in done or r["group_name"] != "Indirect Expenses") for r in cy]


class FakePipeline:
    status = "OK"

    def build_workbook(self, cfg_path, cy, py, out, log=None):
        json.loads(Path(cfg_path).read_text(encoding="utf-8"))
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Checks"
        for row in (["Checks - all must read OK before issuing"], ["Check", "Current year", "Previous year", "Status"],
                    ["Balance Sheet tallies (Assets - Equity & Liabilities)", 0, 0, self.status], ["Suspense balances (should be nil)", 0, 0, "OK"],
                    ["Tolerance: Rs 1."], ["Balance Sheet line", "Per PY company", "Per PY column", "Difference"], ["Share capital", 1, 1, 0]):
            ws.append(row)
        wb.save(out)
        if log:
            log("Done")
        return out


def engine(open_cos, **kw):
    return F.Engine(FakeTally(open_cos, **kw), FakeApproval(), FakePipeline())


ONE = [{"name": "Sample Fasteners Pvt Ltd", "books_from": "2024-04-01"}]
TWO = [{"name": "Sample Fasteners Pvt Ltd - Audited", "books_from": "2025-04-01"},
       {"name": "Sample Fasteners Pvt Ltd - Audited 24-25", "books_from": "2024-04-01"},
       {"name": "Other Traders", "books_from": "2020-04-01"}]
CLIENT = dict(id="c1", name="Sample Fasteners Pvt Ltd", group="Sample Group", folder="Sample Group - Sample Fasteners Pvt Ltd", cin="U12345TN2000PTC000001")
SETTINGS = dict(form_filler_dir="", financial_year="2025-26", tally_host="localhost", tally_port=9000)


class Companies(unittest.TestCase):
    def test_years(self):
        self.assertEqual(F.fy_dates("2025-26"), (dt.date(2025, 4, 1), dt.date(2026, 3, 31)))
        self.assertEqual(F.prev_fy("2025-26"), "2024-25")
        self.assertEqual(F.prev_fy("2000-01"), "1999-00")

    def test_exact_name_wins(self):
        self.assertEqual(F.resolve_company("Sample Fasteners Pvt Ltd", ONE), ("Sample Fasteners Pvt Ltd", ""))
        self.assertEqual(F.resolve_company("sample fasteners pvt ltd", ONE)[0], "Sample Fasteners Pvt Ltd")

    def test_single_near_name_is_used_and_noted(self):
        name, note = F.resolve_company("Sample Fasteners Pvt Ltd", TWO[:1] + TWO[2:])
        self.assertEqual(name, "Sample Fasteners Pvt Ltd - Audited")
        self.assertIn("not open in Tally", note)

    def test_several_near_names_use_books_start(self):
        self.assertEqual(F.resolve_company("Sample Fasteners Pvt Ltd", TWO, dt.date(2025, 4, 1))[0], "Sample Fasteners Pvt Ltd - Audited")
        self.assertEqual(F.resolve_company("Sample Fasteners Pvt Ltd", TWO, dt.date(2024, 4, 1))[0], "Sample Fasteners Pvt Ltd - Audited 24-25")
        self.assertEqual(F.resolve_company("Sample Fasteners Pvt Ltd", TWO), (None, ""))

    def test_unknown_name_needs_a_pick(self):
        self.assertEqual(F.resolve_company("Nobody Ltd", TWO, dt.date(2025, 4, 1)), (None, ""))
        self.assertEqual(F.resolve_company("", TWO), (None, ""))

    def test_sibling_covers_last_year(self):
        self.assertEqual(F.sibling_for(TWO, "Sample Fasteners Pvt Ltd - Audited", dt.date(2024, 4, 1)), "Sample Fasteners Pvt Ltd - Audited 24-25")
        self.assertIsNone(F.sibling_for(TWO[:1], "Sample Fasteners Pvt Ltd - Audited", dt.date(2024, 4, 1)))


class Checks(unittest.TestCase):
    def test_failed_checks_stop_at_the_roll_forward_table(self):
        rows = [["Checks", "", "", ""], ["Check", "Current year", "Previous year", "Status"], ["Balance Sheet tallies", "5", "0", "ERROR"],
                ["Suspense", "0", "0", "OK"], ["Tolerance: Rs 1.", "", "", ""], ["Share capital", "1", "1", "0"], ["Reserves", "0", "4", "-4"]]
        self.assertEqual(F.failed_checks(rows), ["Balance Sheet tallies"])
        self.assertEqual(F.failed_checks([]), [])


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = str(Path(self.tmp.name) / "Clients")
        self.folder = Path(self.root) / CLIENT["folder"]

    def tearDown(self):
        self.tmp.cleanup()

    def trail(self):
        return [json.loads(l) for l in (self.folder / "_os" / "trail.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_get_data_reads_both_years_and_builds(self):
        eng = engine(TWO)
        st = F.get_data(CLIENT, self.root, SETTINGS, engine=eng)
        self.assertEqual(st["state"], "done")
        self.assertEqual([(c, f.year) for c, f, _ in eng.tally.asked],
                         [("Sample Fasteners Pvt Ltd - Audited", 2025), ("Sample Fasteners Pvt Ltd - Audited 24-25", 2024)])
        self.assertTrue((self.folder / "financials" / "2025-26" / "tb_cy.csv").exists())
        self.assertTrue((self.folder / "financials" / "2025-26" / "tb_py.csv").exists())
        self.assertTrue((self.folder / "Sample Fasteners Pvt Ltd - Schedule III FY2025-26.xlsx").exists())
        cfg = json.loads((self.folder / "financials" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["tally_company_py"], "Sample Fasteners Pvt Ltd - Audited 24-25")
        self.assertEqual(cfg["setup"]["Net profit as per Tally P&L - current year"], sum(r["closing_balance"] for r in CY))
        self.assertEqual(cfg["setup"]["Net profit as per Tally P&L - previous year"], sum(r["closing_balance"] for r in PY))
        self.assertEqual(cfg["setup"]["Current year - balance sheet date"], "31 March 2026")
        self.assertEqual(cfg["setup"]["CIN"], CLIENT["cin"])

    def test_every_step_is_in_the_trail_with_its_source(self):
        F.get_data(CLIENT, self.root, SETTINGS, user="Sam Staff", engine=engine(ONE))
        t = [x for x in self.trail() if x["kind"] == "financials"]
        read = [x for x in t if "trial balance read from Tally" in x["text"]]
        self.assertEqual(len(read), 2)
        self.assertEqual(read[0]["ledgers"], len(CY))
        self.assertEqual(read[0]["file"], "financials/2025-26/tb_cy.csv")
        self.assertIn("01-Apr-2025 to 31-Mar-2026", read[0]["text"])
        self.assertTrue(all(x["by"] == "Sam Staff" and x["at"] for x in t))
        self.assertIn("workbook built", t[-1]["text"])

    def test_review_points(self):
        F.get_data(CLIENT, self.root, SETTINGS, engine=engine(ONE))
        pts = F.status(CLIENT, self.root, "2025-26")["points"]
        self.assertEqual(pts, [("mapping", "2 ledgers mapped by the agent: a reviewer confirms the heads")])
        eng = engine(ONE)
        eng.pipeline.status = "ERROR"
        F.build(CLIENT, self.root, SETTINGS, engine=eng)
        self.assertIn(("check", "Balance Sheet tallies (Assets - Equity & Liabilities)"), F.status(CLIENT, self.root, "2025-26")["points"])

    def test_company_not_open_asks_staff_with_the_open_list(self):
        with self.assertRaises(F.StaffNeeded) as e:
            F.get_data(CLIENT, self.root, SETTINGS, engine=engine([{"name": "Other Traders", "books_from": "2020-04-01"}]))
        self.assertEqual(e.exception.pick, {"which": "tb_cy", "want": "Sample Fasteners Pvt Ltd", "open": ["Other Traders"]})

    def test_staff_pick_is_used_and_saved(self):
        eng = engine([{"name": "SF Books", "books_from": "2020-04-01"}])
        F.get_data(CLIENT, self.root, SETTINGS, picks={"tb_cy": "SF Books", "tb_py": "SF Books"}, engine=eng)
        self.assertEqual({c for c, _, _ in eng.tally.asked}, {"SF Books"})
        cfg = json.loads((self.folder / "financials" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["tally_company_cy"], "SF Books")

    def test_last_year_not_open_uses_the_stored_copy(self):
        F.get_data(CLIENT, self.root, SETTINGS, engine=engine(ONE))
        eng = engine([{"name": "Sample Fasteners Pvt Ltd", "books_from": "2025-04-01"}])
        st = F.get_data(CLIENT, self.root, SETTINGS, engine=eng)
        self.assertEqual(st["state"], "done")
        self.assertEqual(len(eng.tally.asked), 1)
        self.assertTrue(any("stored copy is used" in x["text"] for x in self.trail()))

    def test_last_year_missing_and_no_copy_asks_staff(self):
        with self.assertRaises(F.StaffNeeded) as e:
            F.get_data(CLIENT, self.root, SETTINGS, engine=engine([{"name": "Sample Fasteners Pvt Ltd", "books_from": "2025-04-01"}]))
        self.assertEqual(e.exception.pick["which"], "tb_py")

    def test_tally_closed_is_a_plain_message(self):
        with self.assertRaises(F.StaffNeeded) as e:
            F.get_data(CLIENT, self.root, SETTINGS, engine=engine(ONE, down=True))
        self.assertIn("Tally is not answering on port 9000", str(e.exception))

    def test_engine_missing(self):
        with self.assertRaises(F.EngineMissing):
            F.load_engine("")
        with self.assertRaises(F.EngineMissing):
            F.load_engine(self.tmp.name)


class Screens(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "Clients"
        self.root.mkdir()
        ff = Path(self.tmp.name) / "Form-Filler" / "sch3" / "engine"
        ff.mkdir(parents=True)
        (ff / "pipeline.py").write_text("", encoding="utf-8")
        self.app = App(Store(Path(self.tmp.name) / "data"))
        self.app.users.add("Pat Partner", "pat", "partner", "password1")
        _, h, _ = self.app.handle("POST", "/login", form=dict(login="pat", password="password1"))
        self.tok = h["Set-Cookie"].split("=", 1)[1].split(";")[0]
        self.csrf = self.app.sessions.get(self.tok)["csrf"]
        self.post("/settings", clients_root=str(self.root), form_filler_dir=str(ff.parent.parent), tally_host="localhost", tally_port="9000", financial_year="2025-26")
        self.ids = []
        for name, svc in (("Sample Fasteners Pvt Ltd", "Statutory Audit"), ("Sample Castings Pvt Ltd", "MCA Annual Compliance"),
                          ("Sample Traders LLP", "Accounting & MIS"), ("Sample Person", "Individual Income Tax Return")):
            self.post("/clients/new", name=name, group="Sample Group", constitution="Private Limited Company", _services=[svc])
        self.by = {c["name"]: c for c in self.app.clients.all()}

    def tearDown(self):
        self.tmp.cleanup()

    def get(self, path):
        return self.app.handle("GET", path, cookie=self.tok)

    def post(self, path, **form):
        return self.app.handle("POST", path, form=dict(form, csrf=self.csrf), cookie=self.tok)

    def use(self, open_cos):
        eng = engine(open_cos)
        self.app.fin_jobs.runner = lambda c, root, s, **kw: F.get_data(c, root, s, engine=eng, **kw)
        return eng

    def run_jobs(self):
        t = self.app.fin_jobs.thread
        if t:
            t.join(20)

    def test_list_shows_only_clients_with_financials_or_roc(self):
        s, _, html = self.get("/financials")
        self.assertEqual(s, 200)
        self.assertIn("Sample Fasteners Pvt Ltd", html)
        self.assertIn("Sample Traders LLP", html)
        self.assertNotIn("Sample Person", html)
        self.assertEqual(html.count('class="btn p"'), 1)

    def test_one_click_runs_three_clients(self):
        self.use([{"name": n, "books_from": "2020-04-01"} for n in self.by])
        ids = [self.by[n]["id"] for n in ("Sample Fasteners Pvt Ltd", "Sample Castings Pvt Ltd", "Sample Traders LLP")]
        s, h, _ = self.post("/financials/get-data", _clients=ids)
        self.assertEqual((s, h["Location"]), (303, "/financials"))
        self.run_jobs()
        for i in ids:
            self.assertEqual(self.app.fin_jobs.get(i)["state"], "review")
        self.assertEqual(len(list(self.root.glob("*/* - Schedule III FY2025-26.xlsx"))), 3)
        _, _, html = self.get("/financials")
        self.assertEqual(html.count("Review points"), 3)

    def test_pick_list_then_run_with_the_pick(self):
        self.use([{"name": "SF Books", "books_from": "2020-04-01"}])
        cid = self.by["Sample Fasteners Pvt Ltd"]["id"]
        self.post("/financials/get-data", _clients=[cid])
        self.run_jobs()
        self.assertEqual(self.app.fin_jobs.get(cid)["state"], "staff")
        _, _, html = self.get("/financials/" + cid)
        self.assertIn("Companies open in Tally now", html)
        self.assertIn("SF Books", html)
        self.post("/financials/get-data", _clients=[cid], pick_which="tb_cy", pick_company="SF Books", back="/financials/" + cid)
        self.run_jobs()
        self.assertEqual(self.app.fin_jobs.get(cid)["pick"]["which"], "tb_py")

    def test_view_and_download(self):
        self.use([{"name": n, "books_from": "2020-04-01"} for n in self.by])
        cid = self.by["Sample Fasteners Pvt Ltd"]["id"]
        self.post("/financials/get-data", _clients=[cid])
        self.run_jobs()
        s, _, html = self.get("/financials/" + cid)
        self.assertEqual(s, 200)
        self.assertIn("Checks in the workbook", html)
        self.assertIn("2 ledgers mapped by the agent", html)
        s, h, body = self.get("/financials/%s/workbook" % cid)
        self.assertEqual(s, 200)
        self.assertTrue(body[:2] == b"PK" and "attachment" in h["Content-Disposition"])

    def test_not_ready_without_settings(self):
        self.post("/settings", clients_root="", form_filler_dir="", tally_host="localhost", tally_port="9000", financial_year="2025-26")
        _, _, html = self.get("/financials")
        self.assertIn("client folders location is not set", html)
        self.post("/financials/get-data", _clients=[self.by["Sample Fasteners Pvt Ltd"]["id"]])
        self.assertEqual(self.app.fin_jobs.all(), {})

    def test_unknown_client_and_other_service(self):
        self.assertEqual(self.get("/financials/nope")[0], 404)
        self.assertEqual(self.get("/financials/" + self.by["Sample Person"]["id"])[0], 404)

    def test_restart_marks_running_jobs_failed(self):
        self.app.st.write("fin_jobs", {"x": {"state": "running", "note": ""}})
        self.assertEqual(F.Jobs(self.app.st).get("x")["state"], "failed")


@unittest.skipUnless(os.environ.get("LODHA_OS_FORM_FILLER"), "set LODHA_OS_FORM_FILLER to run a real Schedule III build")
class RealEngine(unittest.TestCase):
    def test_real_build_from_a_synthetic_trial_balance(self):
        real = F.load_engine(os.environ["LODHA_OS_FORM_FILLER"])
        fake = FakeTally(ONE)
        fake.write_csv, fake.read_tb, fake.net_profit = real.tally.write_csv, real.tally.read_tb, real.tally.net_profit
        with tempfile.TemporaryDirectory() as tmp:
            st = F.get_data(CLIENT, tmp, SETTINGS, engine=F.Engine(fake, real.approval, real.pipeline))
            self.assertEqual(st["state"], "done")
            names = [r[0] for r in st["checks"]]
            self.assertIn("Balance Sheet tallies (Assets - Equity & Liabilities)", names)
            self.assertEqual(st["ledgers"], len(CY))


if __name__ == "__main__":
    unittest.main()
