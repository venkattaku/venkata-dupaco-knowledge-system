"""Verified queries (verified_queries.json): the only SQL that ever runs. The LLM picks a tool and fills its params."""
import json
from pathlib import Path

from . import parse

PATH = Path(__file__).with_name("verified_queries.json")
TIER_FIELDS = ("url", "also", "rank", "family", "label", "eff", "rate", "apr", "apy")      # kept on a matching tier row
MAIN_PRODUCT = "main product of this category"      # flag on the row(s) of a category's headline product


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
            kws = [" ".join(parse.tokens(str(w))) for w in (args.get("keywords") or [])]
            kws = [w for w in kws if w][:6]
            for i, w in enumerate(kws):
                p["kw%d" % i] = "% " + w + " %"
            sql = sql.format(kw="".join(" AND hay LIKE :kw%d" % i for i in range(len(kws))))
            rows = store.q(sql, p)
            for r in rows:
                for c in ("hay", "lo", "hi", "yr_lo", "yr_hi", "rn"):
                    r.pop(c, None)
                main = t.get("headline", {}).get(r["family"])      # the category's main product (e.g. savings -> Share Savings)
                if main and r["label"].startswith(main):
                    r["headline"] = MAIN_PRODUCT
            rows.sort(key=lambda r: "headline" not in r)         # stable: main-product rows first, rest keep their order
            return rows
        if name == "rate_lookup":     # criteria search over rate tiers: product, rate value/range, dollar amount
            return self._rate_lookup(t, store.q(sql, p), args)
        if name == "branch_hours":
            return self._merge_hours(store.q(sql, p))
        if name == "search_text":     # passage search: keywords (FTS5) fused with vector similarity
            skip = parse.STOP | {"dupaco", "credit", "union"}
            words = [w for w in parse.tokens(str(args.get("query", ""))) if w not in skip]
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
            rows = self._fuse(store, rows[:20], qvec, si)
            # page outline: one row per section of the two best official pages, so facts that sit under a
            # neighbouring heading (e.g. "Local Service" next to "You're Eligible to Join") are visible too
            seen = {(r["url"], r["head"]) for r in rows}
            weight = {}                    # a page that matches several times beats one that ranks high once
            for n, r in enumerate(rows):
                if (r.get("rank") or 9) <= 3:
                    weight[r["url"]] = weight.get(r["url"], 0.0) + 1.0 / (5 + n)
            for u in sorted(weight, key=lambda u: -weight[u])[:2]:
                for r in store.q(t["outline_sql"], {"u": u, "si": si}):
                    if (r["url"], r["head"]) not in seen:
                        rows.append(r)
            return rows[:40]
        return store.q(sql, p)

    @staticmethod
    def _rate_lookup(t, tiers, args):
        """Apply the criteria to every tier of the family and summarise per product.

        Output rows: one `summary` row per product (lowest and highest rate, the tier where the highest applies,
        how many tiers match) followed by the matching tier rows. When a criterion matches nothing the summary
        still shows the product's real range, so the answer can say "no, it tops out at X"."""
        def product(r):
            return r["label"].split(" | ")[0]

        def rate(r):
            for k in ("apy", "apr", "rate"):
                if r.get(k) is not None:
                    return r[k]
            return None

        want = [w for w in parse.tokens(str(args.get("product") or "")) if w]
        picked = [r for r in tiers if all(w in parse.tokens(product(r)) for w in want)] if want else tiers
        picked = picked or tiers                       # unknown product name: fall back to the whole family
        eq, lo, hi, amt = (args.get(k) for k in ("apy_eq", "apy_min", "apy_max", "amount"))

        def matches(r):
            v = rate(r)
            return (v is not None
                    and (eq is None or abs(v - eq) < 0.005) and (lo is None or v >= lo) and (hi is None or v <= hi)
                    and (amt is None or r["lo"] is None or r["lo"] <= amt <= r["hi"]))

        by_product = {}
        for r in picked:
            by_product.setdefault(product(r), []).append(r)
        filtered = any(a is not None for a in (eq, lo, hi, amt))
        out = []
        for name, group in by_product.items():
            rs = [r for r in group if rate(r) is not None] or group
            top = max(rs, key=lambda r: rate(r) or 0)
            bottom = min(rs, key=lambda r: rate(r) or 0)
            hit = [r for r in rs if matches(r)]
            s = {"url": top["url"], "also": top["also"], "rank": top["rank"], "family": top["family"], "summary": name,
                 "tiers": len(rs), "lowest_rate": rate(bottom), "highest_rate": rate(top),
                 "highest_rate_tier": top["label"].split(" | ")[-1], "eff": top["eff"]}
            main = t.get("headline", {}).get(top["family"])
            if main and name.startswith(main):
                s["headline"] = MAIN_PRODUCT
            if filtered:
                s["tiers_matching"] = len(hit)
                s["result"] = ("%d of %d tiers meet the criterion; highest rate %s%% at %s"
                               % (len(hit), len(rs), rate(top), s["highest_rate_tier"]))
            out.append((s, hit if filtered else rs if args.get("product") else []))
        if filtered and not args.get("product"):
            # keep only the products that match, plus the category's main product (even with no match, so that "savings
            # tiers" shows its real range); other products are labelled as different products
            keep = [(s, h) for s, h in out if "headline" in s or s["tiers_matching"]]
            out = keep or out
            if any("headline" in s for s, _ in out):
                for s, _ in out:
                    if "headline" not in s:
                        s["other_product"] = "different product, not the category's main one"
        out.sort(key=lambda x: ("headline" not in x[0], -x[0]["highest_rate"] if x[0]["highest_rate"] is not None else 0))
        rows = []
        for s, tier_rows in out:
            rows.append(s)
            for r in tier_rows:
                rows.append({k: r[k] for k in TIER_FIELDS if r.get(k) not in (None, "")})
        return rows[:40]

    @staticmethod
    def _fuse(store, fts_rows, qvec, si):
        """Merge keyword hits and vector hits by reciprocal rank (a passage found by both rises to the top).
        Vector hits come from any snapshot, so they are filtered to passages that exist in snapshot `si`."""
        vec = store.vec
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

    @staticmethod
    def _merge_hours(rows):
        """One row per kind (lobby / drive-up) that lists every distinct schedule with its dates and branch/event,
        newest first. A single list is much harder for the LLM to under-report than several separate rows."""
        out, by_kind = [], {}
        for r in rows:
            if r["kind"] == "official-text":
                out.append(r)
            else:
                by_kind.setdefault(r["kind"], []).append(r)
        for kind, rs in by_kind.items():
            rs.sort(key=lambda r: r["pub"], reverse=True)
            lines = []
            for i, r in enumerate(rs, 1):
                span = r["pub"] if r["first_pub"] == r["pub"] else "%s to %s" % (r["first_pub"], r["pub"])
                lines.append("Schedule %d (%s; %s): %s" % (i, span, r["title"], "; ".join(json.loads(r["lines"]))))
            also = [u for r in rs for u in (r.get("also") or "").split(",") if u]
            urls = list(dict.fromkeys([r["url"] for r in rs] + also))          # one page per schedule first
            out.append({"url": rs[0]["url"], "title": "%d distinct %s schedules" % (len(rs), kind), "pub": rs[0]["pub"],
                        "rank": 4, "kind": kind, "lines": "\n".join(lines), "also": ",".join(urls)})
        return out
