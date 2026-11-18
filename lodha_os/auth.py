"""Sign-in, roles and sessions.

Three roles (CLAUDE.md, Settings wireframe): partner, reviewer, staff. Agents are not users and have no role:
they can never submit, pay, attach a DSC or approve an invoice."""
import hashlib
import hmac
import secrets
import time

ROLES = ("partner", "reviewer", "staff")
PERMS = {
    "manage_users": ("partner",),
    "change_settings": ("partner",),
    "see_fees": ("partner",),
    "see_passwords": ("partner", "reviewer"),
    "review": ("partner", "reviewer"),
}
SESSION_HOURS = 12
ITER = 200_000


def can(user, perm):
    return bool(user) and user.get("role") in PERMS.get(perm, ())


def hash_password(pw, salt=None):
    salt = salt or secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, ITER)
    return "pbkdf2$%d$%s$%s" % (ITER, salt.hex(), h.hex())


def check_password(pw, stored):
    try:
        _, it, salt, h = stored.split("$")
        got = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(got.hex(), h)
    except Exception:
        return False


class Users:
    def __init__(self, st):
        self.st = st

    def all(self):
        return self.st.read("users", []) or []

    def get(self, uid):
        return next((u for u in self.all() if u["id"] == uid), None)

    def by_login(self, login):
        login = (login or "").strip().lower()
        return next((u for u in self.all() if u["login"] == login), None)

    def validate(self, name, login, role, pw, editing=None):
        e = {}
        login = (login or "").strip().lower()
        if not (name or "").strip():
            e["name"] = "Enter the person's name."
        if not login or not login.replace(".", "").replace("_", "").isalnum():
            e["login"] = "Use letters, digits, dot or underscore."
        else:
            other = self.by_login(login)
            if other and (not editing or other["id"] != editing):
                e["login"] = "This sign-in name is already used."
        if role not in ROLES:
            e["role"] = "Choose a role."
        if (pw or not editing) and len(pw or "") < 8:
            e["password"] = "Use at least 8 characters."
        return e

    def add(self, name, login, role, pw):
        with self.st.lock:
            users = self.all()
            u = {"id": secrets.token_hex(6), "name": name.strip(), "login": login.strip().lower(), "role": role,
                 "pw": hash_password(pw), "active": True}
            users.append(u)
            self.st.write("users", users)
            return u

    def update(self, uid, **kw):
        with self.st.lock:
            users = self.all()
            for u in users:
                if u["id"] == uid:
                    if kw.get("password"):
                        u["pw"] = hash_password(kw["password"])
                    for k in ("name", "role", "active"):
                        if k in kw:
                            u[k] = kw[k]
            self.st.write("users", users)

    def partners(self):
        return [u for u in self.all() if u["role"] == "partner" and u.get("active", True)]

    def login(self, login, pw):
        u = self.by_login(login)
        if u and u.get("active", True) and check_password(pw or "", u["pw"]):
            return u
        return None


class Sessions:
    """In memory: a restart signs everyone out, which is fine for an office-hours desktop app."""

    def __init__(self):
        self.s = {}

    def start(self, uid):
        tok = secrets.token_urlsafe(32)
        self.s[tok] = {"uid": uid, "csrf": secrets.token_urlsafe(16), "until": time.time() + SESSION_HOURS * 3600}
        return tok

    def get(self, tok):
        s = self.s.get(tok or "")
        if not s:
            return None
        if s["until"] < time.time():
            self.s.pop(tok, None)
            return None
        return s

    def end(self, tok):
        self.s.pop(tok or "", None)
