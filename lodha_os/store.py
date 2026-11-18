"""Small JSON file store. One file per collection, written atomically, guarded by one lock.

Enough for one office (about 10 staff, a few hundred clients). The data folder is outside git."""
import json
import os
import threading
from pathlib import Path


class Store:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def _path(self, name):
        return self.folder / (name + ".json")

    def read(self, name, default=None):
        with self.lock:
            p = self._path(name)
            if not p.exists():
                return default
            with open(p, encoding="utf-8") as f:
                return json.load(f)

    def write(self, name, value):
        with self.lock:
            p = self._path(name)
            tmp = p.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(value, f, indent=1, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, p)
            return value
