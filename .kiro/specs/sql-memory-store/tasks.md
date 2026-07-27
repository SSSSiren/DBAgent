# Implementation Plan

- [ ] 1. Foundation: Data model, config, and storage backends

- [ ] 1.1 Add SQL memory configuration fields to the settings system
  - Add `sql_memory_enabled` toggle (default `False`) and `sql_memory_top_k` retrieval limit (default 5)
  - Add `sql_memory_token_budget` context injection cap (default 1500 chars)
  - Add `sql_memory_sql_max_length` per-record truncation limit (default 2000 chars)
  - Add `sql_memory_ttl_days` auto-expiry (default 90 days)
  - Add `sql_memory_min_similarity` retrieval threshold (default 0.0)
  - Add `sql_memory_pattern_min_records` mining threshold (default 20)
  - Add `sql_memory_scope` mode selector (default `"user"`, options: `"user"` / `"database"` / `"mixed"`)
  - All config fields are readable via the existing settings singleton and support environment variable overrides
  - _Requirements: 6.1, 6.2, 6.3, 6.5_

- [ ] 1.2 Define the storage Protocol, data model, and in-memory implementation
  - Define `SqlMemoryBackend` Protocol with `@runtime_checkable` decorator: `record()`, `search_similar()`, `list_by_user()`, `delete_expired()`, `mine_patterns()`, `initialize()`, `close()`
  - Define the `SqlMemoryRecord` data structure: id, user_id, question, sql_text, sql_truncated, table_names, database_name, schema_id, row_count, column_names, data_preview, execution_status, embedding_json, scope, created_at
  - Implement `InMemorySqlMemoryStore` with dict-based storage, `threading.Lock` for defensive concurrency, per-user LRU eviction (default 100 records per user)
  - `record()` upserts records with dedup on (user_id, sql_text) within the same session; `search_similar()` computes cosine similarity via pure Python and returns top-K sorted by score
  - Observable: `InMemorySqlMemoryStore` passes a basic record → search roundtrip (insert 3 records, search returns them sorted by similarity)
  - _Requirements: 1.1, 1.3, 2.1, 4.1, 4.2, 4.3_

- [ ] 1.3 Implement the SQLite-backed persistent storage
  - Create `sql_memories` table with all columns matching the data model, including composite indexes on `(user_id, database_name)` and `(database_name)` for scope filtering, plus `(created_at)` for TTL cleanup
  - Implement `record()` with UPSERT (INSERT OR REPLACE), storing the full `sql_text` and auto-generating `sql_truncated` as the first 500 characters; if `sql_text` exceeds `sql_max_length` (config), store a mark at the end indicating truncation occurred for context injection purposes
  - Implement `search_similar()` loading all records with non-null embedding_json, computing cosine similarity in pure Python, filtering by scope + min_similarity, returning top-K by score
  - Implement `delete_expired()` removing records where `created_at` is older than `ttl_days`
  - Implement `list_by_user()` returning records for a given user_id with pagination
  - Use WAL mode and `aiosqlite.Row` row factory; share the same database file path as sessions/preferences
  - Observable: `SqliteSqlMemoryStore(":memory:")` initializes without error, record → search roundtrip returns correct results, `delete_expired(0)` clears all records
  - _Requirements: 1.1, 1.2, 1.4, 1.5, 2.1, 2.3, 2.5, 4.1, 4.2, 4.3, 6.4_

- [ ] 2. Wiring: Embedding, factory, and lifecycle management

- [ ] 2.1 Build the embedding client wrapper
  - Create a function that takes a text string and returns a 1536-dim embedding vector (list[float]) using the existing `AsyncOpenAI` client
  - Use the model name from config (`llm_embedding_model`, default `"text-embedding-3-small"`)
  - Wrap the API call in try/except: on failure, log WARN and return `None` (graceful degradation)
  - Support a `cache` parameter (dict-based memoization) to avoid re-embedding identical text within the same session
  - Observable: calling the embedding function with a short text returns a list of 1536 floats; calling with an invalid API key returns `None` without crashing
  - _Requirements: 2.2, 2.4_

- [ ] 2.2 Wire the storage factory, StorageManager lifecycle, and public API exports
  - Create `get_sql_memory_store()` factory function with module-level singleton pattern (matching `get_preference_store()`)
  - Implement `reset_sql_memory_store()` for test isolation
  - Register `sql_memory_store` in `StorageManager`: add constructor parameter, initialize in `initialize()` (after preference_store), close in `close()` (before preference_store)
  - Update `get_storage()` to conditionally create the SQL memory backend based on `storage_backend` and `sql_memory_enabled` config
  - Export `SqlMemoryBackend`, `InMemorySqlMemoryStore`, `SqliteSqlMemoryStore`, `get_sql_memory_store`, `reset_sql_memory_store` from the memory package
  - Observable: `get_storage().sql_memory_store` is `None` when `sql_memory_enabled=False`; is a valid store instance when enabled; `reset_sql_memory_store()` clears the singleton
  - _Requirements: 6.1, 6.5_

