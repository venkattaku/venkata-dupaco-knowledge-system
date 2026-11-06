#!/usr/bin/env python3
"""Append one iteration to docs/SCORE_LOG.md from a harness results folder.

    python tools/log_score.py --iter 1 --results results/iter1 \
        --title "Verified queries v1" --notes "what changed" [--dry-run]

Reads <results>/report.json and <results>/per_question.jsonl, writes:
  * a row into the summary table (above the ROWS marker)
  * a per-iteration section (category scores + questions still below 1.0)
  * a copy of the aggregate report at docs/score_reports/iter<N>.json

Re-running for the same iteration replaces its row and section.
Only aggregates and question ids are logged; answer text is not copied.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "docs" / "SCORE_LOG.md"
ROWS = "<!-- ROWS -->"
SECTIONS = "<!-- SECTIONS -->"

HEADER = f"""# Score log

Local score from `python harness/run_eval.py --eval eval/public_eval.jsonl` (40 public questions).
The conflicts pillar is not scored locally (no gold list ships with the kit), so `final` is the
weighted mean of accuracy, consistency and speed, with weights renormalised as the harness does.
Consistency and speed are multiplied by accuracy, as in the official scorer.

| Iter | Date | Commit | Change | Final | Accuracy | Consistency | Speed (p95 s) | Trap hits | Errors |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|
{ROWS}

{SECTIONS}
"""


def git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception:
        return "n/a"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iter", required=True, type=int)
    ap.add_argument("--results", required=True, type=Path)
    ap.add_argument("--title", required=True)
    ap.add_argument("--notes", default="")
    ap.add_argument("--commit", default=None, help="commit the run was made on (default: HEAD)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    res = a.results if a.results.is_absolute() else ROOT / a.results
    rep = json.loads((res / "report.json").read_text())
    pq = [json.loads(l) for l in (res / "per_question.jsonl").read_text().splitlines() if l.strip()]

    commit = a.commit or git("rev-parse", "--short", "HEAD")
    dirty = git("status", "--porcelain", "--", ".", ":!docs", ":!results")
    if a.commit is None and dirty not in ("", "n/a"):
        commit += "+wip"
    today = dt.date.today().isoformat()
    p = rep["pillars"]
    row = (
        f"| {a.iter} | {today} | `{commit}` | {a.title} | **{rep['final_score']:.3f}** | "
        f"{p['accuracy']:.3f} | {rep['consistency']['score']:.3f} | {rep['speed']['p95_s']:.2f} | "
        f"{rep['stale_trap_hits']} | {rep['errors']} |"
    )

    cats = "\n".join(
        f"| {k} | {v['n']} | {v['score']:.2f} |" for k, v in rep["by_category"].items()
    )
    weak = sorted((r for r in pq if r["score"] < 0.999), key=lambda r: (r["score"], r["id"]))
    weak_lines = "\n".join(
        f"| {r['id']} | {r['category']} | {r['score']:.2f} | "
        f"{'TRAP ' + ', '.join(r['trap_hits']) if r['trap_hits'] else ('missed ' + ', '.join(r['missed']) if r['missed'] else 'behaviour / source')} |"
        for r in weak
    ) or "| – | – | – | all questions at 1.0 |"
    section = f"""## Iteration {a.iter}: {a.title}

- Commit: `{commit}`  |  Date: {today}  |  Ingest: {rep['ingest_seconds']}s  |  p50/p95/max latency: {rep['speed']['p50_s']}/{rep['speed']['p95_s']}/{rep['speed']['max_s']}s
- Questions at full score: {sum(1 for r in pq if r['score'] >= 0.999)}/{len(pq)}
- {a.notes or 'No notes.'}

| Category | n | Score |
|---|---:|---:|
{cats}

Questions below 1.0:

| ID | Category | Score | Why |
|---|---|---:|---|
{weak_lines}

"""

    if a.dry_run:
        print(row)
        print(section)
        return

    LOG.parent.mkdir(parents=True, exist_ok=True)
    text = LOG.read_text() if LOG.exists() else HEADER
    # replace an existing row / section for this iteration
    text = re.sub(rf"^\| {a.iter} \|.*\n", "", text, flags=re.M)
    text = re.sub(rf"## Iteration {a.iter}: .*?(?=\n## Iteration |\Z)", "", text, flags=re.S)
    text = text.replace(ROWS, row + "\n" + ROWS)
    text = text.rstrip() + "\n\n" + section.rstrip() + "\n"
    LOG.write_text(text)

    out = ROOT / "docs" / "score_reports"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"iter{a.iter}.json").write_text(json.dumps(rep, indent=2))
    print(f"logged iteration {a.iter}: final={rep['final_score']}")


if __name__ == "__main__":
    main()
