"""Where things live. Office-specific values are in settings (data/settings.json), never in the repo."""
import os
from pathlib import Path

from .store import Store

ROOT = Path(__file__).resolve().parent.parent
PORT = 8750  # Form Filler is 8742, the old Schedule III app 8765

DEFAULTS = {
    "clients_root": "",       # e.g. D:\Clients ; one folder per client: "Group name - Client name"
    "form_filler_dir": "",    # checkout of the Form-Filler repo; its sch3/engine is reused, not copied
    "tally_host": "localhost",
    "tally_port": 9000,
    "financial_year": "2025-26",
}


def data_dir():
    return Path(os.environ.get("LODHA_OS_DATA") or ROOT / "data")


def store():
    return Store(data_dir())


def settings(st):
    s = dict(DEFAULTS)
    s.update(st.read("settings", {}) or {})
    return s


def save_settings(st, values):
    s = settings(st)
    for k in DEFAULTS:
        if k in values:
            v = values[k]
            s[k] = int(v) if k == "tally_port" else str(v).strip()
    return st.write("settings", s)
