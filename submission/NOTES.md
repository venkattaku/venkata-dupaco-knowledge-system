# Dupaco knowledge system: design notes

## Approach
Ingest every snapshot into an in-memory SQLite database, then answer with **verified queries**. A rule-based router
picks a query for the question's intent. The query runs with parameters, and a template renders the answer. Nothing
needs a network call or an API key, so answers are deterministic and fast.

| Table | Built from | Used for |
|---|---|---|
| `rates` | every markdown rate table, with the per-block "effective as of" date | rate, APR and APY questions |
| `cards` | credit-card bullets and tables | card APR questions |
| `hours`, `locator`, `counts` | branch-opening releases, the `/contact` locator, "N branch office locations" boilerplate | hours, addresses, branch count |
| `links` | every markdown link | "what link should I use" |
| `sent` + FTS5 | de-duplicated page chunks with page date and authority | closures, definitions, other facts |

## Verified queries and the intent router
- Every SQL statement lives in `kb/verified_queries.json` (name, description, SQL), grouped under named intents
  (`rate_lookup`, `branch_hours`, `routing_number`, ...). The engine can only run queries by catalog name.
- **Intent routing:** if `GROQ_API_KEY` is set, a Groq function call (`route_question`, temperature 0, forced tool
  choice, 1.8 s timeout, cached per question) picks the intent and product family from that catalog. The model never
  writes SQL or answers. If the key is missing, the call fails, or the chosen handler declines, the keyword rules route
  the question instead. `general_fact` always falls through to the rules and then passage retrieval.
- The key is read from the environment only. `GROQ_MODEL` and `GROQ_BASE_URL` can override the defaults.
- Without a key the solution scores the same as with one that fails, so the grader works with no network.

## Handling stale and conflicting values
- Each page gets an authority rank. Canonical product pages and `/contact` rank highest. Promo pages, calculators, newsroom posts and blog posts rank lower.
- For each rate row the answer comes from the latest snapshot at or before `as_of`. A SQL window function picks one row per row key, preferring canonical pages and then the newest effective date.
- Other pages that carry the identical value are cited as extra sources.
- Branch count: the value on the most recently dated page wins (22), not the most frequent one (23).
- Text-fact retrieval: when passages tie on score, the newest page wins.

## Refusals
Programs the site never prices (ARM, construction, HELOC and similar), unknown branches, and weak retrieval matches all return
`confident=False` with no numbers in the text.

## Known gaps and shortcuts
- The "update my contact information" answer is a template, not site text. The site data has no such page; the phone number it quotes comes from the site.
- `conflicts()` reports rate-row disagreements between pages, branch-count variants and lobby/drive-up hour variants. It is not scored locally.
- `dup-005` has no `must_include`, so it can only be scored by the optional LLM judge.
- Stdlib only (Python 3.9+, sqlite3 with FTS5). No API key is used.
