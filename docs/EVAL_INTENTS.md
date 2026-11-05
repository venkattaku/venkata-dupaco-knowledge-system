# Analysis of the 40 public eval questions

Source: `eval/public_eval.jsonl`. Total weight 64.5. Each question was checked against the latest snapshot to see where its answer lives.

## 1. Shape of the set

| Category (given) | Questions | Weight | Share of score |
|---|---:|---:|---:|
| stale_trap | 7 | 11.0 | 17.1% |
| branch_info | 6 | 10.0 | 15.5% |
| tier_disambiguation | 6 | 9.5 | 14.7% |
| temporal_as_of | 4 | 7.0 | 10.9% |
| list_completeness | 4 | 6.5 | 10.1% |
| conflict_resolution | 3 | 6.0 | 9.3% |
| should_refuse | 3 | 6.0 | 9.3% |
| entity_attribution | 4 | 5.5 | 8.5% |
| current_value | 3 | 3.0 | 4.7% |

- 20 questions carry a `group` id. Those are the ones the hidden set rewords; together they hold 50% of the weight. They drive the consistency pillar.
- 27 of 40 questions have a `must_not_include` trap; a trap hit zeroes the question.
- 4 questions have an empty `must_include` (dup-005, 102, 145, 147): they are scored on behaviour (refuse, or don't ask a clarifying question).
- Only 1 question has `as_of` set (dup-006). Event and period questions ("as of October 2026", "last year") carry the rest of the temporal weight.
- Only 8 questions list `expected_sources`. The source bonus is small (15%).
- IDs run up to dup-147, so the hidden pool is probably several times larger than the 40 shown. This is an inference from the ID range.

## 2. Member intents (what the person is asking for)

| Intent | What the member wants | Questions |
|---|---|---|
| **I1 Single rate lookup** | One number for a named product and tier | 001, 016, 017, 028, 035, 045, 046, 050, 006 |
| **I2 Rate survey** | "What are the rates?" with no product named; answer must cover several items | 009, 011, 052, 034, 040, 005 |
| **I3 Verify a claim** | Yes/no or false premise ("does any tier pay 0.35%?", "same hours everywhere?") | 049, 075, 094, 104 |
| **I4 Identifier or contact** | Routing number, phone, address | 054, 055, 060, 068 |
| **I5 Branch hours and status** | Lobby, drive-up, which branch, closed or open | 064, 065, 066, 104, 074, 075, 076, 102 |
| **I6 Organization stat** | Branch count, awards, employee volunteering | 073, 087, 088 |
| **I7 Policy or eligibility** | Who can join | 081 |
| **I8 Program explanation** | What is X / do you offer X | 031, 101, 094 |
| **I9 Navigation** | The URL to use | 008, 080, 082 |
| **I10 Unanswerable** | Rate or branch the site does not publish | 145, 147, 102 |

## 3. Objectives (what each question is really testing)

| Objective | Capability required | Questions | Typical failure it targets |
|---|---|---|---|
| **O1 Currency** | Prefer the latest, authoritative value | 009, 016, 017, 008, 080, 082, 087 | Quoting a stale calculator, old blog, legacy URL |
| **O2 Tier precision** | Pick the right row of a table | 001, 028, 035, 045, 046, 011 | Mixing tiers; quoting the intro rate (2.9%) as the standard APR |
| **O3 Entity attribution** | Don't confuse similar products or segments | 050, 054, 055, 101, 034 | Bright Savings vs other savings; business vs personal cards; savings rates in a student-loan answer |
| **O4 Completeness** | Return all items of a set | 034, 040, 005, 094, 076 | Only business cards; asking "which term?" instead of listing |
| **O5 Calibrated refusal** | Say "not listed" without inventing numbers | 145, 147, 102 | Making up an ARM or construction rate; fabricating Mullan Avenue hours |
| **O6 Temporal reasoning** | Use as-of date, event date or period | 006, 074, 075, 088 | Answering 4.00% for a May question; ignoring that a closure date has passed |
| **O7 Conflict resolution** | Choose between disagreeing counts or ranges | 073, 049, 081 | 24 vs 22 branches; "up to 0.35%" range |
| **O8 Conversation policy** | Answer first, don't gate on a question | 005, 065, 064 | Asking for ZIP or term before answering |
| **O9 Determinism** | Same answer when reworded or repeated | the 20 grouped questions | Different numbers per paraphrase |

## 4. Question-by-question map

"Where it lives" is the page type in the latest snapshot where the gold value was found.

| ID | Question (short) | Primary intent | Objective | Answer type | Where it lives | Trap in gold |
|---|---|---|---|---|---|---|
| 001 | 17-month special cert APY | I1 | O2 | number | `/rates`, `/personal/retirement`, `/business-rates` | jumbo 4.20 is the other tier |
| 009 | 30-year mortgage rate | I2 | O1, O2 | 2 numbers | `/rates`, home-loans page | 6.037%, 6.061%, 5.954% from `/homebuying-guidance` |
| 011 | Mortgage rates right now | I2 | O2 | number | `/rates` | 6.7%, 6.037% |
| 016 | 60-mo auto, 2025 model year | I1 | O1, O2 | number | `/rates`, auto pages | 5.34% on calculator and switch-and-earn |
| 017 | 84-mo auto, 2024 model year | I1 | O1, O2 | number | auto pages | 5.54% |
| 034 | Credit cards and APRs | I2 | O4, O3 | 4 names, 2+ numbers | `/personal/credit-cards`, `/business/credit-cards` | 9.9% |
| 035 | Platinum Visa standard APR | I1 | O2 | number | `/rates`, card page | 9.9% (intro 2.9% also present) |
| 045 | Share Savings $10k-$24,999 | I1 | O2 | number | `/rates` | 0.30%, 0.40% |
| 046 | Highest Share Savings APY | I1 | O2 | 2 numbers | `/rates` | 0.35% |
| 049 | Any tier pay 0.35%? | I3 | O7 | no + 0.20 | `/rates` | "up to 0.35" |
| 050 | Bright Savings rate | I1 | O3 | number | `/rates` | Jump Start, 0.35% |
| 052 | Checking interest rates | I2 | O2 | number | `/rates` | 3% APY |
| 028 | 36-month personal loan APR | I1 | O2 | number | `/rates`, personal-loans page | none |
| 005 | "Rate for the certificate of accounts" | I2 | O4, O8 | list | `/rates` | asking "which term" |
| 006 | 10-mo jumbo, as of May 2026 | I1 | O6 | number | snapshots 01-04 `/rates` | 4.00% (latest) |
| 054 | Routing number | I4 | O3 | number | `/contact`, cash-management | 271176899, masking `***`, `<val` |
| 055 | "Repeat the routing number" | I4 | O3, O8 | number | same | "coffee table" (a mis-retrieval) |
| 060 | Update contact info | I4 | O1 | phone | many pages | "member number" |
| 068 | Galena branch address | I4 | O3 | address | `/contact` locator | "unable to find" |
| 064 | General lobby hours | I5 | O8 | times | branch-opening press releases, `/contact` | none |
| 065 | "Your lobby hours" | I5 | O8 | times | same | "ZIP code" |
| 066 | Drive-up hours | I5 | O8 | times | press releases | none |
| 104 | Same hours at all branches? | I3 | O7 | no + schedules | press releases | none |
| 074 | When does Hy-Vee branch close | I5 | O6 | date | newsroom (dated 2025-06-20) | "don't have that detail" |
| 075 | Hy-Vee still open (Oct 2026)? | I3 | O6 | no + date | same | none |
| 076 | Where can Hy-Vee members bank | I5 | O4 | 2 names | same release, `/contact` | CO-OP Shared Branch |
| 102 | Mullan Avenue lobby hours | I10 | O5 | refusal | n/a | fabricated hours |
| 073 | How many branches | I6 | O7 | number | boilerplate in press releases | "24 branch" |
| 087 | Forbes recognition | I6 | O1 | ordinal | newsroom Forbes release | "fourth", 2020, 2021 |
| 088 | VTO employees last year | I6 | O6 | number | newsroom article reporting 2023 results | none |
| 081 | Who can join | I7 | O7 | 3 states | `/about/join` | none |
| 031 | What is Home$tart | I8 | O1 | amount | newsroom FHLB release | none |
| 101 | Student loan options | I8 | O3 | topic | `/personal/loans/student-loans` | Share Savings, 0.20% |
| 094 | Mobile wallets | I8 | O4 | 3 names | BrightTrack FAQ, mobile-payments page | none |
| 008 | Link to CD rates | I9 | O1 | URL | `/personal/savings-account#rates` | legacy `info.dupaco.com/...` |
| 080 | Branch/ATM locator URL | I9 | O1 | URL | `/contact` | `/locations/branch-hours` |
| 082 | How to join online | I9 | O1 | URL | `join.dupaco.com` | `info.dupaco.com/how_to_join` |
| 145 | 7/1 ARM rate | I10 | O5 | refusal | not on site | invented rate |
| 147 | Construction loan rate | I10 | O5 | refusal | not on site | invented rate |
| 040 | Credit card rates | I2 | O4 | 2+ numbers | card pages | business-only answer |

## 5. Findings that change the design

1. **Rate questions (I1 + I2) are about 38% of the weight** (24.5 of 64.5) and all resolve to table rows. A structured fact store with qualifiers beats text retrieval here.
2. **The traps are almost always embedded copies.** Gold traps like 5.34%, 6.037% and 9.9% appear on calculators, landing pages and `/homebuying-guidance`. A source-authority rule removes most of them.
3. **Hours questions have no clean source.** The `/contact` locator shows "Closed" for every branch, so lobby and drive-up hours come from branch-opening press releases (for example the Learning Lab release: lobby Mon-Thu 8:30-5, Fri 8:30-6, Sat 8:30-12:30; drive-up Mon-Fri 8-6). These are narrative pages, and the right behaviour is to give a typical schedule and offer to name the branch.
4. **Refusal needs an existence check, not a score threshold.** "Mullan Avenue branch" does appear in the latest snapshot (a staff profile in Waterloo, and a blog), but with no address or hours. Retrieval will find it. The system must see that no hours fact exists for that location.
5. **Behaviour requirements are hidden in `must_not_include`.** Strings like "ZIP code", "Which certificate term would you like", "I'm not asking again", "don't have that detail", "in these facts", "***" and "<val" are leftovers from a previous assistant's failure modes: gating questions, leaked template text, masked values. Answers should be direct, free of placeholders, and never ask a clarifying question before giving the data.
6. **Temporal questions are mostly not `as_of`.** dup-006 is the only dated query, and the 10-month jumbo is 3.90% in snapshots 01-04, so even a latest-only system would need the right answer from history. The other temporal items need event-date reasoning: a closure dated March 31, 2026 means "closed" by October 2026, and "last year" for volunteer time off maps to the 2023 figure in a newsroom article, a gold answer that ignores today's date.
7. **The gold text can lag the data.** dup-011's expected answer mentions a 15-year rate of 6.25%, but that value appears in none of the five snapshots (latest `/rates` shows 6.75%, earlier snapshots 5.375% to 6.000%). Only 7.13 is in `must_include`, so scoring is unaffected, but don't treat expected-answer prose as ground truth.
