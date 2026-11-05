"""Question router + verified queries over the SQLite store.

answer(q) -> classify intent with rules -> run a parameterised, vetted query -> render from a template.
Anything the catalog does not cover falls back to BM25 passage retrieval, and low-confidence
retrieval becomes an honest "I can't find that" (confident=False, no numbers).
"""
import json
import math
import re
import threading
from collections import Counter, defaultdict

from contract import Answer, Conflict, Source

from . import parse as P
from .catalog import Catalog, VerifiedStore
from .router import GroqRouter

REFUSAL = ("I can't find that on Dupaco's website, so I don't want to guess. "
           "Please contact Dupaco directly or visit dupaco.com/contact and a team member can help.")

# program words the site never publishes a rate for -> refuse instead of quoting a neighbour
UNLISTED = {"arm", "adjustable", "construction", "fha", "va", "usda", "bridge", "reverse", "heloc", "boat",
            "rv", "student", "lot", "land", "manufactured", "balloon"}

FAMILY_WORDS = {
    "mortgage": r"mortgage|home loan|home-loan|refinanc|\b(?:10|15|20|30)[- ]?(?:year|yr)\b|fixed[- ]rate",
    "home_improvement": r"home improvement",
    "auto": r"\bauto\b|\bcar loan|vehicle|model[- ]year|\bmotorcycle",
    "personal_loan": r"personal loan",
    "cert": r"certificate|\bcds?\b|\bcd rate",
    "checking": r"checking",
    "card": r"credit card|\bvisa\b|platinum|rewards card",
    "savings": r"savings|money market|\bhsa\b|health savings|bright|launchpad|holiday club|you name it|high[- ]yield|dividend",
}
RATE_WORDS = re.compile(r"\b(rate|rates|apr|apy|dividend|interest|yield|pay|pays|earn|earns|cost|charge|percent|"
                        r"how much|offer|offers|tier|tiers)\b", re.I)


def _fmt_pct(x):
    return "%.2f%%" % x if x is not None else ""


def _fmt_money(x):
    return "${:,.0f}".format(x) if float(x).is_integer() else "${:,.2f}".format(x)


def _us_date(iso):
    if not iso:
        return ""
    y, m, d = iso.split("-")
    return "%s/%s/%s" % (m, d, y)


