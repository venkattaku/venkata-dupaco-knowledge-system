# Architecture

Two LLM calls around one database lookup. All judgement lives in two prompts; the code has no keyword or rule logic.

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
1. **Route.** The LLM sees the question and the tool schemas built from `kb/verified_queries.json` (seven parameterised queries: `rates`, `credit_cards`, `branch_hours`, `branch_locations`, `branch_count`, `links`, `search_text`). It calls one to three of them and fills in the parameters, including an `as_of` date when the question names a past date.
2. **Run.** `kb/catalog.py` executes that SQL against the snapshot that was current at the question's date. These are the only statements that ever run. `search_text` fuses keyword and vector hits by reciprocal rank; the question is embedded in a background thread while step 1 runs, so it adds no latency. If nothing comes back, a plain passage search is tried.
3. **Write.** The LLM gets today's date, the question and the numbered rows (each labelled with its source tier) and calls an `answer` function with the text, a confidence flag and the row numbers it used. Prompt rules: use only the rows, prefer the highest tier and the newest date, copy numbers exactly, list every schedule when asked whether branches differ.
4. **Sources.** The URLs of the rows it cites become the sources. If it is not confident, the answer is a fixed refusal with no figures and no sources.

## Conflicts (`kb/conflicts.py`)
SQL over the latest snapshot finds rate products shown with different values, differing branch counts and differing hours, and names the winner (official page, newest date).

## Robustness
- `kb/llm.py`: disk cache, retries with backoff, a duplicate "hedged" request when a call is slow, a call budget.
- Without an API key, or if embeddings fail, the system falls back to keyword passage search and never crashes.
- `kb/trace.py` writes `solution_trace.csv`: the input and output of every step of every question.

## Configuration
`DEEPINFRA_API_KEY` (required for the LLM), `DEEPINFRA_MODEL`, `EMBED_MODEL`, `DUPACO_TRACE=0` to disable the trace.
