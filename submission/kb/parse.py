"""Parsing helpers: markdown -> structured records. Pure functions, stdlib only (Python 3.9+)."""
import re
from urllib.parse import urlparse

MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}

STOP = set("""a an the of to in on for and or is are was were be been do does did can could would should will
i me my we our you your it its this that these those what which who whom how when where why with at by from as
about any all there their them they than then so if not no yes please tell give provide get want like know
dupaco credit union offer offers have has had much many""".split())


def stem(tok: str) -> str:
    t = tok.lower()
    t = re.sub(r"[^a-z0-9$.]", "", t)
    if len(t) > 4 and t.endswith("ies"):
        t = t[:-3] + "y"
    elif len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
        t = t[:-1]
    return t[:7]


def tokens(text: str):
    text = (text or "").lower().replace("–", " ").replace("—", " ")
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text)           # 1,000 -> 1000
    text = re.sub(r"[-/_]", " ", text)
    return [s for t in re.findall(r"[a-z0-9$][a-z0-9$.%]*", text) if (s := stem(t))]


# ------------------------------------------------------------------ authority
def url_path(url: str) -> str:
    return urlparse(url).path.rstrip("/").lower()


PRODUCT_PAGE = re.compile(r"^/(personal|business)/[a-z0-9-]+(/[a-z0-9-]+)?$")


def authority(url: str) -> int:
    """1 = canonical product / contact page ... 5 = blog / pdf / calculators."""
    p = url_path(url)
    if p in ("/contact", ""):
        return 1
    if "/learn/" in p or "/blog" in p or p.endswith(".pdf") or "/hubfs/" in p:
        return 5
    if "/calculators" in p or "/newsroom" in p:
        return 4
    if PRODUCT_PAGE.match(p):
        return 1
    return 3                                                  # landing pages, promos, misc


# ------------------------------------------------------------------ dates
def _iso(y, m, d):
    try:
        return "%04d-%02d-%02d" % (int(y), int(m), int(d))
    except Exception:
        return ""


EFF = re.compile(r"(?:effective|as of|rates? (?:are|as of))\D{0,25}(\d{1,2})/(\d{1,2})/(\d{4})", re.I)
LONG_DATE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),\s+(20\d\d)")


def page_pub_date(md: str) -> str:
    m = LONG_DATE.search(md[:2500])
    if m:
        return _iso(m.group(3), MONTHS[m.group(1).lower()[:3]], m.group(2))
    return ""


# ------------------------------------------------------------------ cleaning
def clean_cell(c: str) -> str:
    c = c.strip().replace("\\*", "").replace("\\|", "|").replace("**", "")
    c = re.sub(r"<br\s*/?>", " ", c)
    c = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", c)
    c = re.sub(r"(?<=[%A-Za-z\)])\s?\d$", "", c)              # footnote digit: 4.20%1 / APR1
    return re.sub(r"\s+", " ", c).strip()


def split_row(line: str):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [clean_cell(x) for x in re.split(r"(?<!\\)\|", line)]


def first_pct(cell: str):
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", cell or "")
    return float(m.group(1)) if m else None


def money(cell: str):
    m = re.search(r"\$\s*(\d[\d,]*(?:\.\d+)?)", cell or "")
    return float(m.group(1).replace(",", "")) if m else None


def tier_bounds(text: str):
    """'$10,000 – $24,999.99' -> (10000, 24999.99); '$25,000+' -> (25000, inf);
    '... $300,000 or less' -> (0, 300000)."""
    t = (text or "").replace("–", "-").replace("—", "-")
    nums = [float(x.replace(",", "")) for x in re.findall(r"\$\s*(\d[\d,]*(?:\.\d+)?)", t)]
    if not nums:
        return None
    if "or less" in t.lower() or "up to" in t.lower():
        return (0.0, nums[0])
    if "+" in t or "or more" in t.lower():
        return (nums[0], float("inf"))
    if len(nums) >= 2:
        return (nums[0], nums[1])
    return (nums[0], nums[0])


# ------------------------------------------------------------------ tables
VALUE_HDR = re.compile(r"rate|apr|apy|yield|dividend|points|payment|min\b|min\.|minimum", re.I)


