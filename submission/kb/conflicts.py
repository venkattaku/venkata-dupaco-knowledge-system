"""conflicts(): places where the website disagrees with itself, found with SQL over the latest snapshot.

Three kinds: the same rate product shown with different values, the branch count quoted differently, and lobby /
drive-up hours that differ between branches. Each Conflict names the winning value and why it wins."""
import json
from collections import defaultdict

from contract import Conflict, Source


def find_conflicts(store):
    s, out = store, []
    if not s.snaps:
        return out
    si = len(s.snaps) - 1
    by = defaultdict(list)
    for r in s.q("SELECT * FROM rates WHERE snap_idx=? AND family!='other'", (si,)):
        by[r["ckey"]].append(r)

    def show(r):
        return ", ".join(x for x in (
            "%.3f%% APY" % r["apy"] if r["apy"] is not None else "",
            "%.3f%% rate" % r["rate"] if r["rate"] is not None and r["apy"] is None else "",
            "%.3f%% APR" % r["apr"] if r["apr"] is not None else "") if x)
    for rs in by.values():
        if len({(r["rate"], r["apr"], r["apy"]) for r in rs}) > 1:
            win = sorted(rs, key=lambda r: (r["rank"] > 1, -int((r["eff"] or "0").replace("-", "") or 0), r["rank"]))[0]
            vals = list(dict.fromkeys(show(r) for r in rs))
            out.append(Conflict(
                topic="%s (%s)" % (win["label"].replace(" | ", ", "), win["family"].replace("_", " ")),
                values=vals, sources=[Source(url=r["url"], snapshot_id=s.snaps[si][0], quote=r["raw"][:240]) for r in rs[:6]],
                resolution=show(win),
                reason="The canonical product page%s supersedes copies on promo/calculator/other pages."
                       % (" (rates effective %s)" % win["eff"] if win["eff"] else "")))
    cnts = s.q("SELECT value, url, pub FROM counts WHERE snap_idx=? ORDER BY pub DESC", (si,))
    if len({c["value"] for c in cnts}) > 1:
        out.append(Conflict(topic="number of Dupaco branch office locations",
                            values=list(dict.fromkeys(str(c["value"]) for c in cnts)),
                            sources=[Source(url=cnts[0]["url"], snapshot_id=s.snaps[si][0]),
                                     Source(url=cnts[-1]["url"], snapshot_id=s.snaps[si][0])],
                            resolution=str(cnts[0]["value"]),
                            reason="Press-release boilerplate is stale on older posts; the most recently dated page wins."))
    hrs = s.q("SELECT url, kind, lines FROM hours WHERE snap_idx=?", (si,))
    for kind in ("lobby", "drive-up"):
        variants = {}
        for h in hrs:
            if h["kind"] == kind:
                variants.setdefault(h["lines"], h["url"])
        if len(variants) > 1:
            out.append(Conflict(topic="%s hours differ by branch" % kind,
                                values=["; ".join(json.loads(k)) for k in variants],
                                sources=[Source(url=u, snapshot_id=s.snaps[si][0]) for u in variants.values()],
                                resolution=None, reason="Hours are branch-specific; no single schedule applies to all branches."))
    return out
