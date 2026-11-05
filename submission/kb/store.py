"""SQLite store: every snapshot is ingested into relational tables (see docs/DATA_MODEL.md)."""
import json
import sqlite3

from . import parse as P

SCHEMA = """
CREATE TABLE snaps  (idx INTEGER PRIMARY KEY, snap_id TEXT, taken_on TEXT);
CREATE TABLE pages  (snap_idx INT, url TEXT, title TEXT, rank INT, pub TEXT, fetched_at TEXT);
CREATE TABLE rates  (id INTEGER PRIMARY KEY, snap_idx INT, url TEXT, rank INT, family TEXT, segment TEXT,
                     label TEXT, ckey TEXT, head TEXT, ctx TEXT, eff TEXT, rate REAL, apr REAL, apy REAL,
                     minearn REAL, raw TEXT);
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
        self.db.executescript(SCHEMA)
        self.snaps = []                  # [(snap_id, taken_on)]
        self._sent = {}                  # text -> [id, rank, pub]

    # ------------------------------------------------------------ ingest
    def ingest(self, snapshot):
        idx = len(self.snaps)
        self.snaps.append((snapshot.snapshot_id, snapshot.taken_on))
        db = self.db
        db.execute("INSERT INTO snaps VALUES (?,?,?)", (idx, snapshot.snapshot_id, snapshot.taken_on))
        seen_text = set()
        new_sent = []
        for pg in snapshot.pages:
            md = pg.markdown or ""
            url = pg.url
            rank = P.authority(url)
            pub = P.page_pub_date(md)
            db.execute("INSERT INTO pages VALUES (?,?,?,?,?,?)", (idx, url, pg.title, rank, pub, pg.fetched_at))
            path = P.url_path(url)

            for r in P.parse_rate_tables(url, md):
                db.execute(
                    "INSERT INTO rates(snap_idx,url,rank,family,segment,label,ckey,head,ctx,eff,rate,apr,apy,minearn,raw)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (idx, url, rank, r["family"], r["segment"], r["label"], P.ckey(r["family"] + "|" + r["label"]),
                     r["head"], r["ctx"], r["eff"], r["rate"], r["apr"], r["apy"], r["minearn"], r["raw"]))
            if "credit-cards" in path:
                for c in P.parse_card_rows(url, md):
                    db.execute("INSERT INTO cards VALUES (?,?,?,?,?,?,?,?)",
                               (idx, url, rank, c["name"], c["lo"], c["hi"], c["intro"], c["intro_text"]))
            for b in P.parse_hours_blocks(md):
                db.execute("INSERT INTO hours VALUES (?,?,?,?,?,?,?)",
                           (idx, url, pg.title, pub, b["kind"], json.dumps(b["lines"]), md[:4000]))
            if path == "/contact":
                for e in P.parse_locator(md):
                    db.execute("INSERT INTO locator VALUES (?,?,?,?,?,?,?,?,?)",
                               (idx, url, e["name"], e["kind"], e["street"], e["city"], e["state"], e["zip"],
                                e["services"]))
            n = P.parse_branch_count(md)
            if n:
                db.execute("INSERT INTO counts VALUES (?,?,?,?)", (idx, url, pub, n))
            for text, href in P.parse_links(md):
                db.execute("INSERT INTO links VALUES (?,?,?,?)", (idx, url, text, href))

            for head, text in P.chunk_page(md):
                key = text
                if key in seen_text and key in self._sent and self._sent[key][1] <= rank:
                    continue
                seen_text.add(key)
                cur = self._sent.get(key)
                if cur is None:
                    new_sent.append((url, rank, pub, head, pg.title or "", text, idx, idx))
                    self._sent[key] = [None, rank, pub, len(new_sent) - 1]
                else:
                    if cur[0] is not None and (rank < cur[1] or (rank == cur[1] and pub > (cur[2] or ""))):
                        db.execute("UPDATE sent SET url=?, rank=?, pub=?, head=?, title=? WHERE id=?",
                                   (url, rank, pub, head, pg.title or "", cur[0]))
                        cur[1], cur[2] = rank, pub
                    elif cur[0] is None and (rank < cur[1] or (rank == cur[1] and pub > (cur[2] or ""))):
                        i = cur[3]
                        new_sent[i] = (url, rank, pub, head, pg.title or "", text, idx, idx)
                        cur[1], cur[2] = rank, pub
        # insert new sentences + FTS rows; extend last_idx of those still present
        for (url, rank, pub, head, title, text, fi, li) in new_sent:
            cur = db.execute("INSERT INTO sent(url,rank,pub,head,title,text,first_idx,last_idx) VALUES (?,?,?,?,?,?,?,?)",
                             (url, rank, pub, head, title, text, fi, li))
            sid = cur.lastrowid
            self._sent[text][0] = sid
            slug = " ".join(P.tokens(P.url_path(url) + " " + title + " " + head))
            db.execute("INSERT INTO sent_fts(rowid, stext) VALUES (?,?)",
                       (sid, " ".join(P.tokens(text)) + " " + slug))
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
        cur = self.db.execute(sql, args)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