def iter_tables(md: str):
    lines = md.split("\n")
    i, n = 0, len(lines)
    head, ctx = "", ""
    while i < n:
        ln = lines[i]
        s = ln.strip()
        if s.startswith("|") and i + 1 < n and re.match(r"^\s*\|\s*:?-{2,}", lines[i + 1]):
            header = split_row(s)
            j = i + 2
            rows = []
            while j < n and lines[j].strip().startswith("|"):
                rows.append(split_row(lines[j]))
                j += 1
            eff = ""
            for k in range(j, min(j + 8, n)):
                if lines[k].strip().startswith("|"):
                    break
                m = EFF.search(lines[k])
                if m:
                    eff = _iso(m.group(3), m.group(1), m.group(2))
                    break
            if any(h for h in header):
                yield {"header": header, "rows": rows, "head": head, "ctx": ctx, "eff": eff}
            i = j
            continue
        if s.startswith("#"):
            head = clean_cell(re.sub(r"^#+", "", s))
            ctx = ""
        elif s and not s.startswith("|") and not s.startswith("!["):
            ctx = clean_cell(s)[:140]
        i += 1


def family_of(url: str, header, label: str) -> str:
    h = " ".join(header).lower()
    lab = label.lower()
    path = url_path(url)
    if "model year" in lab:
        return "auto"
    if re.search(r"year fixed|^(purchase|refinance):|\barm\b|adjustable", lab):
        return "mortgage"
    if "card type" in h or "visa" in lab:
        return "card"
    if "certificate" in lab or "certificate" in h or re.match(r"^\d+ months?$", lab) and "savings" in path:
        return "cert"
    if "checking" in lab:
        return "checking"
    if "loan amount" in h and "home" in path:
        return "home_improvement"
    if re.search(r"savings|money market|health savings|\bhsa\b|share|ira", lab):
        return "savings"
    if h.startswith("term") and "personal-loans" in path:
        return "personal_loan"
    if "loan" in path and "apr" in h:
        return "loan_other"
    return "other"


def parse_rate_tables(url: str, md: str):
    """-> list of dict rows (one per table row that carries a rate)."""
    out = []
    for t in iter_tables(md):
        header = t["header"]
        vi = next((i for i, h in enumerate(header) if VALUE_HDR.search(h)), None)
        if vi is None or vi == 0:
            continue
        for cells in t["rows"]:
            if len(cells) < vi + 1:
                continue
            labcells = [c for c in cells[:vi] if c and c != "—"]
            if not labcells:
                continue
            label = " | ".join(labcells)
            vals = {header[k]: cells[k] for k in range(vi, min(len(header), len(cells)))}
            rate = apr = apy = None
            for k, v in vals.items():
                kl = k.lower()
                p = first_pct(v)
                if p is None:
                    continue
                if "apy" in kl or "annual percentage yield" in kl:
                    apy = p
                elif "apr" in kl or "annual percentage rate" in kl:
                    apr = p
                elif "dividend" in kl or "rate" in kl:
                    rate = p
            if rate is None and apr is None and apy is None:
                continue
            fam = family_of(url, header, label)
            minearn = None
            for k, v in vals.items():
                if "earn" in k.lower() or "min" in k.lower():
                    minearn = money(v)
            out.append({
                "family": fam, "label": label, "head": t["head"], "ctx": t["ctx"], "eff": t["eff"],
                "rate": rate, "apr": apr, "apy": apy, "minearn": minearn,
                "raw": "| " + " | ".join(cells) + " |",
                "segment": "business" if "/business" in url_path(url) or "business" in label.lower() else "personal",
            })
    return out


def ckey(label: str) -> str:
    s = label.lower().replace("–", "-").replace("—", "-")
    s = re.sub(r"[$,\s]", "", s)
    return re.sub(r"[^a-z0-9.+|:()-]", "", s)


# ------------------------------------------------------------------ branches / hours
HOURS_LINE = re.compile(r"^\s*(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*"
                        r"(?:\s*[-–]\s*(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*)?"
                        r"\s*:\s*(.+?)\s*$", re.I)


def parse_hours_blocks(md: str):
    """Newsroom branch releases: '**Lobby** Monday-Thursday: ... **Drive-up** ...'.
    -> list of {'kind': 'lobby'|'drive-up', 'lines': [...]}"""
    out = []
    lines = md.split("\n")
    cur = None
    for ln in lines:
        s = ln.strip()
        m = re.match(r"^\*\*(Lobby|Drive[- ]?up)\*\*\s*(.*)$", s, re.I)
        if m:
            cur = {"kind": "lobby" if m.group(1).lower().startswith("lobby") else "drive-up", "lines": []}
            out.append(cur)
            rest = m.group(2).strip()
            if rest:
                s = rest
            else:
                continue
        if cur is None:
            continue
        s = s.replace("*", "")
        if HOURS_LINE.match(s):
            cur["lines"].append(re.sub(r"\s+", " ", s))
        elif s and not s.startswith("Branch hours") and cur["lines"]:
            cur = None
    return [b for b in out if b["lines"]]


ADDR = re.compile(r"^(\d+\s+[^,\n]+?),\s*([A-Za-z .'-]+?),\s*([A-Z]{2}),?\s*(\d{5})$")


