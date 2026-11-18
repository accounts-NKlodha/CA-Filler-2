"""Client master and client folders.

One folder per client under the clients root, named "Group name - Client name" (the firm's existing rule).
Everything the OS records about a client's work goes in that folder, including the audit trail."""
import datetime as dt
import json
import re
import secrets
from pathlib import Path

from . import services

CONSTITUTIONS = ("Private Limited Company", "Public Limited Company", "LLP", "Partnership Firm", "Proprietorship",
                 "Trust", "Society", "HUF", "Individual")
PAN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
GSTIN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
CIN = re.compile(r"^[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$")
LLPIN = re.compile(r"^[A-Z]{3}-[0-9]{4}$")
MOBILE = re.compile(r"^[6-9][0-9]{9}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {"COM%d" % i for i in range(1, 10)} | {"LPT%d" % i for i in range(1, 10)}
FIELDS = ("name", "group", "constitution", "pan", "gstin", "cin", "contact", "mobile", "email", "tally_company")


def clean(data):
    c = {k: " ".join(str(data.get(k, "")).split()) for k in FIELDS}
    for k in ("pan", "gstin", "cin"):
        c[k] = c[k].upper().replace(" ", "")
    c["mobile"] = re.sub(r"[\s-]", "", c["mobile"])
    if c["mobile"].startswith("+91"):
        c["mobile"] = c["mobile"][3:]
    c["email"] = c["email"].lower()
    c["services"] = [s for s in data.get("services", []) if s in services.SERVICES]
    return c


def validate(c, others=()):
    """Returns {field: message}. `others` are the other clients, for duplicate checks."""
    e = {}
    if not c["name"]:
        e["name"] = "Enter the client's legal name."
    if c["constitution"] not in CONSTITUTIONS:
        e["constitution"] = "Choose the constitution."
    if c["pan"] and not PAN.match(c["pan"]):
        e["pan"] = "PAN is 10 characters, like AAAAA9999A."
    if c["gstin"] and not GSTIN.match(c["gstin"]):
        e["gstin"] = "GSTIN is 15 characters, like 33AAAAA9999A1Z5."
    elif c["gstin"] and c["pan"] and c["gstin"][2:12] != c["pan"]:
        e["gstin"] = "Characters 3 to 12 of the GSTIN must be the PAN."
    if c["cin"] and not (CIN.match(c["cin"]) or LLPIN.match(c["cin"])):
        e["cin"] = "Enter a 21-character CIN, or an LLPIN like AAA-1234."
    if c["mobile"] and not MOBILE.match(c["mobile"]):
        e["mobile"] = "Enter a 10-digit mobile number."
    if c["email"] and not EMAIL.match(c["email"]):
        e["email"] = "Enter a valid e-mail address."
    for o in others:
        if c["pan"] and o.get("pan") == c["pan"] and "pan" not in e:
            e["pan"] = "Another client already has this PAN: %s." % o["name"]
        if c["name"] and o["name"].lower() == c["name"].lower() and (o.get("group") or "").lower() == c["group"].lower():
            e["name"] = "A client with this name already exists in this group."
    return e


def _part(s):
    s = BAD.sub(" ", s)
    s = " ".join(s.split()).rstrip(". ")
    if s.upper() in RESERVED:
        s += " (client)"
    return s


def folder_name(group, name):
    """'Group name - Client name'; just the client name when there is no separate group."""
    g, n = _part(group or ""), _part(name or "")
    if not n:
        raise ValueError("client name is empty")
    out = n if not g or g.lower() == n.lower() else g + " - " + n
    return out[:150].rstrip(". ")


class Clients:
    def __init__(self, st):
        self.st = st

    def all(self):
        return sorted(self.st.read("clients", []) or [], key=lambda c: ((c.get("group") or c["name"]).lower(), c["name"].lower()))

    def get(self, cid):
        return next((c for c in self.all() if c["id"] == cid), None)

    def save(self, data, user, cid=None, root=""):
        """Add or update. Returns (client, errors). The folder is created on add and never renamed afterwards:
        renaming a folder that staff have open breaks their files, so a name change keeps the old folder."""
        with self.st.lock:
            rows = self.st.read("clients", []) or []
            c = clean(data)
            errors = validate(c, [r for r in rows if r["id"] != cid])
            if errors:
                return c, errors
            now = dt.datetime.now().isoformat(timespec="seconds")
            if cid:
                row = next(r for r in rows if r["id"] == cid)
                changed = [k for k in FIELDS + ("services",) if row.get(k) != c[k]]
                row.update(c)
                row["updated"] = now
                what = "Client details changed: " + ", ".join(changed) if changed else ""
            else:
                row = dict(c, id=secrets.token_hex(6), created=now, created_by=user, folder=folder_name(c["group"], c["name"]))
                taken = {r["folder"].lower() for r in rows}
                base, i = row["folder"], 2
                while row["folder"].lower() in taken:
                    row["folder"] = "%s (%d)" % (base, i)
                    i += 1
                rows.append(row)
                what = "Client added"
            self.st.write("clients", rows)
        if root:
            ensure_folder(root, row)
            if what:
                trail(root, row, "client", what, user)
        return row, {}


def folder_path(root, client):
    return Path(root) / client["folder"]


def ensure_folder(root, client):
    p = folder_path(root, client)
    (p / "_os").mkdir(parents=True, exist_ok=True)
    return p


def trail(root, client, kind, text, user, **data):
    """Append one line to the client's audit trail (kept in the client folder, 8 years with the folder)."""
    p = ensure_folder(root, client) / "_os" / "trail.jsonl"
    rec = dict(data, at=dt.datetime.now().isoformat(timespec="seconds"), kind=kind, text=text, by=user)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def read_trail(root, client, limit=50):
    p = folder_path(root, client) / "_os" / "trail.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out[-limit:][::-1]
