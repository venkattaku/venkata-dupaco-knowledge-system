"""The question-answering pipeline. One question goes through three steps (each step is written to the CSV log):

  1. ROUTE      the LLM picks verified queries (tools) and fills in their parameters
  2. QUERY      we run those queries on SQLite (a plain passage search is the fallback)
  3. INTERPRET  the LLM writes the answer from the returned rows only and names the rows it used; the URLs of
                those rows become the answer's sources

The two prompts below (ROUTE, INTERPRET) hold all the judgement; there is no keyword or rule logic in the code."""
import concurrent.futures as cf
import json
import re
import time

from contract import Answer, Source

from . import logger
from .catalog import Catalog
from .conflicts import find_conflicts
from .llm import LLM

REFUSAL = ("I can't find that on Dupaco's website, so I don't want to guess. "
           "Please contact Dupaco directly or visit dupaco.com/contact and a team member can help.")

ROUTE = ("You route questions about Dupaco Credit Union to verified database queries. Call the best tool(s) "
         "(at most 3) for the member's question. For open questions (who is eligible, where, what recognition) call search_text twice with differently worded queries: one for the topic, one for the scope words the answer would contain (places, counties, states, counts, 'time'). Snapshots exist for: %s. Set as_of (YYYY-MM-DD, e.g. 'as of May 2026' -> 2026-05-31) only if the question names a past date, else null.")
INTERPRET = ("Call the answer function. Answer the Dupaco Credit Union member's question using ONLY the numbered rows below. Rules: never write row numbers in the answer text (use the rows field only); rows with a 'headline' field are the main product of their category: when the question asks whether or which tiers/rates of the category exist, always include their tiers or top rate too, listed first; a row with a 'summary' field describes one product (lowest_rate, highest_rate, highest_rate_tier); when it has tiers_matching 0 no tier of that product meets the question's criterion, so answer No and state its highest_rate and highest_rate_tier; when the question is about a category's tiers, give the headline product's result first (its 'result' field), then name any 'other_product' rows that do match; for recognition/award/count questions, report the count or ordinal the NEWEST row states (e.g. 'the fifth time') and do not list the older years; name all places, states or counties a row lists for eligibility or coverage. Today's date is given; resolve 'last year', 'this year', 'recently' from it. If no row states a figure for the exact year asked, give every dated figure the rows state for it, each labelled with its year, and set partial=true with confident=true. Set confident=false only when your text states no figure or answer at all. If the question asks for a specific figure (a rate, fee or price) of a product that no row states (the product is not offered or no figure is published; saying so in words does not make the answer confident), set confident=false and add no figures from other products. "
             "copy numbers, dates and identifiers EXACTLY as written in the rows (no reformatting, plain digits); for rates give the rate type asked (APR for loans, APY for "
             "deposits) and the tier that matches the question; rows are already the canonical current values. Each row has a source tier: official > site page > newsroom/calculator > blog/pdf. Use the highest tier that answers the question and fall back to a lower tier only if the higher ones do not; within a tier take the newest by pub/eff (but for a past date use what was current then); if tiers disagree trust the higher tier. "
             "(prefer newer 'pub'/'eff' and lower 'rank' = more official page); if rows conflict or do not contain "
             "the answer, set confident=false and do not invent numbers; give both the rate and the APR when a row has both; if the question names no tier, list the relevant tiers; when sources differ prefer the newest dated one and say if hours/values vary by branch; Row urls omit the https://www.dupaco.com prefix: always write full URLs with it. For 'what link/URL to SEE information' give the page url where it lives; for 'how to join/apply/open' give the application link. When rows list names, options or places (e.g. wallet providers, states, counties) name ALL of them. When rows span several dates or tiers, report ONLY the current one (except for comparison questions such as whether things are the same/differ/vary across branches or over time: then the answer is No when more than one distinct schedule exists, and you MUST list EVERY schedule in the row's lines (Schedule 1, 2, ...), each with its dates and branch/event, using the exact wording incl. 'noon'): never mention older, superseded or alternative values or years. For link questions, the first row is the best page and its link_texts show what it covers: give its page_url (do not refuse just because the page title is generic). If the rows do not contain the specific thing asked (an unlisted product, branch or rate), set confident=false. Include geographic scope (states, counties) when rows mention it. Be concise (1-3 sentences). "
             "In `rows` list the row numbers you used.")
TIER = {1: "official", 2: "official", 3: "site page", 4: "newsroom/calculator", 5: "blog/pdf"}
ANSWER_TOOL = {"type": "function", "function": {
    "name": "answer", "description": "Final answer for the member.",
    "parameters": {"type": "object", "properties": {
        "text": {"type": "string"}, "confident": {"type": "boolean", "description": "true whenever text gives any figure or answer, including closest dated figures labelled with their years; false only if text is a pure refusal with no figures"},
        "partial": {"type": "boolean", "description": "true when text gives the closest available dated figures because no row matches the exact period or detail asked"}, "rows": {"type": "array", "items": {"type": "integer"}}}, "required": ["text", "confident", "rows"]}}}


