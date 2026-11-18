import tempfile
import unittest
from pathlib import Path

from lodha_os import clients, services
from lodha_os.store import Store

GOOD = dict(name="Sample Fasteners Pvt Ltd", group="Sample Group", constitution="Private Limited Company",
            pan="AAGCS4821K", gstin="33AAGCS4821K1Z6", cin="U28999TN2011PTC081234", mobile="98410 12345",
            email="Accounts@Example.com", services=["MCA Annual Compliance", "GST Monthly Compliance", "Not a service"])


class Validation(unittest.TestCase):
    def test_clean_normalises(self):
        c = clients.clean(dict(GOOD, pan=" aagcs4821k ", mobile="+91 98410-12345"))
        self.assertEqual(c["pan"], "AAGCS4821K")
        self.assertEqual(c["mobile"], "9841012345")
        self.assertEqual(c["email"], "accounts@example.com")
        self.assertEqual(c["services"], ["MCA Annual Compliance", "GST Monthly Compliance"])

    def test_good_record_has_no_errors(self):
        self.assertEqual(clients.validate(clients.clean(GOOD)), {})

    def test_bad_identifiers(self):
        e = clients.validate(clients.clean(dict(GOOD, pan="ABC", gstin="33XXXXX0000X1Z6", cin="123", mobile="12345", email="x")))
        self.assertEqual(set(e), {"pan", "gstin", "cin", "mobile", "email"})

    def test_gstin_must_contain_pan(self):
        e = clients.validate(clients.clean(dict(GOOD, gstin="33AAGCS9999K1Z6")))
        self.assertIn("PAN", e["gstin"])

    def test_llpin_accepted(self):
        self.assertEqual(clients.validate(clients.clean(dict(GOOD, cin="acx-1331", constitution="LLP"))), {})

    def test_name_and_constitution_required(self):
        e = clients.validate(clients.clean(dict(name="", constitution="")))
        self.assertEqual(set(e), {"name", "constitution"})


class Folders(unittest.TestCase):
    def test_group_dash_client(self):
        self.assertEqual(clients.folder_name("Sample Group", "Sample Fasteners Pvt Ltd"), "Sample Group - Sample Fasteners Pvt Ltd")

    def test_no_group_or_same_group(self):
        self.assertEqual(clients.folder_name("", "Alpha Traders"), "Alpha Traders")
        self.assertEqual(clients.folder_name("alpha traders", "Alpha Traders"), "Alpha Traders")

    def test_windows_unsafe_characters(self):
        n = clients.folder_name('A/B: "Group"', "M/s. X <Y> | Co.")
        for ch in '<>:"/\\|?*':
            self.assertNotIn(ch, n)
        self.assertFalse(n.endswith((".", " ")))

    def test_reserved_name(self):
        self.assertEqual(clients.folder_name("", "CON"), "CON (client)")

    def test_empty_name_refused(self):
        with self.assertRaises(ValueError):
            clients.folder_name("G", " . ")


class Master(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "Clients"
        self.root.mkdir()
        self.cl = clients.Clients(Store(Path(self.tmp.name) / "data"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_creates_folder_and_trail(self):
        c, e = self.cl.save(GOOD, "Tester", root=str(self.root))
        self.assertEqual(e, {})
        self.assertTrue((self.root / "Sample Group - Sample Fasteners Pvt Ltd" / "_os" / "trail.jsonl").exists())
        t = clients.read_trail(str(self.root), c)
        self.assertEqual((t[0]["text"], t[0]["by"]), ("Client added", "Tester"))

    def test_duplicate_pan_and_name_refused(self):
        self.cl.save(GOOD, "T")
        _, e = self.cl.save(dict(GOOD, name="Other Name Pvt Ltd"), "T")
        self.assertIn("pan", e)
        _, e = self.cl.save(dict(GOOD, pan="", gstin=""), "T")
        self.assertIn("name", e)
        self.assertEqual(len(self.cl.all()), 1)

    def test_edit_keeps_folder_and_records_change(self):
        c, _ = self.cl.save(GOOD, "T", root=str(self.root))
        c2, e = self.cl.save(dict(GOOD, name="Renamed Fasteners Pvt Ltd"), "T", cid=c["id"], root=str(self.root))
        self.assertEqual(e, {})
        self.assertEqual(c2["folder"], c["folder"])
        self.assertIn("name", clients.read_trail(str(self.root), c2)[0]["text"])
        self.assertEqual(len(self.cl.all()), 1)

    def test_same_folder_name_gets_a_suffix(self):
        a, _ = self.cl.save(dict(GOOD, pan="", gstin="", name="X: Y"), "T")
        b, e = self.cl.save(dict(GOOD, pan="", gstin="", name="X/ Y"), "T")
        self.assertEqual(e, {})
        self.assertNotEqual(a["folder"].lower(), b["folder"].lower())


class Services(unittest.TestCase):
    def test_every_service_has_a_line(self):
        self.assertTrue(all(l in services.LINES for l in services.SERVICES.values()))

    def test_lines_of(self):
        self.assertEqual(services.lines_of(["GST Refund", "Tax Audit"]), ["GST", "Income tax"])


if __name__ == "__main__":
    unittest.main()