- [ ] 3. Core: Recording, retrieval, and context injection hooks

- [ ] 3.1 Implement the post-execution SQL recording hook
  - In the agent execution flow, after the existing preference recording block, add a new `_record_sql_memory()` call gated by `sql_memory_enabled`
  - Extract from `final_payload["tool_calls"]`: SQL text (from `args.sql` or result markdown parsing), table names, schema_id, execution result (row count, column names, data preview first 3 rows)
  - Determine `execution_status`: if tool result is None or contains error → `"error"`; if result row count is 0 → `"empty"`; otherwise → `"success"`
  - Extract the original user question from `initial_state["user_input"]`
  - Skip recording only when: tool_calls is empty or SQL text is empty (still record failed/empty results per requirement 1.2)
  - Check for dedup within current session: if the same user + database + normalized SQL already exists, skip
  - Generate embedding via the embedding client for the concatenated `question + " " + sql_truncated` text; if embedding fails, store with `embedding_json=None` (excluded from search until async backfill)
  - Wrap the entire block in try/except: log ERROR on failure, never block the agent response
  - Observable: after a successful `query_database` tool call, the corresponding SQL record appears in the store; after a failed SQL execution, a record with `execution_status="error"` is stored; after an empty result, `execution_status="empty"` is stored
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [ ] 3.2 Implement the async embedding backfill for null-embedding records
  - When `search_similar()` is called, after retrieving records with non-null embeddings, also check for records with `embedding_json IS NULL` that were stored during an embedding API outage
  - For each null-embedding record, attempt to generate an embedding using the embedding client with the record's `question + " " + sql_truncated` text
  - On success, update the record's `embedding_json` column with the generated embedding, making it available for future searches
  - On failure, leave the record as-is and skip it (no re-attempt until next `search_similar()` call)
  - Limit backfill to at most N records per search call (default 10) to avoid excessive API calls within a single request
  - Wrap the backfill logic in try/except: log WARN on individual record failures; log INFO with backfill count on completion
  - Observable: after a simulated embedding API outage where 5 records were stored with null embeddings, calling `search_similar()` returns results from the backfilled records in subsequent searches
  - _Requirements: 2.5_

- [ ] 3.3 Implement the pre-agent SQL memory retrieval hook
  - In the agent execution flow, before context building, add a new `_retrieve_sql_memories()` call gated by `sql_memory_enabled`
  - Generate query embedding from `initial_state["user_input"]` using the embedding client; if embedding fails, set `_sql_memories` to empty list and continue
  - Determine scope from config: `"user"` → filter by user_id only; `"database"` → filter by database_name only; `"mixed"` → database_name filter with user_id fallback
  - Call `search_similar()` with the query embedding, scope, top_k, and min_similarity from config
  - Store the result list in `session_state["_sql_memories"]`
  - Wrap the entire block in try/except: on any failure, set `_sql_memories = []` and log WARN
  - Observable: before agent execution, `session_state["_sql_memories"]` contains up to top_k records (or empty list); timing metrics show retrieval completes within latency budget
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 4.1, 4.2, 4.3, 4.4, 4.5_