class Engine:
    def __init__(self, store):
        self.cat = Catalog()
        self.s = VerifiedStore(store, self.cat)
        self.router = GroqRouter.from_env(self.cat)      # None unless GROQ_API_KEY is set
        self._tl = threading.local()
        self._idf = None

    # ============================================================ public
    def warm(self):
        """Pre-load the IDF table so the first answer isn't slower than the rest."""
        self._idf = None
        self._load_idf()
        self.s.q("warm_fts")

    def answer(self, question, as_of=None):
        q = (question or "").strip()
        ql = q.lower()
        as_of = as_of or self._infer_as_of(ql)
        si = self.s.snap_for(as_of)
        if si is None:
            return Answer(text=REFUSAL, confident=False)
        try:
            routed = self._route_with_groq(q, ql, si, as_of)
            if routed is not None:
                return routed
            for handler in (self.h_routing, self.h_closure, self.h_count, self.h_hours, self.h_address,
                            self.h_link, self.h_cards, self.h_rates, self.h_unlisted,
                            self.h_eligibility, self.h_contact_update):
                a = handler(q, ql, si, as_of)
                if a is not None:
                    return a
            return self.h_retrieve(q, ql, si)
        except Exception as e:                      # never crash a scoring run
            return Answer(text=REFUSAL, confident=False, conflict_note="internal error: %s" % e)

    # ============================================================ intent routing
    def _is(self, intent):
        return getattr(self._tl, "force", None) == intent

    def _route_with_groq(self, q, ql, si, as_of):
        """Groq picks the intent; the matching verified-query handler runs with its keyword gate bypassed.
        Returns None when there is no router/key, the call fails, or the handler declines (rules take over)."""
        if self.router is None:
            return None
        route = self.router.route(q)
        if not route:
            return None
        intent = route["intent"]
        table = {"rate_lookup": self.h_rates, "credit_cards": self.h_cards, "routing_number": self.h_routing,
                 "branch_closure": self.h_closure, "branch_count": self.h_count, "branch_hours": self.h_hours,
                 "branch_address": self.h_address, "link_lookup": self.h_link,
                 "membership_eligibility": self.h_eligibility, "contact_update": self.h_contact_update,
                 "unlisted_rate": self.h_unlisted}
        self._tl.force, self._tl.family = intent, route.get("family")
        try:
            if intent == "general_fact":                 # nothing specific: let the rule chain / retrieval decide
                return None
            return table[intent](q, ql, si, as_of)
        finally:
            self._tl.force = self._tl.family = None

    # ============================================================ helpers
    @staticmethod
    def _infer_as_of(ql):
        """'as of May 2026' / 'back in March 2026' in the question text -> last day of that month."""
        m = re.search(r"\b(?:as of|back in|during|at the end of|in the month of)\s+(?:early |late |mid-?)?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(?:\d{1,2}(?:st|nd|rd|th)?,?\s+)?(20\d\d)", ql)
        if not m:
            return None
        mon, yr = P.MONTHS[m.group(1)], int(m.group(2))
        last = [31, 29 if yr % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mon - 1]
        return "%04d-%02d-%02d" % (yr, mon, last)

    def _src(self, url, si, quote=None):
        return Source(url=url, snapshot_id=self.s.snaps[si][0], quote=(quote or None) and quote[:240])

    def _refuse(self, extra=""):
        return Answer(text=(extra + " " if extra else "") + REFUSAL, confident=False)

    # ============================================================ routing number
    def h_routing(self, q, ql, si, as_of):
        if not self._is("routing_number") and not re.search(r"routing|\baba\b|transit number", ql):
            return None
        rows = self.s.q(
            "routing_votes", (si, si))
        votes, srcs = Counter(), {}
        for r in rows:
            for m in re.finditer(r"\b(\d{9})\b", r["text"]):
                w = 3 if r["rank"] <= 2 else 1
                votes[m.group(1)] += w
                srcs.setdefault(m.group(1), []).append((r["url"], r["text"]))
        if not votes:
            return None
        val = votes.most_common(1)[0][0]
        srcs_l = []
        seen = set()
        for u, t in srcs[val]:
            if u not in seen:
                seen.add(u)
                srcs_l.append(self._src(u, si, t))
        return Answer(text="Dupaco's routing number (ABA) is %s." % val, sources=srcs_l[:3])

    # ============================================================ closures / temporal
    def h_closure(self, q, ql, si, as_of):
        if not self._is("branch_closure") and not re.search(r"\b(clos(e|es|ed|ing|ure)|still open|shut|relocat)", ql):
            return None
        if not self._is("branch_closure") and "branch" not in ql and "location" not in ql and not re.search(r"hy-?vee", ql):
            return None
        qt = [t for t in P.content_tokens(q) if t not in ("branch", "close", "clos", "closed", "closure", "still",
              "open", "today", "when", "will", "locatio", "locat", "october", "november", "december", "now",
              "currently", "2026", "2025", "stop", "does", "date")]
        qt = [t for t in qt if not t.isdigit()]
        if not qt:
            return None
        rows = self.s.q("closure_candidates", (si, si))
        best, best_sc = None, 0
        for r in rows:
            toks = set(P.tokens(r["text"] + " " + r["url"]))
            sc = sum(1 for t in qt if t in toks)
            if not re.search(r"\b(will|to|has|was|is|be)\s+(be\s+)?clos|last day of service", r["text"]) \
                    or not P.LONG_DATE.search(r["text"]):
                continue
            if sc > best_sc or (sc == best_sc and best and r["pub"] > best["pub"]):
                best, best_sc = r, sc
        if not best or best_sc < max(1, min(2, len(qt))):
            return None
        m = P.LONG_DATE.search(best["text"])
        text = best["text"]
        if m:
            when = "%s %s, %s" % (m.group(0).split()[0], m.group(2), m.group(3))
            ref = (as_of or self.s.snaps[si][1])[:10]
            iso = P._iso(m.group(3), P.MONTHS[m.group(1).lower()[:3]], m.group(2))
            gone = bool(iso and iso <= ref)
            verb = "closed" if gone else "is scheduled to close"
            if re.search(r"still|open today|currently open|open now", ql):
                text = "%sThe branch %s on %s. %s" % ("No. " if gone else "Yes, for now. ", verb, when, text)
            else:
                text = "The branch %s on %s. %s" % (verb, when, text)
        return Answer(text=text, sources=[self._src(best["url"], si, best["text"])])

    # ============================================================ branch count
    def h_count(self, q, ql, si, as_of):
        if not self._is("branch_count") and not re.search(r"how many (dupaco )?(branches|branch|locations|offices|banking centers)|number of (branches|locations|offices)",
                         ql):
            return None
        rows = self.s.q("branch_count_latest", (si,))
        if not rows:
            return None
        top = rows[0]
        same = [r for r in rows if r["value"] == top["value"]][:3]
        return Answer(text="Dupaco has %d branch office locations." % top["value"],
                      sources=[self._src(r["url"], si) for r in same],
                      conflict_note="Older pages cite other counts (%s); the most recently dated page was used."
                                    % ", ".join(sorted({str(r["value"]) for r in rows if r["value"] != top["value"]})))

    # ============================================================ branch hours
    def _branch_tokens(self, q):
        """Distinctive branch-name tokens in the question ('Mullan Avenue branch' -> {'mullan'})."""
        generic = {"lobby", "main", "nearest", "your", "the", "a", "each", "any", "all", "what", "are", "is", "do",
                   "dupaco", "general", "drive", "up", "hours", "branch", "open", "when", "does", "which", "same",
                   "typical", "regular", "banking", "full", "service", "address", "location", "office", "atm"}
        street = {"avenue", "ave", "street", "st", "road", "rd", "drive", "dr", "lane", "ln", "boulevard", "blvd",
                  "highway", "hwy", "court", "ct", "way"}
        out = []
        for m in re.finditer(r"((?:[A-Z][\w.'-]*\s+){1,3})(?:[Bb]ranch|[Oo]ffice|[Ll]ocation)", q):
            for w in m.group(1).split():
                wl = w.lower().strip(".'")
                if wl not in generic and wl not in street and w[0].isupper():
                    out.append(P.stem(wl))
        for m in re.finditer(r"(?:branch|office|location)\s+(?:in|at|on)\s+([A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*)?)", q):
            for w in m.group(1).split():
                wl = w.lower().strip(".'")
                if wl not in generic and wl not in street:
                    out.append(P.stem(wl))
        return out

    def _known_places(self, si):
        known = set()
        for r in self.s.q("locator_place_tokens", (si,)):
            known |= set(P.tokens(r["street"] + " " + r["city"]))
        for r in self.s.q("hours_place_titles", (si,)):
            known |= set(P.tokens(r["title"] or ""))
        return known

    @staticmethod
    def _norm_hours(line):
        line = line.replace("\u2013", "-").replace("\u2014", "-").replace("a.m.", "a.m.")
        line = re.sub(r"(\d)\s*a\.m\.-", r"\1 a.m.-", line)
        return re.sub(r"\s+", " ", line).strip()

    def h_hours(self, q, ql, si, as_of):
        if not self._is("branch_hours") and not re.search(r"\b(hours|open|opens|lobby|drive[- ]?up|close at|closing time)\b", ql):
            return None
        if re.search(r"\b(routing|rate|apy|apr)\b", ql):
            return None
        want_drive = bool(re.search(r"drive[- ]?(up|thru|through)", ql))
        names = self._branch_tokens(q)
        rows = self.s.q("hours_for_snapshot", (si,))
        if not rows:
            rows = self.s.q("hours_all_snapshots")
        if not rows:
            return None
        if names:
            place_rows = [r for r in rows if any(n in set(P.tokens(r["blurb"][:3500])) for n in names)]
            known = self._known_places(si)
            if not place_rows:
                if not any(n in known for n in names):
                    return self._refuse("I couldn't find hours for that branch.")
                return self._refuse("I couldn't find hours for that branch.")
            rows = place_rows
        kind = "drive-up" if want_drive else "lobby"
        sched = defaultdict(list)
        for r in rows:
            if r["kind"] == kind:
                sched[tuple(self._norm_hours(l) for l in json.loads(r["lines"]))].append(r)
        if not sched:
            return None
        order = sorted(sched.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        label = "Drive-up" if want_drive else "Lobby"
        parts = []
        for lines, rs in order[:5]:
            parts.append("; ".join(l.replace("Monday", "Mon").replace("Tuesday", "Tue").replace("Thursday", "Thu")
                                   .replace("Friday", "Fri").replace("Saturday", "Sat").replace("Sunday", "Sun")
                                   .replace("Wednesday", "Wed") for l in lines))
        if names and len(order) == 1:
            text = "%s hours: %s." % (label, parts[0])
        else:
            text = ("%s hours vary by branch. Typical schedules on file: " % label) + " | ".join(
                "(%d) %s" % (i + 1, p) for i, p in enumerate(parts)) + ". Which branch would you like hours for, or all branches?"
        srcs = []
        for lines, rs in order[:3]:
            srcs.append(self._src(rs[0]["url"], si, "; ".join(lines)))
        srcs.append(self._src("https://www.dupaco.com/contact", si))
        srcs.append(self._src("https://www.dupaco.com/", si))
        return Answer(text=text, sources=srcs)

    # ============================================================ address
    def h_address(self, q, ql, si, as_of):
        if not self._is("branch_address") and (not re.search(r"\b(address|located|where is|where's|find the)\b", ql) or not re.search(r"branch|office|location", ql)):
            return None
        names = self._branch_tokens(q)
        rows = self.s.q("locator_branches", (si,))
        qt = set(P.tokens(q))
        best, best_sc = None, 0
        for r in rows:
            sc = len(qt & set(P.tokens(r["street"] + " " + r["city"])))
            if sc > best_sc:
                best, best_sc = r, sc
        if best is None:
            if names:
                return self._refuse("I couldn't find an address for that branch.")
            return None
        text = "The Dupaco %s branch is at %s, %s, %s %s." % (best["city"], best["street"], best["city"], best["state"], best["zip"])
        text = text.replace(" Ln.,", " Lane,")
        if best["services"]:
            text += " Services: %s." % best["services"]
        return Answer(text=text, sources=[self._src(best["url"], si)])

    # ============================================================ links
    LINK_TOPICS = [
        (r"certificate|\bcds?\b", r"rate|certificate|compare|cd", r"savings-account.*rates|certificate", "Dupaco's certificate (CD) rates are listed at"),
        (r"locator|branch|atm|locations?", r"locat|branch|atm|find|contact", r"dupaco\.com/contact/?$", "Dupaco's branch and ATM locator is at"),
        (r"join|become a member|open an account|membership|sign up", r"join|become|member|open|apply", r"join\.dupaco\.com", "You can join Dupaco online at"),
    ]

    def h_link(self, q, ql, si, as_of):
        if not self._is("link_lookup") and not re.search(r"\b(link|url|website|web address|web page|webpage|site|where (can|do) i (see|find|go|join|sign))\b", ql) \
                and not re.search(r"how (do|can) i join", ql):
            return None
        if re.search(r"\b(rate|apy|apr)\b", ql) and not re.search(r"certificate|\bcds?\b", ql):
            return None
        for topic_re, text_re, href_re, lead in self.LINK_TOPICS:
            if not re.search(topic_re, ql):
                continue
            rows = self.s.q("links_with_authority", (si,))
            votes = Counter()
            for r in rows:
                if "info.dupaco.com" in r["href"] or "dupaco.com" not in r["href"]:
                    continue
                if not re.search(text_re, r["text"], re.I) or not re.search(href_re, r["href"], re.I):
                    continue
                if P.authority(r["href"].split("#")[0]) >= 4:
                    continue
                votes[r["href"].rstrip("/") if "#" not in r["href"] else r["href"]] += 4 if r["rank"] <= 2 else 1
            if votes:
                href = votes.most_common(1)[0][0]
                if href.endswith("join.dupaco.com"):
                    href += "/"
                holder = next((r["url"] for r in rows if r["href"].rstrip("/") == href.rstrip("/")), None)
                page = href.split("#")[0]
                return Answer(text="%s %s" % (lead, href),
                              sources=[self._src(page, si), self._src(holder, si)] if holder else [self._src(page, si)])
        return None

    # ============================================================ credit cards
    def h_cards(self, q, ql, si, as_of):
        if not self._is("credit_cards") and not (re.search(r"credit card|\bvisa\b|platinum|rewards (visa|card)", ql) and RATE_WORDS.search(ql)):
            return None
        rows = self.s.q("cards_for_snapshot", (si,))
        if not rows:
            return None
        seen, cards = set(), []
        for r in rows:
            if r["name"] in seen:
                continue
            seen.add(r["name"])
            cards.append(r)
        want_business = "business" in ql
        named = [c for c in cards if all(t in ql for t in P.tokens(c["name"]) if t not in ("visa",))]
        pick = cards
        if want_business:
            pick = [c for c in cards if "Business" in c["name"]]
        elif re.search(r"platinum|rewards", ql):
            sub = [c for c in cards if ("platinum" in ql and "Platinum" in c["name"]) or ("rewards" in ql and "Rewards" in c["name"])]
            if sub and not re.search(r"credit cards|all (your )?cards|cards do you", ql):
                pick = [c for c in sub if "Business" not in c["name"]] or sub
        lines, srcs = [], []
        for c in pick:
            kind = "variable " if "Business" in c["name"] else ""
            if c["lo"] is not None and c["hi"] is not None and c["lo"] != c["hi"]:
                apr = "%s–%s APR" % (_fmt_pct(c["lo"]), _fmt_pct(c["hi"]))
            else:
                apr = "%s%s APR" % (kind, _fmt_pct(c["lo"]))
            line = "%s: %s" % (c["name"], apr)
            if c["intro"] and "Platinum" in c["name"] and "Business" not in c["name"]:
                line += " (the %s intro APR applies only to balance transfers for new cardholders)" % _fmt_pct(c["intro"])
            lines.append(line)
            srcs.append(self._src(c["url"], si, line))
        if not lines:
            return None
        if len(lines) == 1:
            text = "The %s currently has a %s." % (pick[0]["name"], lines[0].split(": ", 1)[1])
        else:
            text = "Dupaco offers %d credit cards: " % len(lines) + "; ".join(lines) + "."
        # unique sources by url
        uniq, seen_u = [], set()
        for s_ in srcs:
            if s_.url not in seen_u:
                seen_u.add(s_.url)
                uniq.append(s_)
        return Answer(text=text, sources=uniq)

    # ============================================================ rate tables
    def _detect_families(self, ql):
        fams = []
        for fam in ("home_improvement", "personal_loan", "cert", "auto", "mortgage", "checking", "card", "savings"):
            if re.search(FAMILY_WORDS[fam], ql):
                fams.append(fam)
        if "cert" in fams and "savings" in fams and not re.search(r"\bsavings (account|tier)", ql):
            fams.remove("savings")
        if "mortgage" in fams and "auto" in fams:
            fams.remove("auto")
        hint = getattr(self._tl, "family", None)       # family chosen by the Groq router
        if hint and hint != "none" and self._is("rate_lookup") and hint not in fams:
            fams = [hint] if not fams else fams
        return fams

    def _dominant_rows(self, si, fams, segment):
        marks = ",".join("?" * len(fams))
        return self.s.q("rates_dominant", [si] + fams + [segment], fmt={"marks": marks})

    def h_rates(self, q, ql, si, as_of):
        fams = self._detect_families(ql)
        if not fams:
            return None
        if not self._is("rate_lookup") and not RATE_WORDS.search(ql) and not re.search(r"\d+(\.\d+)?\s*%", ql):
            return None
        if "card" in fams and len(fams) == 1:
            return None
        fams = [f for f in fams if f != "card"] or fams
        segment = "business" if "business" in ql else "personal"
        rows = self._dominant_rows(si, fams, segment)
        if not rows and segment == "business":
            rows = self._dominant_rows(si, fams, "personal")
        if not rows:
            if any(u in set(P.tokens(q)) for u in UNLISTED) or fams:
                return self._refuse("I couldn't find a published rate for that.")
            return None
        # ---- unlisted program words (7/1 ARM, construction ...)
        qtok = set(P.tokens(q))
        hay_all = set()
        for r in rows:
            hay_all |= set(P.tokens(r["label"] + " " + r["head"] + " " + r["ctx"]))
        for u in UNLISTED:
            if P.stem(u) in qtok and P.stem(u) not in hay_all and not (u == "auto"):
                if u in ("student", "motorcycle") and "auto" in fams:
                    continue
                return self._refuse("I couldn't find a published rate for that program.")
        # ---- filters: term numbers, model year, refinance/purchase
        terms = [(int(n), u[:2]) for n, u in re.findall(r"\b(\d{1,3})\s*[- ]?\s*(month|mo\b|year|yr)", ql)]
        years = [int(y) for y in re.findall(r"\b(20[12]\d)\b", ql)]
        if "auto" in fams and years:
            def in_range(label):
                m = re.match(r"(\d{4})\s*-\s*(\d{2,4})", label)
                if m:
                    lo, hi = int(m.group(1)), m.group(2)
                    hi = int(hi) if len(hi) == 4 else int(m.group(1)[:2] + hi)
                    return lo <= years[0] <= hi
                m = re.match(r"(\d{4})", label)
                if m and "older" in label.lower():
                    return years[0] <= int(m.group(1))
                return False
            f = [r for r in rows if in_range(r["label"])]
            if f:
                rows = f
            else:
                return self._refuse("I couldn't find a published rate for that model year.")
        if terms:
            def has_term(r):
                lt = P.tokens(r["label"])
                return all(str(n) in lt and any(u == t[:2] for t in lt) or str(n) in lt for n, u in terms)
            f = [r for r in rows if has_term(r)]
            if not f:
                return self._refuse("I couldn't find a published rate for that term.")
            rows = f
        if "mortgage" in fams:
            if re.search(r"refinanc|refi", ql):
                rows = [r for r in rows if r["label"].lower().startswith("refinance")] or rows
            else:
                rows = [r for r in rows if r["label"].lower().startswith("purchase")] or rows
        # ---- entity tokens (product names): keep best-matching rows
        drop = set(P.tokens(" ".join([
            "rate rates interest apr apy dividend current right now today percent annual what whats the is are for on of "
            "month months year years loan loans account accounts mortgage auto vehicle certificate certificates",
            "model purchase earn pay offer offers tier tiers balance between and highest lowest best how much do you "
            "have your can tell me provide get want know current checking savings"])))
        etok = [t for t in P.content_tokens(q) if t not in drop and not re.match(r"^[\d.$%]+$", t)]
        scored = []
        for r in rows:
            hay = set(P.tokens(r["label"] + " " + r["head"] + " " + r["ctx"]))
            scored.append((sum(1 for t in etok if t in hay), r))
        if etok:
            mx = max(s for s, _ in scored)
            if mx > 0:
                rows = [r for s, r in scored if s == mx]
        elif "savings" in fams and not re.search(r"\b(all|every|each)\b", ql) and (
                re.search(r"\b(tier|tiers|highest|lowest|best|top|any)\b", ql) or "savings" in ql and re.search(r"\$", q)):
            share = [r for r in rows if r["label"].lower().startswith("share savings")]
            rows = share or rows
        # ---- tiers by amount
        amts = [float(a.replace(",", "")) for a in re.findall(r"\$\s?(\d[\d,]*(?:\.\d+)?)", q)]
        if amts:
            rows = self._pick_tier(rows, amts)
        # ---- superlatives / yes-no
        key = "apy" if any(r["apy"] is not None for r in rows) else ("apr" if any(r["apr"] is not None for r in rows) else "rate")
        yn = re.search(r"\b(do|does|is|are|will) (any|you|dupaco)\b.*?(\d+(?:\.\d+)?)\s*%", ql)
        if yn and not re.search(r"\bwhat\b", ql):
            target = float(yn.group(3))
            hits = [r for r in rows if target in (r["apy"], r["rate"], r["apr"])]
            fam_label = rows[0]["label"].split(" | ")[0] if rows else "that product"
            if hits:
                return self._render(hits, si, key, lead="Yes. ")
            top = max(rows, key=lambda r: (r[key] if r[key] is not None else -1))
            tl = top["label"].replace(" | ", ", ")
            best = _fmt_pct(top[key])
            return Answer(text="No. The %s tiers top out at %s %s (%s); %s isn't on the current rate sheet."
                               % (fam_label, best, key.upper(), tl.split(", ", 1)[-1], _fmt_pct(target)),
                          sources=[self._src(top["url"], si, top["raw"])])
        if re.search(r"\b(highest|best|top|maximum|max)\b", ql):
            top = max(rows, key=lambda r: (r[key] if r[key] is not None else -1))
            return self._render([top], si, key, lead="The highest is ")
        if re.search(r"\b(lowest|minimum rate|cheapest)\b", ql):
            top = min(rows, key=lambda r: (r[key] if r[key] is not None else 999))
            return self._render([top], si, key, lead="The lowest is ")
        return self._render(rows, si, key)

    def _pick_tier(self, rows, amts):
        groups = defaultdict(list)
        for r in rows:
            base = re.sub(r"\|?\s*\$[\d,.\s]+(?:\s*[–-]\s*\$[\d,.]+|\+|\s*or less)?", "", r["label"]).strip(" |") or r["label"]
            base = re.sub(r"\s+", " ", base)
            groups[base].append(r)
        out = []
        lo_a, hi_a = min(amts), max(amts)
        for base, rs in groups.items():
            tiered = [(P.tier_bounds(r["label"]), r) for r in rs]
            if not any(b for b, _ in tiered):
                out += rs
                continue
            cont = [(b, r) for b, r in tiered if b and b[0] <= lo_a and (b[1] >= hi_a)]
            if not cont:
                cont = [(b, r) for b, r in tiered if b and b[0] <= lo_a <= b[1]]
            if not cont:
                continue
            cont.sort(key=lambda br: (br[0][1] - br[0][0]))
            out.append(cont[0][1])
        return out or rows

    def _line(self, r):
        lab = r["label"].replace(" | ", ", ")
        fam = r["family"]
        if r["apy"] is not None and (fam in ("savings", "cert", "checking") or r["rate"] is not None):
            core = "%s APY" % _fmt_pct(r["apy"])
            if r["rate"] is not None and r["rate"] != r["apy"]:
                core += " (%s dividend rate)" % _fmt_pct(r["rate"])
            return "%s: %s" % (lab, core)
        if r["rate"] is not None and r["apr"] is not None:
            return "%s: %s rate / %s APR" % (lab, _fmt_pct(r["rate"]), _fmt_pct(r["apr"]))
        if r["apr"] is not None:
            return "%s: %s APR" % (lab, _fmt_pct(r["apr"]))
        return "%s: %s" % (lab, _fmt_pct(r["rate"]))

    def _render(self, rows, si, key, lead=""):
        if not rows:
            return self._refuse()
        def order(r):
            if r["family"] == "mortgage":
                t = re.search(r"(\d+)-year", r["label"].lower())
                tb = P.tier_bounds(r["label"])
                return (r["label"].lower().startswith("refinance"), -(int(t.group(1)) if t else 0), tb[1] if tb else 0, r["label"])
            return ("jumbo" in r["label"].lower(), -(r["rank"] <= 1), r["label"])
        rows = sorted(rows, key=lambda r: order(r)) if len(rows) <= 40 else rows
        rows = rows[:14]
        effs = Counter(r["eff"] for r in rows if r["eff"])
        eff = effs.most_common(1)[0][0] if effs else ""
        lines = [self._line(r) for r in rows]
        if len(lines) == 1:
            text = (lead + lines[0] if lead else lines[0]) + "."
        else:
            text = (lead + "; ".join(lines)) + "."
        if eff:
            text += " (Rates effective %s.)" % _us_date(eff)
        srcs, seen = [], set()
        for r in rows:
            if r["url"] not in seen:
                seen.add(r["url"])
                srcs.append(self._src(r["url"], si, r["raw"]))
        # corroboration: other pages of the same snapshot carrying the identical row value
        for r in rows[:3]:
            for o in self.s.q(
                    "rates_corroboration",
                    (si, r["ckey"], r["rate"], r["apr"], r["apy"])):
                if o["url"] not in seen:
                    seen.add(o["url"])
                    srcs.append(self._src(o["url"], si))
        hint = {"mortgage": "home-loans", "auto": "auto", "personal_loan": "personal-loans", "cert": "savings-account",
                "savings": "savings-account", "checking": "checking", "home_improvement": "home-loans"}.get(rows[0]["family"], "")
        srcs.sort(key=lambda x: (hint not in x.url, "/personal/" not in x.url))
        page = srcs[0].url
        if "#rates" not in page and rows[0]["rank"] <= 1:
            srcs.insert(1, self._src(page.rstrip("/") + "#rates", si))
        return Answer(text=text, sources=srcs[:6])

    # ============================================================ passage retrieval fallback
    def _load_idf(self):
        if self._idf is None:
            self.s.db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS sent_v USING fts5vocab(sent_fts, 'row')")
            self._idf = {t: d for t, d in self.s.db.execute("SELECT term, doc FROM sent_v")}
            self._n = self.s.db.execute("SELECT COUNT(*) FROM sent").fetchone()[0] or 1
        return self._idf

    def _idf_of(self, t):
        df = self._load_idf().get(t, 0)
        return math.log(1 + (self._n - df + 0.5) / (df + 0.5))

    def retrieve(self, q, si, k=60):
        qt = []
        for t in P.content_tokens(q):
            for w in re.findall(r"[a-z0-9]+", t):
                if w not in qt and w not in P.STOP:
                    qt.append(w)
        if not qt:
            return [], qt
        match = " OR ".join('"%s"' % w for w in qt)
        rows = self.s.q(
            "retrieve_fts",
            (match, si, si, k))
        return rows, qt

    def _score_chunks(self, rows, qt):
        total = sum(self._idf_of(t) for t in qt) or 1.0
        out = []
        for r in rows:
            toks = set(re.findall(r"[a-z0-9]+", " ".join(P.tokens(r["text"]))))
            cov = sum(self._idf_of(t) for t in qt if t in toks) / total
            slug = set(re.findall(r"[a-z0-9]+", " ".join(P.tokens(P.url_path(r["url"]) + " " + r["title"] + " " + r["head"]))))
            cov += 0.15 * sum(self._idf_of(t) for t in qt if t in slug) / total
            cov += {1: 0.10, 2: 0.06, 3: 0.03, 4: 0.0, 5: -0.04}.get(r["rank"], 0)
            out.append((cov, r))
        out.sort(key=lambda x: -x[0])
        return out

    def h_unlisted(self, q, ql, si, as_of):
        if self._is("unlisted_rate"):
            return self._refuse("I couldn't find a published rate for that program.")
        if not RATE_WORDS.search(ql):
            return None
        qtok = set(P.tokens(q))
        for u in UNLISTED:
            if P.stem(u) in qtok:
                return self._refuse("I couldn't find a published rate for that program.")
        return None

    def h_eligibility(self, q, ql, si, as_of):
        if not self._is("membership_eligibility") and not re.search(r"eligib|who can (join|become)|who (is|are) (able|allowed)|qualify (to|for) (join|member)|join dupaco|become a member|membership requirements", ql):
            return None
        if re.search(r"how do i join|how can i join|join online|link|url", ql):
            return None
        rows = self.s.q("membership_eligibility_chunks", (si, si))
        if not rows:
            return None
        rows.sort(key=lambda r: (0 if "charter area" in r["text"] else 1, r["id"]))
        text = ("Eligibility: " + " ".join(r["text"].rstrip(".") + "." for r in rows))[:900]
        return Answer(text=text, sources=[self._src(rows[0]["url"], si, rows[0]["text"])])

    def h_contact_update(self, q, ql, si, as_of):
        if not self._is("contact_update") and not re.search(r"(update|change|edit|correct|new)\b.*\b(contact|phone number|address|email|mailing)", ql):
            return None
        if re.search(r"branch|atm|routing|rate", ql):
            return None
        rows = self.s.q("phone_number_page", (si, si))
        url = rows[0]["url"] if rows else "https://www.dupaco.com/contact"
        return Answer(text="You can update your contact information by logging in to your account in Shine online or mobile "
                           "banking, or by calling Dupaco at 800-373-7600. No account details are needed just to ask how.",
                      sources=[self._src("https://www.dupaco.com/contact", si), self._src(url, si)])

    def h_retrieve(self, q, ql, si):
        rows, qt = self.retrieve(q, si)
        if not rows:
            return self._refuse()
        scored = self._score_chunks(rows, qt)
        best_sc = scored[0][0]
        if best_sc < 0.38:
            return self._refuse()
        # near-ties -> the newest page wins (newer supersedes older)
        ties = [(sc, r) for sc, r in scored if sc >= 0.9 * best_sc]
        ties.sort(key=lambda x: (x[1]["pub"] or "", x[0]), reverse=True)
        chosen = ties[0][1]
        parts = [chosen]
        # supporting chunks from the same page, in page order
        same = sorted([r for sc, r in scored if r["url"] == chosen["url"] and r["id"] != chosen["id"] and sc >= 0.6 * best_sc],
                      key=lambda r: r["id"])[:2]
        parts += same
        parts.sort(key=lambda r: r["id"])
        text = " ".join(r["text"] for r in parts)
        if len(text) < 140:
            nxt = self.s.q("next_chunk_on_page",
                           (chosen["url"], parts[-1]["id"], si, si))
            if nxt:
                text += " " + nxt[0]["text"]
        # "how many ..." with conflicting numbers on other dated pages: give both, newest first
        if re.search(r"\bhow (many|much)\b", ql):
            nums = set(re.findall(r"\d[\d,.]*", chosen["text"]))
            for sc, r in ties[1:]:
                if r["url"] != chosen["url"] and set(re.findall(r"\d[\d,.]*", r["text"])) != nums:
                    text += " (An earlier page says: %s)" % r["text"]
                    break
        return Answer(text=text[:900], sources=[self._src(r["url"], si, r["text"]) for r in parts][:3])

    # ============================================================ conflicts
    def conflicts(self):
        s = self.s
        if not s.snaps:
            return []
        si = len(s.snaps) - 1
        out = []
        # 1. rate rows whose value differs between pages of the latest snapshot
        rows = s.q("conflict_rate_rows", (si,))
        by = defaultdict(list)
        for r in rows:
            by[r["ckey"]].append(r)
        for key, rs in by.items():
            vals = {(r["rate"], r["apr"], r["apy"]) for r in rs}
            if len(vals) <= 1:
                continue
            best = sorted(rs, key=lambda r: (r["rank"] > 1, "" if not r["eff"] else r["eff"]), reverse=False)
            win = sorted(rs, key=lambda r: (r["rank"] > 1, -int((r["eff"] or "0").replace("-", "") or 0), r["rank"]))[0]
            def show(r):
                return ", ".join(x for x in (
                    _fmt_pct(r["apy"]) + " APY" if r["apy"] is not None else "",
                    _fmt_pct(r["rate"]) + " rate" if r["rate"] is not None and r["apy"] is None else "",
                    _fmt_pct(r["apr"]) + " APR" if r["apr"] is not None else "") if x)
            values = []
            for r in rs:
                v = show(r)
                if v not in values:
                    values.append(v)
            out.append(Conflict(
                topic="%s (%s)" % (win["label"].replace(" | ", ", "), win["family"].replace("_", " ")),
                values=values,
                sources=[self._src(r["url"], si, r["raw"]) for r in rs[:6]],
                resolution=show(win),
                reason="The canonical product page%s supersedes copies on promo/calculator/other pages."
                       % (" (rates effective %s)" % _us_date(win["eff"]) if win["eff"] else "")))
        # 2. branch-count boilerplate
        cnts = s.q("conflict_branch_counts", (si,))
        if len({c["value"] for c in cnts}) > 1:
            vals = []
            for c in cnts:
                if str(c["value"]) not in vals:
                    vals.append(str(c["value"]))
            out.append(Conflict(topic="number of Dupaco branch office locations", values=vals,
                                sources=[self._src(c["url"], si) for c in cnts[:1]]
                                + [self._src(c["url"], si) for c in cnts[-1:]],
                                resolution=str(cnts[0]["value"]),
                                reason="Press-release boilerplate is stale on older posts; the most recently dated page wins."))
        # 3. lobby-hours variants
        hrs = s.q("conflict_hours_variants", (si,))
        for kind in ("lobby", "drive-up"):
            variants = {}
            for h in hrs:
                if h["kind"] == kind:
                    variants.setdefault(h["lines"], h["url"])
            if len(variants) > 1:
                out.append(Conflict(topic="%s hours differ by branch" % kind,
                                    values=["; ".join(json.loads(k)) for k in variants],
                                    sources=[self._src(u, si) for u in variants.values()],
                                    resolution=None, reason="Hours are branch-specific; no single schedule applies to all branches."))
        return out
