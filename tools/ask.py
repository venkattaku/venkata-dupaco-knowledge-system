#!/usr/bin/env python3
"""Ask a few questions without the full harness (fast loop for one failing question).

Usage (from the kit folder, same terminal as DEEPINFRA_API_KEY):
    python3 tools/ask.py "Do any Dupaco savings tiers pay 0.35% APY?" ["another question" ...]
Prints the router's choice, the rows the query returned, and the final answer with sources."""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "harness"), str(root / "submission")]
os.environ.setdefault("LLM_CACHE", "")
import run_eval  # noqa: E402
import solution  # noqa: E402

ks = solution.build()
for snap in run_eval.load_snapshots(root / "snapshots"):
    ks.ingest(snap)
for q in sys.argv[1:]:
    a = ks.answer(q)
    print("\nQ:", q, "\nA:", a.text, "\nSOURCES:", [s.url for s in a.sources])
