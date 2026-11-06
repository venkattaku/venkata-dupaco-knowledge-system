# Score log

Local score from `python harness/run_eval.py --eval eval/public_eval.jsonl` (40 public questions).
The conflicts pillar is not scored locally (no gold list ships with the kit), so `final` is the
weighted mean of accuracy, consistency and speed, with weights renormalised as the harness does.
Consistency and speed are multiplied by accuracy, as in the official scorer.

| Iter | Date | Commit | Change | Final | Accuracy | Consistency | Speed (p95 s) | Trap hits | Errors |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|
| 0 | 2026-11-05 | `dc0266f` | Starter (naive paragraph overlap), unchanged | **0.093** | 0.093 | 1.000 | 0.31 | 0 | 0 |
| 1 | 2026-11-05 | `c58ed96+wip` | SQLite ingest + verified queries (rule router, templated answers) | **0.969** | 0.969 | 1.000 | 1.14 | 0 | 0 |
| 2 | 2026-11-05 | `8b7c545+wip` | Verified queries moved to JSON + optional Groq intent router | **0.969** | 0.969 | 1.000 | 1.10 | 0 | 0 |
| 3 | 2026-11-06 | `5eacb9f+wip` | DeepInfra LLM router + answer writer | **0.774** | 0.805 | 1.000 | 5.94 | 0 | 0 |
| 4 | 2026-11-06 | `5eacb9f+wip` | Tier waterfall, per-step trace, hedged requests | **0.769** | 0.851 | 1.000 | 11.80 | 0 | 0 |
| 5 | 2026-11-06 | `5eacb9f+wip` | Hours schedules merged, link texts, partial answers | **0.844** | 0.874 | 1.000 | 5.60 | 0 | 0 |
| 6 | 2026-11-06 | `5eacb9f+wip` | Dense vectors (numpy) fused with FTS5 | **0.840** | 0.881 | 1.000 | 6.75 | 1 | 0 |
| 7 | 2026-11-06 | `5eacb9f+wip` | Wider keyword recall, two-query router, ordinal rule | **0.871** | 0.900 | 1.000 | 5.34 | 0 | 0 |
| 8 | 2026-11-06 | `d72ec04+wip` | Section outline for the best pages, merged-hours source URLs, tier-ordered sources | **0.874** | 0.933 | 1.000 | 8.50 | 0 | 0 |
| 9 | 2026-11-06 | `f085bf3+wip` | Row numbers kept out of answer text (default-product rule tried, no effect) | **0.863** | 0.933 | 1.000 | 9.66 | 0 | 0 |
| 10 | 2026-11-06 | `5215f4f+wip` | Hours as one list per kind, main-product flag and ordering for rates, one page per schedule in sources | **0.880** | 0.938 | 1.000 | 8.30 | 0 | 0 |
| 11 | 2026-11-06 | `c31c373` | rate_lookup: criteria search over rate tiers, main-product default (fixes dup-049) | **0.923** | 0.969 | 1.000 | 6.84 | 0 | 0 |
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

## Iteration 1: SQLite ingest + verified queries (rule router, templated answers)

- Commit: `c58ed96+wip`  |  Date: 2026-11-05  |  Ingest: 10.6s  |  p50/p95/max latency: 0.0/1.14/1.19s
- Questions at full score: 39/40
- No LLM, stdlib only. Rate tables parsed per snapshot; canonical-page + newest-effective-date dominance in SQL; hours/address/count/closure/link handlers; BM25 fallback with refusal. Confirmed identical 0.969 on user machine (Py3.10). dup-005 has no must_include so is unscorable without the judge.

| Category | n | Score |
|---|---:|---:|
| branch_info | 6 | 1.00 |
| conflict_resolution | 3 | 1.00 |
| current_value | 3 | 1.00 |
| entity_attribution | 4 | 1.00 |
| list_completeness | 4 | 0.75 |
| should_refuse | 3 | 1.00 |
| stale_trap | 7 | 1.00 |
| temporal_as_of | 4 | 1.00 |
| tier_disambiguation | 6 | 1.00 |

Questions below 1.0:

| ID | Category | Score | Why |
|---|---|---:|---|
| dup-005 | list_completeness | 0.00 | behaviour / source |