def parse_locator(md: str):
    """/contact locator entries: heading, kind, 'street, City, ST, ZIP', status, services."""
    out = []
    lines = [ln.strip() for ln in md.split("\n")]
    for i, line in enumerate(lines):
        m = ADDR.match(line)
        if not m:
            continue
        name, kind = "", ""
        for k in range(i - 1, max(-1, i - 6), -1):
            if lines[k].startswith("### "):
                name = lines[k][4:].strip()
                break
            if lines[k] and not kind:
                kind = lines[k]
        services = ""
        for k in range(i + 1, min(len(lines), i + 6)):
            if "ATM" in lines[k] or "Drive" in lines[k] or "Teller" in lines[k]:
                services = lines[k]
                break
            if lines[k].startswith("###"):
                break
        out.append({"name": name, "kind": kind, "street": m.group(1), "city": m.group(2), "state": m.group(3),
                    "zip": m.group(4), "services": services})
    return out


# ------------------------------------------------------------------ chunks / links / counts
def chunk_page(md: str, max_len=450):
    """Split into retrieval units: paragraphs / bullets / table rows, long ones split on sentences."""
    chunks = []
    head = ""
    for block in re.split(r"\n\s*\n", md):
        b = block.strip()
        if not b or b.startswith("![") and b.endswith(")") and "\n" not in b:
            continue
        if b.startswith("#"):
            head = clean_cell(re.sub(r"^#+", "", b.split("\n")[0]))
        items = b.split("\n") if re.match(r"^(\s*[-*]\s|\|)", b) else [b]
        for it in items:
            t = it.strip()
            if t.startswith("|") and re.match(r"^\|\s*:?-{2,}", t):
                continue
            t = re.sub(r"\[([^\]]*)\]\(([^)]*)\)", r"\1", t)
            t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
            t = re.sub(r"^\s*[-*]\s+", "", t).replace("**", "").replace("\\*", "*")
            t = re.sub(r"\s+", " ", t).strip()
            if len(t) < 25:
                continue
            if len(t) <= max_len:
                chunks.append((head, t))
            else:
                sents = re.split(r"(?<=[.!?])\s+(?=[A-Z“\"])", t)
                cur = ""
                for s in sents:
                    if cur and len(cur) + len(s) > max_len:
                        chunks.append((head, cur))
                        cur = s
                    else:
                        cur = (cur + " " + s).strip()
                if cur:
                    chunks.append((head, cur))
    return chunks


LINK = re.compile(r"\[([^\]]{2,80})\]\((https?://[^)\s]+)\)")


def parse_links(md: str):
    return [(m.group(1).strip(), m.group(2).strip()) for m in LINK.finditer(md)]


COUNT = re.compile(r"(?:more than |nearly |over )?(\d{2})\s+branch office locations", re.I)


def parse_branch_count(md: str):
    m = COUNT.search(md)
    return int(m.group(1)) if m else None


def parse_card_rows(md: str):
    """Personal card pages: '### Rewards Visa' sections with 'NN.NN%–NN.NN% APR' bullets."""
    out = []
    parts = re.split(r"\n(?=###\s)", md)
    for p in parts:
        m = re.match(r"###\s+(.*?Visa.*?)\s*\n", p)
        if not m:
            continue
        name = clean_cell(m.group(1))
        body = p
        rng = re.search(r"(\d+\.\d+)%\s*[–-]\s*(\d+\.\d+)%\s*APR", body)
        intro = re.search(r"(\d+\.\d+)%\s*intro APR[^.\n]*", body)
        single = re.search(r"[Vv]ariable Annual Percentage Rate \(APR\) of (\d+\.\d+)%", body)
        rec = {"name": name, "lo": None, "hi": None, "intro": None, "intro_text": ""}
        if rng:
            rec["lo"], rec["hi"] = float(rng.group(1)), float(rng.group(2))
        elif single:
            rec["lo"] = rec["hi"] = float(single.group(1))
        if intro:
            rec["intro"] = float(intro.group(1))
            rec["intro_text"] = clean_cell(intro.group(0))
        if rec["lo"] is not None:
            out.append(rec)
    return out


def model_years(label: str):
    """'2024-27 Model Year' -> (2024, 2027); '2016 Model Year (and older)' -> (0, 2016); else None."""
    m = re.match(r"\s*(\d{4})\s*-\s*(\d{2,4})", label)
    if m:
        hi = m.group(2)
        return int(m.group(1)), int(hi if len(hi) == 4 else m.group(1)[:2] + hi)
    m = re.match(r"\s*(\d{4}).*older", label, re.I)
    return (0, int(m.group(1))) if m else None
