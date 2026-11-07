"""Tiny CSV logger so a run can be audited step by step (input and output of each step).
Set DUPACO_LOG=0 to turn it off. Never records the API key.
"""
import csv
import json
import os
import sys
import threading

_lock = threading.Lock()
_warned = set()


def enabled():
    return os.environ.get("DUPACO_LOG", "1") != "0"


def path():
    return os.environ.get("DUPACO_LOG_FILE", "solution_log.csv")


def _cell(v):
    if not isinstance(v, str):
        v = json.dumps(v, ensure_ascii=False, default=str)
    return v if len(v) <= 30000 else v[:30000] + " ...[truncated]"      # Excel cell limit is 32,767


def log(event, **kw):
    """Misc events (errors) in the same columns."""
    q = kw.pop("q", "")
    step(q, "", event, "", "\n".join("%s: %s" % (k, _cell(v)) for k, v in kw.items()))


def step(q, no, name, inp, out, ms=None, note=""):
    """One CSV row per pipeline step: question | step no | step | INPUT | OUTPUT | ms | note."""
    if not enabled():
        return
    try:
        with _lock:
            p = path()
            new = not os.path.exists(p) or os.path.getsize(p) == 0
            with open(p, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["question", "step_no", "step", "input", "output", "ms", "note"])
                w.writerow([q or "", no, name, _cell(inp), _cell(out), "" if ms is None else ms, _cell(note)])
    except Exception:
        pass


def warn_once(key, msg):
    """Print a distinct warning to stderr once (so a failing router is visible in the console)."""
    if key not in _warned:
        _warned.add(key)
        print("[dupaco] " + msg, file=sys.stderr, flush=True)
