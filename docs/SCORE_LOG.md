# Score log

Local score from `python harness/run_eval.py --eval eval/public_eval.jsonl` (40 public questions).
The conflicts pillar is not scored locally (no gold list ships with the kit), so `final` is the
weighted mean of accuracy, consistency and speed, with weights renormalised as the harness does.
Consistency and speed are multiplied by accuracy, as in the official scorer.

| Iter | Date | Commit | Change | Final | Accuracy | Consistency | Speed (p95 s) | Trap hits | Errors |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|
| 0 | 2026-11-05 | `dc0266f` | Starter (naive paragraph overlap), unchanged | **0.093** | 0.093 | 1.000 | 0.31 | 0 | 0 |
<!-- ROWS -->

<!-- SECTIONS -->

## Iteration 0: Starter (naive paragraph overlap), unchanged

- Commit: `dc0266f`  |  Date: 2026-11-05  |  Ingest: 0.0s  |  p50/p95/max latency: 0.25/0.31/0.35s
- Questions at full score: 4/40
- Baseline. Keeps the latest copy of each page, returns the paragraph sharing most words with the question, ignores as_of, reports no conflicts. Consistency and speed look perfect but are multiplied by an accuracy of 0.093.

| Category | n | Score |
|---|---:|---:|
| branch_info | 6 | 0.17 |
| conflict_resolution | 3 | 0.00 |
| current_value | 3 | 0.00 |
| entity_attribution | 4 | 0.25 |
| list_completeness | 4 | 0.00 |
| should_refuse | 3 | 0.00 |
| stale_trap | 7 | 0.14 |
| temporal_as_of | 4 | 0.25 |
| tier_disambiguation | 6 | 0.00 |

Questions below 1.0:

| ID | Category | Score | Why |
|---|---|---:|---|
| dup-001 | tier_disambiguation | 0.00 | missed 4.10% |
| dup-005 | list_completeness | 0.00 | behaviour / source |
| dup-006 | temporal_as_of | 0.00 | missed 3.90% |
| dup-008 | stale_trap | 0.00 | missed dupaco.com/personal/savings-account |
| dup-009 | stale_trap | 0.00 | missed 7.13, 7.25 |
| dup-011 | tier_disambiguation | 0.00 | missed 7.13 |
| dup-016 | stale_trap | 0.00 | missed 5.39% |
| dup-017 | stale_trap | 0.00 | missed 5.59% |
| dup-028 | tier_disambiguation | 0.00 | missed 10.49 |
| dup-031 | current_value | 0.00 | missed 15,000 |
| dup-034 | list_completeness | 0.00 | missed Platinum Visa, Rewards Visa, Business Platinum, Business Rewards, 12.5, 20.5 |
| dup-035 | tier_disambiguation | 0.00 | missed 12.5 |
| dup-040 | list_completeness | 0.00 | missed 12.5, 15.5 |
| dup-045 | tier_disambiguation | 0.00 | missed 0.15 |
| dup-046 | tier_disambiguation | 0.00 | missed 0.20, 25,000 |
| dup-049 | conflict_resolution | 0.00 | missed 0.20 |
| dup-050 | entity_attribution | 0.00 | missed 2.25 |
| dup-052 | current_value | 0.00 | missed 2.50% |
| dup-054 | entity_attribution | 0.00 | missed 273974581 |
| dup-060 | current_value | 0.00 | missed 800-373-7600 |
| dup-064 | branch_info | 0.00 | missed 8:30 |
| dup-065 | branch_info | 0.00 | missed 8:30 |
| dup-066 | branch_info | 0.00 | missed 8 a.m., 6 p.m. |
| dup-068 | branch_info | 0.00 | missed 11375 Oldenburg, 61036 |
| dup-073 | conflict_resolution | 0.00 | missed 22 |
| dup-075 | temporal_as_of | 0.00 | missed March 31, 2026 |
| dup-081 | conflict_resolution | 0.00 | missed Iowa, Illinois, Wisconsin |
| dup-082 | stale_trap | 0.00 | missed join.dupaco.com |
| dup-087 | stale_trap | 0.00 | missed fifth |
| dup-088 | temporal_as_of | 0.00 | missed 294 |
| dup-094 | list_completeness | 0.00 | missed Apple Pay, Google Pay, Samsung Pay |
| dup-101 | entity_attribution | 0.00 | missed student loan |
| dup-102 | should_refuse | 0.00 | behaviour / source |
| dup-104 | branch_info | 0.00 | missed 12:30, noon |
| dup-145 | should_refuse | 0.00 | behaviour / source |
| dup-147 | should_refuse | 0.00 | behaviour / source |