## Iteration 2: Verified queries moved to JSON + optional Groq intent router

- Commit: `8b7c545+wip`  |  Date: 2026-11-05  |  Ingest: 10.9s  |  p50/p95/max latency: 0.0/1.1/1.15s
- Questions at full score: 39/40
- All SQL in kb/verified_queries.json; Groq function-calling picks intent/family when GROQ_API_KEY set, else keyword rules. Score shown is the no-key path (identical to iter 1). Groq unreachable from sandbox and user device (HTTP 000), so the live router is untested; verified against a local mock server only.

| Category | n | Score |
|---|---:|---:|
| branch_info | 6 | 1.00 |
| conflict_resolution | 3 | 1.00 |
| current_value | 3 | 1.00 |
| entity_attribution | 4 | 1.00 |
| list_completeness | 4 | 0.75 |
| should_refuse | 3 | 1.00 |
| stale_trap | 7 | 1.00 |
| temporal_as_of | 4 | 1.00 |
| tier_disambiguation | 6 | 1.00 |

Questions below 1.0:

| ID | Category | Score | Why |
|---|---|---:|---|
| dup-005 | list_completeness | 0.00 | behaviour / source |

## Iteration 3: DeepInfra LLM router + answer writer

- Commit: `5eacb9f+wip`  |  Date: 2026-11-06  |  Ingest: 8.0s  |  p50/p95/max latency: 3.29/5.94/9.05s
- Questions at full score: 30/40
- local run 8 (DeepInfra)

| Category | n | Score |
|---|---:|---:|
| branch_info | 6 | 0.87 |
| conflict_resolution | 3 | 0.33 |
| current_value | 3 | 0.67 |
| entity_attribution | 4 | 1.00 |
| list_completeness | 4 | 0.50 |
| should_refuse | 3 | 1.00 |
| stale_trap | 7 | 0.86 |
| temporal_as_of | 4 | 0.75 |
| tier_disambiguation | 6 | 1.00 |

Questions below 1.0:

| ID | Category | Score | Why |
|---|---|---:|---|
| dup-005 | list_completeness | 0.00 | behaviour / source |
| dup-008 | stale_trap | 0.00 | missed dupaco.com/personal/savings-account |
| dup-049 | conflict_resolution | 0.00 | missed 0.20 |
| dup-060 | current_value | 0.00 | missed 800-373-7600 |
| dup-081 | conflict_resolution | 0.00 | missed Iowa, Illinois, Wisconsin |
| dup-088 | temporal_as_of | 0.00 | missed 294 |
| dup-094 | list_completeness | 0.00 | missed Apple Pay, Google Pay, Samsung Pay |
| dup-104 | branch_info | 0.50 | missed noon |
| dup-064 | branch_info | 0.85 | behaviour / source |
| dup-066 | branch_info | 0.85 | behaviour / source |

## Iteration 4: Tier waterfall, per-step trace, hedged requests

- Commit: `5eacb9f+wip`  |  Date: 2026-11-06  |  Ingest: 8.3s  |  p50/p95/max latency: 3.15/11.8/13.12s
- Questions at full score: 32/40
- local run 11 (DeepInfra)

| Category | n | Score |
|---|---:|---:|
| branch_info | 6 | 0.87 |
| conflict_resolution | 3 | 0.67 |
| current_value | 3 | 0.67 |
| entity_attribution | 4 | 1.00 |
| list_completeness | 4 | 0.75 |
| should_refuse | 3 | 1.00 |
| stale_trap | 7 | 0.86 |
| temporal_as_of | 4 | 0.75 |
| tier_disambiguation | 6 | 1.00 |

Questions below 1.0:

| ID | Category | Score | Why |
|---|---|---:|---|
| dup-005 | list_completeness | 0.00 | behaviour / source |
| dup-008 | stale_trap | 0.00 | missed dupaco.com/personal/savings-account |
| dup-049 | conflict_resolution | 0.00 | missed 0.20 |
| dup-060 | current_value | 0.00 | missed 800-373-7600 |
| dup-088 | temporal_as_of | 0.00 | missed 294 |
| dup-104 | branch_info | 0.50 | missed noon |
| dup-064 | branch_info | 0.85 | behaviour / source |
| dup-066 | branch_info | 0.85 | behaviour / source |

