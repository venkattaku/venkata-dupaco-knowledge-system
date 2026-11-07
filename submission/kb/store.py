"""SQLite store: every snapshot is ingested into relational tables (see the Data model section of NOTES.md)."""
import json
import sqlite3
import threading

from . import parse
from .vec import Vectors

SCHEMA = """
CREATE TABLE snaps  (idx INTEGER PRIMARY KEY, snap_id TEXT, taken_on TEXT);
CREATE TABLE pages  (snap_idx INT, url TEXT, title TEXT, rank INT, pub TEXT);
CREATE TABLE rates  (id INTEGER PRIMARY KEY, snap_idx INT, url TEXT, rank INT, family TEXT, segment TEXT,
                     label TEXT, ckey TEXT, head TEXT, ctx TEXT, eff TEXT, rate REAL, apr REAL, apy REAL,
                     minearn REAL, raw TEXT, hay TEXT, lo REAL, hi REAL, yr_lo INT, yr_hi INT);
CREATE INDEX rates_i ON rates(snap_idx, family);
CREATE TABLE cards  (snap_idx INT, url TEXT, rank INT, name TEXT, lo REAL, hi REAL, intro REAL, intro_text TEXT);
CREATE TABLE hours  (snap_idx INT, url TEXT, title TEXT, pub TEXT, kind TEXT, lines TEXT, blurb TEXT);
CREATE TABLE locator(snap_idx INT, url TEXT, name TEXT, kind TEXT, street TEXT, city TEXT, state TEXT,
                     zip TEXT, services TEXT);
CREATE TABLE counts (snap_idx INT, url TEXT, pub TEXT, value INT);
CREATE TABLE links  (snap_idx INT, url TEXT, text TEXT, href TEXT);
CREATE INDEX links_i ON links(snap_idx);
CREATE TABLE sent   (id INTEGER PRIMARY KEY, url TEXT, rank INT, pub TEXT, head TEXT, title TEXT, text TEXT,
                     first_idx INT, last_idx INT);
CREATE VIRTUAL TABLE sent_fts USING fts5(stext, tokenize='unicode61');
"""


