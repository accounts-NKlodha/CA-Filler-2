import tempfile
import unittest
from pathlib import Path

from lodha_os import auth, config
from lodha_os.server import App
from lodha_os.store import Store

CLIENT = dict(name="Sample Fasteners Pvt Ltd", group="Sample Group", constitution="Private Limited Company",
              pan="AAGCS4821K", _services=["MCA Annual Compliance"])


class Passwords(unittest.TestCase):
    def test_hash_and_check(self):
        h = auth.hash_password("correct horse")
        self.assertNotIn("correct horse", h)
        self.assertTrue(auth.check_password("correct horse", h))
        self.assertFalse(auth.check_password("wrong", h))
        self.assertFalse(auth.check_password("x", "garbage"))


class Flow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = Store(Path(self.tmp.name) / "data")
        self.app = App(self.st)
        self.root = Path(self.tmp.name) / "Clients"
        self.root.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def start(self, role="partner"):
        self.app.users.add("Pat Partner", "pat", "partner", "password1")
        if role != "partner":
            self.app.users.add("Sam Staff", "sam", role, "password1")
        s, h, _ = self.app.handle("POST", "/login", form=dict(login="pat" if role == "partner" else "sam", password="password1"))
        self.assertEqual(s, 303)
        self.tok = h["Set-Cookie"].split("=", 1)[1].split(";")[0]
        self.csrf = self.app.sessions.get(self.tok)["csrf"]

    def get(self, path, **q):
        return self.app.handle("GET", path, query=q, cookie=self.tok)

    def post(self, path, **form):
        return self.app.handle("POST", path, form=dict(form, csrf=self.csrf), cookie=self.tok)

    def test_first_run_goes_to_setup_then_login(self):
        self.assertEqual(self.app.handle("GET", "/")[1]["Location"], "/setup")
        s, _, html = self.app.handle("POST", "/setup", form=dict(name="Pat", login="pat", password="short"))
        self.assertIn("at least 8", html)
        s, h, _ = self.app.handle("POST", "/setup", form=dict(name="Pat", login="pat", password="password1"))
        self.assertEqual((s, h["Location"]), (303, "/login"))
        self.assertEqual(self.app.users.all()[0]["role"], "partner")
        self.assertEqual(self.app.handle("GET", "/setup")[0], 303)

    def test_pages_need_sign_in(self):
        self.app.users.add("Pat", "pat", "partner", "password1")
        s, h, _ = self.app.handle("GET", "/clients")
        self.assertEqual((s, h["Location"]), (303, "/login?next=/clients"))
        self.assertEqual(self.app.handle("POST", "/login", form=dict(login="pat", password="nope"))[0], 401)

    def test_login_does_not_redirect_off_site(self):
        self.app.users.add("Pat", "pat", "partner", "password1")
        _, h, _ = self.app.handle("POST", "/login", form=dict(login="pat", password="password1", next="//evil.example"))
        self.assertEqual(h["Location"], "/")

    def test_post_without_csrf_is_refused(self):
        self.start()
        s, _, _ = self.app.handle("POST", "/clients/new", form=dict(CLIENT), cookie=self.tok)
        self.assertEqual(s, 403)
        self.assertEqual(self.app.clients.all(), [])

    def test_add_client_end_to_end(self):
        self.start()
        config.save_settings(self.st, {"clients_root": str(self.root)})
        s, h, _ = self.post("/clients/new", **CLIENT)
        self.assertEqual(s, 303)
        cid = self.app.clients.all()[0]["id"]
        self.assertTrue((self.root / "Sample Group - Sample Fasteners Pvt Ltd").is_dir())
        s, _, html = self.get("/clients/" + cid)
        self.assertIn("Sample Fasteners Pvt Ltd", html)
        self.assertIn("Client added", html)
        self.assertIn("Folder exists", html)
        self.assertIn(">ROC</a>", html)
        s, _, html = self.get("/clients", q="aagcs")
        self.assertIn("1 shown", html)
        self.assertIn("0 shown", self.get("/clients", line="GST")[2])

    def test_bad_client_is_shown_with_errors_and_not_saved(self):
        self.start()
        s, _, html = self.post("/clients/new", **dict(CLIENT, pan="BAD"))
        self.assertEqual(s, 422)
        self.assertIn("PAN is 10 characters", html)
        self.assertEqual(self.app.clients.all(), [])

    def test_html_is_escaped(self):
        self.start()
        self.post("/clients/new", **dict(CLIENT, name="<script>alert(1)</script> & Co", pan=""))
        html = self.get("/clients")[2]
        self.assertNotIn("<script>alert(1)", html)
        self.assertIn("&lt;script&gt;", html)

    def test_staff_cannot_open_settings(self):
        self.start("staff")
        self.assertEqual(self.get("/settings")[0], 403)
        self.assertEqual(self.post("/settings/people/new", name="X", login="x", role="partner", password="password1")[0], 403)
        self.assertEqual(len(self.app.users.all()), 2)

    def test_settings_validate_folders(self):
        self.start()
        s, _, html = self.post("/settings", clients_root="/no/such/folder", form_filler_dir="", tally_host="localhost", tally_port="9000", financial_year="2025-26")
        self.assertEqual(s, 422)
        self.assertIn("does not exist", html)
        s, _, _ = self.post("/settings", clients_root=str(self.root), form_filler_dir="", tally_host="localhost", tally_port="9000", financial_year="2025-26")
        self.assertEqual(s, 200)
        self.assertEqual(config.settings(self.st)["clients_root"], str(self.root))

    def test_last_partner_cannot_be_demoted_or_switched_off(self):
        self.start()
        uid = self.app.users.all()[0]["id"]
        s, _, html = self.post("/settings/people/" + uid, name="Pat", role="staff", active="1")
        self.assertEqual(s, 422)
        self.assertIn("only partner", html)
        self.assertEqual(self.app.users.get(uid)["role"], "partner")

    def test_switched_off_person_is_signed_out(self):
        self.start("staff")
        sam = self.app.users.by_login("sam")
        self.app.users.update(sam["id"], active=False)
        self.assertEqual(self.get("/clients")[0], 303)
        self.assertIsNone(self.app.users.login("sam", "password1"))

    def test_unbuilt_screens_say_so(self):
        self.start()
        for p in ("/proposals", "/financials", "/gst", "/tds", "/agents", "/inbox", "/billing"):
            s, _, html = self.get(p)
            self.assertEqual(s, 200)
            self.assertIn("Not built yet", html)
        self.assertEqual(self.get("/nothing-here")[0], 404)


if __name__ == "__main__":
    unittest.main()