- [ ] 3.4 Add SQL memory context paragraph to the prompt builder
  - Read `session_state.get("_sql_memories")` in the context assembly function; if empty or missing, skip this paragraph entirely
  - Format each memory record as a numbered entry: question, SQL text (truncated to 500 chars), and result summary (row count + column names)
  - Wrap in a labeled section header `[SQL 历史记忆 — 相关查询]` with a brief introductory line explaining these are past successful queries
  - Sort entries by similarity score (highest first, already sorted by `search_similar`)
  - Enforce `sql_memory_token_budget`: measure total paragraph length, truncate from the bottom (lowest similarity) if budget exceeded, log INFO when truncation occurs
  - Filter out any SQL that contains INSERT/UPDATE/DELETE/DDL/DROP/TRUNCATE/ALTER keywords (safety: don't show write operations as examples)
  - Observable: `build_context()` output includes the `[SQL 历史记忆]` paragraph when `_sql_memories` is non-empty; when `_sql_memories` is empty, the output is identical to the current 7-paragraph format; when 5 records exceed the token budget, only the top N fit within budget
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 4. Pattern mining and offline analysis

- [ ] 4.1 Implement the pattern mining query logic
  - Implement `mine_patterns()` on the SQLite store: accept `database_name` and `min_records` threshold
  - If total records for the database < `min_records`, return a result with `total_records` and a message indicating insufficient data
  - Extract top tables: parse `table_names` JSON column, count occurrences per table, return top-10 by frequency
  - Extract top condition patterns: parse `sql_text` for WHERE clauses, normalize literal values to placeholders (e.g., `'paid'` → `?`, `123` → `?`), count normalized patterns, return top-10
  - Extract common JOINs: parse `sql_text` for JOIN/ON clauses, extract table pairs, count occurrences, return top-10
  - Return results as a structured dict with keys: `total_records`, `top_tables`, `top_condition_patterns`, `common_joins`
  - Observable: calling `mine_patterns()` on a store with 30 records returns non-empty `top_tables` and `top_condition_patterns`; calling with `min_records=100` on 30 records returns an "insufficient data" message
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [ ] 5. Validation: Tests and evaluation

- [ ] 5.1 (P) Write unit tests for the storage layer
  - Test both `InMemorySqlMemoryStore` and `SqliteSqlMemoryStore(":memory:")` with identical test cases
  - Test record → search roundtrip: insert 5 records with different SQL patterns, search with a known query, verify top result is the most semantically similar
  - Test scope isolation: insert records for user_a and user_b, verify user_a search only returns user_a records in `"user"` scope
  - Test per-database shared scope: verify `"database"` scope returns records from all users for the same database
  - Test dedup: insert the same SQL twice in the same session, verify only one record exists
  - Test TTL cleanup: insert records with old timestamps, call `delete_expired(1)`, verify only old records removed
  - Test empty store: search on empty store returns `[]`; `list_by_user` on non-existent user returns `[]`
  - Test cosine similarity ordering: insert records with known embeddings, verify search returns them in correct similarity order
  - Observable: all tests pass with `pytest tests/test_sql_memory_store.py -v`
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.3, 4.1, 4.2, 4.3, 6.4_
  - _Boundary: SqlMemoryStore_

- [ ] 5.2 (P) Write integration tests for context injection and hook behavior
  - Test `build_context()` output includes `[SQL 历史记忆]` paragraph when `_sql_memories` is non-empty, with correct formatting
  - Test `build_context()` output is identical to current 7-paragraph format when `_sql_memories` is empty or None
  - Test token budget truncation: provide 5 records totaling 3000 chars, budget=1500, verify output ≤ 1500 chars
  - Test SQL safety filter: provide a memory record containing `INSERT INTO`, verify it is excluded from the context paragraph
  - Test end-to-end hook flow: simulate a full agent execution with a mock store, verify recording hook writes to store and retrieval hook populates session_state
  - Observable: all tests pass with `pytest tests/test_sql_memory_context.py -v`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  - _Boundary: ContextBuilder, SqlMemoryRecorder, SqlMemoryRetriever_

- [ ] 5.3 (P) Generate the twin test case dataset for memory evaluation
  - Read the existing 28 test cases from the evaluation test case file
  - For each TC, create a twin case (TWIN-XXX) that is semantically similar but not identical, using the transformation rules from the design: value substitution, condition inversion, aggregation function swap, time window shift, sort direction reversal, synonym replacement
  - Each twin case must include: natural language question, reference SQL, expected result description, and a mapping back to the original TC
  - Verify twin case quality: the SQL structure (tables, JOINs, aggregation type) must match the original TC; only literal values, function names, or sort directions differ
  - Write all 28 twin cases to the twin cases markdown file following the same format as the original test cases
  - Observable: the twin cases file contains exactly 28 TWIN-XXX entries, each with a question, SQL, and expected result; manual spot-check of 3 cases confirms semantic similarity
  - _Requirements: 7.1_
  - _Boundary: Evaluation_

- [ ] 5.4 Implement the `--compare-sql-memory` evaluation mode
  - Add `--compare-sql-memory` flag and `--twin-cases` parameter to the evaluation CLI
  - Implement Phase 1 (Baseline): run all selected TCs with SQL memory disabled, collect baseline Judge scores and efficiency metrics
  - Implement Phase 2 (Memory seeding): run all twin cases through the agent to populate the SQL memory store; verify all twin SQLs executed successfully
  - Implement Phase 3 (Memory): run all selected TCs again with SQL memory enabled, collect memory-augmented Judge scores and efficiency metrics
  - Implement Phase 4 (Diff): compute per-case and aggregate deltas for SQL correctness, find_table calls, token consumption, and response latency
  - Annotate Recall Hit/Miss per case: compare the twin case's table names and SQL pattern with the current TC's needs; mark as Hit if the retrieved SQL involves the same tables
  - Generate a comparison report (JSON + Markdown) in the same format as the existing HDC comparison report, with Memory Impact metrics as the primary comparison dimensions
  - Observable: `python -m tests.evaluation.cli run --compare-sql-memory --cases tests/docs/test_cases_onedba_evaluation.md --twin-cases tests/docs/sql_memory_twin_cases.md` runs all 4 phases and produces a comparison report
  - _Depends: 3.1, 3.2, 3.3, 3.4, 5.3_
  - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - _Boundary: Evaluation_