class Store:
    def __init__(self):
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.lock = threading.RLock()
        self.db.executescript(SCHEMA)
        self.snaps = []                  # [(snap_id, taken_on)]
        self._sent = {}                  # text -> [id, rank, pub]
        self.vec = Vectors.from_env()    # optional dense vectors (None -> FTS5 only)

    # ------------------------------------------------------------ ingest
    def ingest(self, snapshot):
        """Parse every page of one snapshot into the tables: rates, cards, hours, branch locator, links and
        de-duplicated text passages (`sent`). A passage seen in several snapshots is stored once, with the range of
        snapshots (first_idx..last_idx) in which it exists."""
        idx = len(self.snaps)
        self.snaps.append((snapshot.snapshot_id, snapshot.taken_on))
        db = self.db
        db.execute("INSERT INTO snaps VALUES (?,?,?)", (idx, snapshot.snapshot_id, snapshot.taken_on))
        seen_text = set()             # passages present in this snapshot
        new_sent = []
        for pg in snapshot.pages:
            md = pg.markdown or ""
            url = pg.url
            rank = parse.authority(url)
            pub = parse.page_pub_date(md)
            db.execute("INSERT INTO pages VALUES (?,?,?,?,?)", (idx, url, pg.title, rank, pub))
            path = parse.url_path(url)

            for r in parse.parse_rate_tables(url, md):
                tb = parse.tier_bounds(r["label"])
                yr = parse.model_years(r["label"])
                hay = " " + " ".join(parse.tokens(" ".join([r["label"], r["head"], r["ctx"], path.replace("/", " ")]))) + " "
                db.execute(
                    "INSERT INTO rates(snap_idx,url,rank,family,segment,label,ckey,head,ctx,eff,rate,apr,apy,minearn,raw,"
                    "hay,lo,hi,yr_lo,yr_hi) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (idx, url, rank, r["family"], r["segment"], r["label"], parse.ckey(r["family"] + "|" + r["label"]),
                     r["head"], r["ctx"], r["eff"], r["rate"], r["apr"], r["apy"], r["minearn"], r["raw"], hay,
                     tb[0] if tb else None, min(tb[1], 1e15) if tb else None,
                     yr[0] if yr else None, yr[1] if yr else None))
            if "credit-cards" in path:
                for c in parse.parse_card_rows(md):
                    db.execute("INSERT INTO cards VALUES (?,?,?,?,?,?,?,?)",
                               (idx, url, rank, c["name"], c["lo"], c["hi"], c["intro"], c["intro_text"]))
            for b in parse.parse_hours_blocks(md):
                db.execute("INSERT INTO hours VALUES (?,?,?,?,?,?,?)",
                           (idx, url, pg.title, pub, b["kind"], json.dumps(b["lines"]), md[:4000]))
            if path == "/contact":
                for e in parse.parse_locator(md):
                    db.execute("INSERT INTO locator VALUES (?,?,?,?,?,?,?,?,?)",
                               (idx, url, e["name"], e["kind"], e["street"], e["city"], e["state"], e["zip"],
                                e["services"]))
            n = parse.parse_branch_count(md)
            if n:
                db.execute("INSERT INTO counts VALUES (?,?,?,?)", (idx, url, pub, n))
            for text, href in parse.parse_links(md):
                db.execute("INSERT INTO links VALUES (?,?,?,?)", (idx, url, text, href))

            for head, text in parse.chunk_page(md):
                if text in seen_text and text in self._sent and self._sent[text][1] <= rank:
                    continue
                seen_text.add(text)
                cur = self._sent.get(text)
                if cur is None:
                    new_sent.append((url, rank, pub, head, pg.title or "", text, idx, idx))
                    self._sent[text] = [None, rank, pub, len(new_sent) - 1]
                else:
                    if cur[0] is not None and (rank < cur[1] or (rank == cur[1] and pub > (cur[2] or ""))):
                        db.execute("UPDATE sent SET url=?, rank=?, pub=?, head=?, title=? WHERE id=?",
                                   (url, rank, pub, head, pg.title or "", cur[0]))
                        cur[1], cur[2] = rank, pub
                    elif cur[0] is None and (rank < cur[1] or (rank == cur[1] and pub > (cur[2] or ""))):
                        i = cur[3]
                        new_sent[i] = (url, rank, pub, head, pg.title or "", text, idx, idx)
                        cur[1], cur[2] = rank, pub
        # new passages: insert, index for keyword search, and embed for vector search; then extend last_idx of all present ones
        vids, vtexts = [], []
        for (url, rank, pub, head, title, text, fi, li) in new_sent:
            cur = db.execute("INSERT INTO sent(url,rank,pub,head,title,text,first_idx,last_idx) VALUES (?,?,?,?,?,?,?,?)",
                             (url, rank, pub, head, title, text, fi, li))
            sid = cur.lastrowid
            self._sent[text][0] = sid
            slug = " ".join(parse.tokens(parse.url_path(url) + " " + title + " " + head))
            db.execute("INSERT INTO sent_fts(rowid, stext) VALUES (?,?)",
                       (sid, " ".join(parse.tokens(text)) + " " + slug))
            vids.append(sid)
            vtexts.append(((head + ". ") if head else "") + text[:1200])
        if self.vec is not None:
            self.vec.add(vids, vtexts)
        present = [self._sent[t][0] for t in seen_text if t in self._sent and self._sent[t][0] is not None]
        for i in range(0, len(present), 500):
            ch = present[i:i + 500]
            db.execute("UPDATE sent SET last_idx=? WHERE id IN (%s)" % ",".join("?" * len(ch)), [idx] + ch)
        db.commit()

    # ------------------------------------------------------------ helpers
    def snap_for(self, as_of):
        """Index of the latest snapshot taken on/before as_of (None -> latest)."""
        if not self.snaps:
            return None
        if not as_of:
            return len(self.snaps) - 1
        d = str(as_of)[:10]
        best = 0
        for i, (_, t) in enumerate(self.snaps):
            if t <= d:
                best = i
        return best

    def q(self, sql, args=()):
        with self.lock:         # one shared connection: serialise queries when answers run concurrently
            cur = self.db.execute(sql, args)
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
