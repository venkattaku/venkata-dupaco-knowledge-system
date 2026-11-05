"""Loads kb/verified_queries.json: every SQL statement the engine may run, plus the intent list."""
import json
from pathlib import Path

PATH = Path(__file__).with_name("verified_queries.json")


class Catalog:
    def __init__(self, path=PATH):
        self.doc = json.loads(Path(path).read_text(encoding="utf-8"))
        self.queries = self.doc["queries"]
        self.intents = self.doc["intents"]

    def sql(self, name, fmt=None):
        sql = self.queries[name]["sql"]
        return sql.format(**fmt) if fmt else sql

    def intent_names(self):
        return [i["name"] for i in self.intents]


class VerifiedStore:
    """Thin proxy over Store: `q(name, args)` only accepts names defined in the catalog (no ad-hoc SQL)."""

    def __init__(self, store, catalog):
        self._store, self._cat = store, catalog

    def q(self, name, args=(), fmt=None):
        return self._store.q(self._cat.sql(name, fmt), args)

    def __getattr__(self, item):
        return getattr(self._store, item)
