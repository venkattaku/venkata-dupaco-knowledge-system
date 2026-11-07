# Architecture

Two LLM calls around one database lookup. Judgement lives in two prompts; the code has no rule logic.

```
question ──► 1 ROUTE ──► 2 RUN ──► 3 WRITE ──► 4 SOURCES ──► Answer
            (LLM picks   (SQLite,   (LLM writes  (URLs of the
             a query)    no LLM)    from rows)   rows it used)
```

## Ingest (`kb/store.py`, `kb/parse.py`)
Each snapshot is parsed into one in-memory SQLite database:

- **Structured tables:** rate tables (with effective dates), credit cards, branch hours, branch locator, branch count, links.
- **Passages:** page text split into chunks, stored once even if it appears in several snapshots, with the range of snapshots in which it exists. Each passage is indexed twice: FTS5 keywords, and a dense vector (`kb/vec.py`, DeepInfra embeddings, kept as a numpy matrix and cached on disk).
- **Authority:** every page gets a tier from its URL (official product pages > site pages > newsroom/calculators > blog/PDF).

## Answering (`kb/engine.py`)
1. **Route.** The LLM sees the question and the tool schemas built from `kb/verified_queries.json` (eight parameterised queries: `rates`, `rate_lookup`, `credit_cards`, `branch_hours`, `branch_locations`, `branch_count`, `links`, `search_text`). It calls one to three of them and fills in the parameters, including an `as_of` date when the question names a past date.
2. **Run.** `kb/catalog.py` executes that SQL against the snapshot that was current at the question's date. These are the only statements that ever run. `search_text` fuses keyword and vector hits by reciprocal rank; the question is embedded in a background thread while step 1 runs, so it adds no latency. `rate_lookup` filters tiers by product, rate or balance and adds a per-product min/max row. `branch_hours` merges identical schedules into one row per kind (lobby, drive-up) so every schedule is in one list. `search_text` also adds a page outline: one row per section heading of the two best pages, so a fact under a neighbouring heading ("Local Service" next to "You're Eligible to Join") is visible. If nothing comes back, a plain passage search is tried.
3. **Write.** The LLM gets today's date, the question and the numbered rows (each labelled with its source tier) and calls an `answer` function with the text, a confidence flag and the row numbers it used. Prompt rules: use only the rows, prefer the highest tier and newest date, copy numbers exactly.
4. **Sources.** The URLs of the rows it cites become the sources. If it is not confident, the answer is a fixed refusal with no figures and no sources.

## Conflicts (`kb/conflicts.py`)
SQL over the latest snapshot finds rate products shown with different values, differing branch counts and differing hours, and names the winner (official page, newest date).

## Robustness
- `kb/llm.py`: disk cache, retries with backoff, a duplicate "hedged" request when a call is slow, a call budget.
- Without an API key, or if embeddings fail, it falls back to keyword passage search.
- `kb/trace.py` writes `solution_trace.csv`: the input and output of every step of every question.

## Configuration
`DEEPINFRA_API_KEY` (required for the LLM), `DEEPINFRA_MODEL`, `EMBED_MODEL`, `DUPACO_TRACE=0` disables the trace.