class Engine:
    def __init__(self, store):
        self.store, self.cat, self.llm = store, Catalog(), LLM.from_env()
        self.pool = cf.ThreadPoolExecutor(max_workers=4)        # embeds the question while the router LLM runs
        if not self.llm:
            logger.warn_once("nokey", "DEEPINFRA_API_KEY not set: answering with plain passage search only.")

    def warm(self):
        """Touch the full-text index once so the first question does not pay for loading it."""
        self.store.q("SELECT 1 FROM sent_fts WHERE sent_fts MATCH 'rate' LIMIT 1")

    def conflicts(self):
        return find_conflicts(self.store)

    # ------------------------------------------------------------------ public entry point
    def answer(self, question, as_of=None):
        t0 = time.time()
        try:
            ans = self._answer((question or "").strip(), as_of)
        except Exception as e:                       # never crash a scoring run
            logger.log("error", q=question, error=repr(e))
            ans = Answer(text=REFUSAL, confident=False)
        logger.step(question, 4, "FINAL ANSWER", "confident=%s" % ans.confident,
                   "%s\nSOURCES: %s" % (ans.text, ", ".join(s.url for s in ans.sources)), int((time.time() - t0) * 1000))
        return ans

    # ------------------------------------------------------------------ the pipeline
    def _answer(self, q, as_of):
        if not self.store.snaps:
            return Answer(text=REFUSAL, confident=False)
        vec = self.store.vec
        qvec = self.pool.submit(vec.query_vec, q) if vec is not None and vec.ok else None    # runs while step 1 waits
        calls = self._route(q)
        rows, sid, asof = self._query(q, calls, as_of, qvec)
        if not rows:
            return Answer(text=REFUSAL, confident=False)
        for i, r in enumerate(rows):
            r["n"] = i                                         # the LLM cites rows by this number
        return self._interpret(q, rows, asof, sid)

    def _route(self, q):
        """Step 1 (ROUTE): the LLM chooses tools + params. Returns [(tool, args)]; without an LLM, a plain passage search."""
        if not self.llm:
            logger.step(q, 1, "No LLM: default query", q, "search_text " + q)
            return [("search_text", {"query": q})]
        t0 = time.time()
        system = ROUTE % ", ".join(t for _, t in self.store.snaps)
        calls = self.llm.tool_call(system, q, self.cat.schemas())
        logger.step(q, 1, "LLM: choose query", "SYSTEM: %s\nQUESTION: %s\nTOOLS: %s" % (system, q, ", ".join(self.cat.tools)),
                   "\n".join("%s %s" % (n, json.dumps(a, ensure_ascii=False)) for n, a in calls) if calls else "(no tool chosen)",
                   int((time.time() - t0) * 1000), self._llm_note())
        return calls or [("search_text", {"query": q})]

    def _query(self, q, calls, as_of, qvec):
        """Step 2 (QUERY): run the chosen queries on the snapshot that was current at the question's date.
        Returns (rows, snapshot id, 'as of' date). Falls back to passage search when nothing came back."""
        rows, sid, asof = [], None, as_of
        for name, args in calls[:3]:
            if name not in self.cat.tools:
                continue
            si = self.store.snap_for(as_of or args.get("as_of"))
            sid = self.store.snaps[si][0]
            asof = as_of or args.get("as_of") or self.store.snaps[si][1]       # also shown to the LLM as "today"
            t0 = time.time()
            got = self.cat.run(self.store, name, args, si, asof, self._vector(qvec) if name == "search_text" else None)
            logger.step(q, 2, "Query: " + name, "args=%s\nsnapshot=%s" % (json.dumps(args, ensure_ascii=False), sid),
                       "%d rows\n%s" % (len(got), "\n".join(json.dumps(r, ensure_ascii=False) for r in got)),
                       int((time.time() - t0) * 1000))
            rows += got
        if not rows and not all(c[0] == "search_text" for c in calls):
            si = self.store.snap_for(as_of)
            sid = self.store.snaps[si][0]
            rows = self.cat.run(self.store, "search_text", {"query": q}, si, None, self._vector(qvec))
            logger.step(q, 2, "Query: search_text (fallback, first query was empty)", "query=" + q,
                       "%d rows\n%s" % (len(rows), "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)))
        return rows, sid, asof

    def _interpret(self, q, rows, asof, sid):
        """Step 3: the LLM writes the answer from the (slimmed) rows and names the rows it used. The sources are the
        URLs of those rows (plus the official hours pages). A refusal carries the fixed, number-free REFUSAL text
        and no sources. Without an LLM answer, fall back to the best passage verbatim."""
        out = self._ask(q, rows, asof)
        if not out:
            return self._fallback(q, rows, sid)
        a = out[0][1]
        urls = self._source_urls(a, rows)
        confident = bool(a.get("confident", True))
        # "partial" = the closest figures were given because the exact period is not on the site: keep that text
        keep = confident or (bool(a.get("partial")) and bool(re.search(r"\d", a.get("text") or "")))
        logger.step(q, 3, "INTERPRET: sources", "rows used by the LLM: %s" % a.get("rows"),
                    "\n".join(urls[:4]) if keep else "(not confident: no sources)")
        return Answer(text=(a.get("text") or REFUSAL) if keep else REFUSAL, confident=keep,
                      sources=[Source(url=u, snapshot_id=sid) for u in urls[:4]] if keep else [])

    def _ask(self, q, rows, asof):
        """The INTERPRET LLM call. Returns the tool call, or None on failure."""
        if not self.llm:
            return None
        payload = json.dumps([self._slim(r) for r in rows[:40]], ensure_ascii=False, separators=(",", ":"))
        user = "Today's date: %s\nQuestion: %s\nRows: %s" % (asof, q, payload)
        t0 = time.time()
        out = self.llm.tool_call(INTERPRET, user, [ANSWER_TOOL], force="answer")
        logger.step(q, 3, "INTERPRET: write answer from rows", "SYSTEM: %s\n%s" % (INTERPRET, user),
                    json.dumps(out[0][1], ensure_ascii=False) if out else "(failed)",
                    int((time.time() - t0) * 1000), self._llm_note())
        return out

    @staticmethod
    def _fallback(q, rows, sid):
        """No LLM answer: return the best passage verbatim, or decline when the top row has no text."""
        top = rows[0]
        if not top.get("text"):
            logger.step(q, 3, "INTERPRET: fallback", "LLM answer unavailable; top row has no passage", "refusal")
            return Answer(text=REFUSAL, confident=False)
        logger.step(q, 3, "INTERPRET: fallback", "LLM answer unavailable", "top passage: " + top["text"][:600])
        return Answer(text=top["text"][:600], sources=[Source(url=top["url"], snapshot_id=sid)])

    @staticmethod
    def _source_urls(a, rows):
        """URLs of the rows the LLM used, official pages first."""
        used = [rows[i] for i in a.get("rows", []) if isinstance(i, int) and 0 <= i < len(rows)] or rows[:1]
        urls = []
        for r in used:
            for u in [r.get("url"), r.get("page_url"), r.get("example_link")] + (r.get("also") or "").split(","):
                if u and u.startswith("http") and u not in urls:
                    urls.append(u)
        for r in reversed([r for r in rows if r.get("kind") == "official-text"][:2]):    # hours: official pages always count
            if str(r.get("url", "")).startswith("http") and r["url"] not in urls:
                urls.insert(0, r["url"])
        for kind in {r.get("kind") for r in used} & {"lobby", "drive-up"}:      # hours: cite every distinct schedule's page
            for r in rows:
                if r.get("kind") == kind and str(r.get("url", "")).startswith("http") and r["url"] not in urls:
                    urls.append(r["url"])
        tier = {r["url"]: r.get("rank") or 9 for r in rows if r.get("url")}
        urls.sort(key=lambda u: tier.get(u, 9))                 # best tier first; stable, so the LLM's order holds within a tier
        return urls

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _vector(fut):
        """The question's embedding (None if vectors are off or it failed: search then uses keywords only)."""
        try:
            return fut.result(timeout=6) if fut is not None else None
        except Exception:
            return None

    def _llm_note(self):
        """One-line description of the last LLM call for the log: model, cache hit, retries, errors."""
        last = self.llm.last
        note = "model=%s%s" % (last["model"], " (cached)" if last["cached"] else "")
        if last.get("attempts"):
            note += " attempts=%d waited=%.1fs%s" % (last["attempts"], last["waited"], " HEDGED" if last.get("hedged") else "")
        if last["errors"]:
            note += " ERRORS: " + " | ".join(last["errors"])
        return note

    @staticmethod
    def _slim(r):
        """Shrink a row for the prompt (tokens are the latency bottleneck): drop empties/helpers, shorten URLs and text."""
        o = {k: v for k, v in r.items() if v not in (None, "") and k not in ("also", "head", "rank", "id")}
        if r.get("rank"):
            o["tier"] = TIER.get(r["rank"], "site page")
        for k in ("url", "page_url", "example_link"):
            if k in o:
                o[k] = o[k].replace("https://www.dupaco.com", "")
        if "text" in o:
            o["text"] = o["text"][:400]
        return o