## Iteration 5: Hours schedules merged, link texts, partial answers

- Commit: `5eacb9f+wip`  |  Date: 2026-11-06  |  Ingest: 9.3s  |  p50/p95/max latency: 2.74/5.6/6.49s
- Questions at full score: 33/40
- local run 14 (DeepInfra)

| Category | n | Score |
|---|---:|---:|
| branch_info | 6 | 0.87 |
| conflict_resolution | 3 | 0.67 |
| current_value | 3 | 0.67 |
| entity_attribution | 4 | 1.00 |
| list_completeness | 4 | 0.75 |
| should_refuse | 3 | 1.00 |
| stale_trap | 7 | 1.00 |
| temporal_as_of | 4 | 0.75 |
| tier_disambiguation | 6 | 1.00 |

Questions below 1.0:

| ID | Category | Score | Why |
|---|---|---:|---|
| dup-005 | list_completeness | 0.00 | behaviour / source |
| dup-049 | conflict_resolution | 0.00 | missed 0.20 |
| dup-060 | current_value | 0.00 | missed 800-373-7600 |
| dup-088 | temporal_as_of | 0.00 | missed 294 |
| dup-104 | branch_info | 0.50 | missed noon |
| dup-064 | branch_info | 0.85 | behaviour / source |
| dup-066 | branch_info | 0.85 | behaviour / source |

## Iteration 6: Dense vectors (numpy) fused with FTS5

- Commit: `5eacb9f+wip`  |  Date: 2026-11-06  |  Ingest: 45.9s  |  p50/p95/max latency: 3.13/6.75/7.29s
- Questions at full score: 35/40
- local run 17 (DeepInfra)

| Category | n | Score |
|---|---:|---:|
| branch_info | 6 | 1.00 |
| conflict_resolution | 3 | 0.33 |
| current_value | 3 | 1.00 |
| entity_attribution | 4 | 0.96 |
| list_completeness | 4 | 0.75 |
| should_refuse | 3 | 1.00 |
| stale_trap | 7 | 0.86 |
| temporal_as_of | 4 | 1.00 |
| tier_disambiguation | 6 | 1.00 |

Questions below 1.0:

| ID | Category | Score | Why |
|---|---|---:|---|
| dup-005 | list_completeness | 0.00 | behaviour / source |
| dup-049 | conflict_resolution | 0.00 | missed 0.20 |
| dup-081 | conflict_resolution | 0.00 | missed Iowa, Illinois, Wisconsin |
| dup-087 | stale_trap | 0.00 | TRAP 2020 |
| dup-054 | entity_attribution | 0.85 | behaviour / source |

## Iteration 7: Wider keyword recall, two-query router, ordinal rule

- Commit: `5eacb9f+wip`  |  Date: 2026-11-06  |  Ingest: 7.9s  |  p50/p95/max latency: 2.88/5.34/7.87s
- Questions at full score: 35/40
- local run 19 (DeepInfra)

| Category | n | Score |
|---|---:|---:|
| branch_info | 6 | 0.97 |
| conflict_resolution | 3 | 0.33 |
| current_value | 3 | 1.00 |
| entity_attribution | 4 | 0.96 |
| list_completeness | 4 | 0.75 |
| should_refuse | 3 | 1.00 |
| stale_trap | 7 | 1.00 |
| temporal_as_of | 4 | 1.00 |
| tier_disambiguation | 6 | 1.00 |

Questions below 1.0:

| ID | Category | Score | Why |
|---|---|---:|---|
| dup-005 | list_completeness | 0.00 | behaviour / source |
| dup-049 | conflict_resolution | 0.00 | missed 0.20 |
| dup-081 | conflict_resolution | 0.00 | missed Iowa, Illinois, Wisconsin |
| dup-054 | entity_attribution | 0.85 | behaviour / source |
| dup-066 | branch_info | 0.85 | behaviour / source |

## Iteration 8: Section outline for the best pages, merged-hours source URLs, tier-ordered sources

