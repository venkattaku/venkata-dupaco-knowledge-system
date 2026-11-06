"""Verified queries (verified_queries.json): the only SQL that ever runs. The LLM picks a tool and fills its params."""
import json
from pathlib import Path

from . import parse as P

PATH = Path(__file__).with_name("verified_queries.json")


class Catalog:
    def __init__(self, path=PATH):
        self.tools = json.loads(Path(path).read_text(encoding="utf-8"))["tools"]

    def schemas(self):
        """OpenAI-style function-calling schemas, one per verified query."""
        return [{"type": "function", "function": {
            "name": n, "description": t["description"],
            "parameters": {"type": "object", "required": t.get("required", []), "properties": {
                k: ({"type": ["string", "null"]} if k == "as_of" else v) for k, v in t["params"].items()}}}}
            for n, t in self.tools.items()]

    def run(self, store, name, args, si, asof=None, qvec=None):
        """Execute tool `name` with LLM-supplied args against snapshot index `si`.

        Most tools are one SQL statement from verified_queries.json. `rates` and `search_text` also build part of
        the statement from the arguments (always as bound parameters or quoted tokens, never raw text)."""
        t = self.tools[name]
        args = {k: v for k, v in args.items() if v is not None}
        sql, p = t["sql"], {"si": si, "asof": asof or "9999-12-31"}
        for k in t["params"]:
            p[k] = args.get(k, t.get("defaults", {}).get(k))
        p.pop("as_of", None)
        if name == "rates":           # product-name keywords narrow the rate rows (one LIKE per keyword)
            kws = [" ".join(P.tokens(str(w))) for w in (args.get("keywords") or [])]
            kws = [w for w in kws if w][:6]
            for i, w in enumerate(kws):
                p["kw%d" % i] = "% " + w + " %"
            sql = sql.format(kw="".join(" AND hay LIKE :kw%d" % i for i in range(len(kws))))
            rows = store.q(sql, p)
            for r in rows:
                for c in ("hay", "lo", "hi", "yr_lo", "yr_hi", "rn"):
                    r.pop(c, None)
            return rows
        if name == "search_text":     # passage search: keywords (FTS5) fused with vector similarity
            words = [w for w in " ".join(P.tokens(str(args.get("query", "")))).split() if w not in P.STOP and w not in ("dupaco", "credit", "union")]
            rows = []
            if words:
                words = ['"%s"' % w.replace('"', "") for w in dict.fromkeys(words)]
                p.pop("query", None)
                p["match"] = " AND ".join(words)                 # precise first, then broaden
                rows = store.q(sql, p)
                if len(rows) < 15 and len(words) > 1:
                    p["match"] = " OR ".join(words)
                    seen = {(r["url"], r["head"], r["text"]) for r in rows}
                    rows += [r for r in store.q(sql, p) if (r["url"], r["head"], r["text"]) not in seen]
            rows = self._fuse(store, t, rows[:20], qvec, si)
            # page outline: one row per section of the two best official pages, so facts that sit under a
            # neighbouring heading (e.g. "Local Service" next to "You're Eligible to Join") are visible too
            seen = {(r["url"], r["head"]) for r in rows}
            for u in list(dict.fromkeys(r["url"] for r in rows[:4]))[:2]:
                for r in store.q(t["outline_sql"], {"u": u, "si": si}):
                    if (r["url"], r["head"]) not in seen:
                        rows.append(r)
            return rows[:36]
        return store.q(sql, p)

    @staticmethod
    def _fuse(store, t, fts_rows, qvec, si):
        """Merge keyword hits and vector hits by reciprocal rank (a passage found by both rises to the top).
        Vector hits come from any snapshot, so they are filtered to passages that exist in snapshot `si`."""
        vec = getattr(store, "vec", None)
        if vec is None or qvec is None:
            return fts_rows
        hits = vec.top(qvec, 80)
        if not hits:
            return fts_rows
        ids = [h[0] for h in hits]
        sim = dict(hits)
        got = {}
        for i in range(0, len(ids), 400):
            ch = ids[i:i + 400]
            for r in store.q("SELECT s.id, s.url, s.rank, s.pub, s.head, substr(s.text,1,500) AS text FROM sent s "
                             "WHERE s.id IN (%s) AND s.first_idx<=? AND s.last_idx>=?" % ",".join("?" * len(ch)),
                             ch + [si, si]):
                got[r["id"]] = r
        vrows = sorted(got.values(), key=lambda r: -(sim[r["id"]] - 0.015 * (r["rank"] or 3)))[:15]   # official pages win ties
        score, byid = {}, {}
        for lst in (fts_rows, vrows):
            for n, r in enumerate(lst):
                score[r["id"]] = score.get(r["id"], 0.0) + 1.0 / (60 + n)
                byid.setdefault(r["id"], r)
        return [byid[i] for i in sorted(score, key=lambda i: -score[i])][:20]
