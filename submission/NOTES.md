# Dupaco knowledge system — notes

The LLM picks a verified SQL query, the query runs on an in-memory SQLite built from all snapshots, and the LLM writes the
answer from the returned rows. See `docs/ARCHITECTURE.md` for the flow and `docs/DATA_MODEL.md` for the tables.

- **Setup:** Python 3.9+, `pip install -r requirements.txt` (numpy only). Set `DEEPINFRA_API_KEY`; without it the system
  answers with plain passage search (low accuracy, never crashes).
- **Files:** `solution.py` (entry point, `build()`), `kb/engine.py` (pipeline + the two prompts), `kb/catalog.py` +
  `kb/verified_queries.json` (the only SQL), `kb/store.py` + `kb/parse.py` (ingest), `kb/vec.py` (embeddings),
  `kb/llm.py` (DeepInfra client), `kb/conflicts.py`, `kb/trace.py`.
- **Debugging:** every step of every question (input, output, milliseconds) is appended to `solution_trace.csv`
  (`DUPACO_TRACE=0` disables it). Delete `.llm_cache.json` before a timing run; `.emb_cache.pkl` only saves embedding cost.
- **Scores:** `docs/SCORE_LOG.md`. Known gaps: dup-049 and dup-081 (retrieval/interpretation), dup-005 has no checkable answer.