- Commit: `d72ec04+wip`  |  Date: 2026-11-06  |  Ingest: 4.4s  |  p50/p95/max latency: 5.11/8.5/11.99s
- Questions at full score: 37/40
- local run 20 (DeepInfra)

| Category | n | Score |
|---|---:|---:|
| branch_info | 6 | 0.97 |
| conflict_resolution | 3 | 0.67 |
| current_value | 3 | 1.00 |
| entity_attribution | 4 | 1.00 |
| list_completeness | 4 | 0.75 |
| should_refuse | 3 | 1.00 |
| stale_trap | 7 | 1.00 |
| temporal_as_of | 4 | 1.00 |
| tier_disambiguation | 6 | 1.00 |

Questions below 1.0:

| ID | Category | Score | Why |
|---|---|---:|---|
| dup-005 | list_completeness | 0.00 | behaviour / source |
| dup-049 | conflict_resolution | 0.00 | missed 0.20 |
| dup-066 | branch_info | 0.85 | behaviour / source |

## Iteration 9: Row numbers kept out of answer text (default-product rule tried, no effect)

- Commit: `f085bf3+wip`  |  Date: 2026-11-06  |  Ingest: 4.3s  |  p50/p95/max latency: 3.9/9.66/12.79s
- Questions at full score: 37/40
- local run 21 (DeepInfra)

| Category | n | Score |
|---|---:|---:|
| branch_info | 6 | 0.97 |
| conflict_resolution | 3 | 0.67 |
| current_value | 3 | 1.00 |
| entity_attribution | 4 | 1.00 |
| list_completeness | 4 | 0.75 |
| should_refuse | 3 | 1.00 |
| stale_trap | 7 | 1.00 |
| temporal_as_of | 4 | 1.00 |
| tier_disambiguation | 6 | 1.00 |

Questions below 1.0:

| ID | Category | Score | Why |
|---|---|---:|---|
| dup-005 | list_completeness | 0.00 | behaviour / source |
| dup-049 | conflict_resolution | 0.00 | missed 0.20 |
| dup-066 | branch_info | 0.85 | behaviour / source |

## Iteration 10: Hours as one list per kind, main-product flag and ordering for rates, one page per schedule in sources

- Commit: `5215f4f+wip`  |  Date: 2026-11-06  |  Ingest: 4.4s  |  p50/p95/max latency: 4.9/8.3/18.85s
- Questions at full score: 38/40
- local run 23 (DeepInfra)

| Category | n | Score |
|---|---:|---:|
| branch_info | 6 | 1.00 |
| conflict_resolution | 3 | 0.67 |
| current_value | 3 | 1.00 |
| entity_attribution | 4 | 1.00 |
| list_completeness | 4 | 0.75 |
| should_refuse | 3 | 1.00 |
| stale_trap | 7 | 1.00 |
| temporal_as_of | 4 | 1.00 |
| tier_disambiguation | 6 | 1.00 |

Questions below 1.0:

| ID | Category | Score | Why |
|---|---|---:|---|
| dup-005 | list_completeness | 0.00 | behaviour / source |
| dup-049 | conflict_resolution | 0.00 | missed 0.20 |

## Iteration 11: rate_lookup: criteria search over rate tiers, main-product default (fixes dup-049)

- Commit: `c31c373`  |  Date: 2026-11-06  |  Ingest: 8.1s  |  p50/p95/max latency: 3.63/6.84/6.96s
- Questions at full score: 39/40
- New verified query rate_lookup filters tiers by product, rate and balance with a per-product summary row; with no product named the main product is always included.

| Category | n | Score |
|---|---:|---:|
| branch_info | 6 | 1.00 |
| conflict_resolution | 3 | 1.00 |
| current_value | 3 | 1.00 |
| entity_attribution | 4 | 1.00 |
| list_completeness | 4 | 0.75 |
| should_refuse | 3 | 1.00 |
| stale_trap | 7 | 1.00 |
| temporal_as_of | 4 | 1.00 |
| tier_disambiguation | 6 | 1.00 |

Questions below 1.0:

| ID | Category | Score | Why |
|---|---|---:|---|
| dup-005 | list_completeness | 0.00 | behaviour / source |
