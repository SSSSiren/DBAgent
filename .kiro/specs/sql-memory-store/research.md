# Research & Design Decisions

## Summary
- **Feature**: sql-memory-store
- **Discovery Scope**: Extension (light discovery)
- **Key Findings**:
  - Project uses `AsyncOpenAI` client at `https://dwai-data.dewu-inc.com/openai/v1` — same client supports `client.embeddings.create()` if proxy serves `/v1/embeddings`
  - No existing vector storage infrastructure; pure Python cosine similarity is sufficient for ≤1000 records
  - `query_preferences.sql_patterns` column already exists but is unused — a natural extension point
  - Existing `PreferenceBackend` Protocol + factory + StorageManager pattern is the exact template to replicate

## Research Log

### Embedding Model Selection
- **Context**: Need embedding model for semantic similarity search on Chinese SQL queries
- **Sources Consulted**: OpenAI API docs, `app/agent/runner.py` (client initialization), `app/config.py` (Settings)
- **Findings**: Existing `AsyncOpenAI` client at base_url `https://dwai-data.dewu-inc.com/openai/v1` supports `client.embeddings.create()`. Model `text-embedding-3-small` (1536 dims) is the standard choice.
- **Implications**: Add `llm_embedding_model: str = "text-embedding-3-small"` to Settings. Verify proxy supports `/v1/embeddings` endpoint before release.

### Vector Storage Approach
- **Context**: Need to store embeddings alongside SQL records and compute cosine similarity for top-K retrieval
- **Sources Consulted**: Project `requirements.txt`, `sqlite-vec` docs, python math stdlib
- **Findings**: No existing vector dependencies. `sqlite-vec` requires C extension compilation. For ≤1000 records, brute-force Python cosine similarity takes milliseconds.
- **Implications**: Store embeddings as JSON text in SQLite column. Compute similarity in pure Python using `math.sqrt`. Zero new dependencies.

### Storage Abstraction Pattern
- **Context**: Need to follow existing project patterns for the new storage backend
- **Sources Consulted**: `app/memory/preferences.py` (full lifecycle), `app/memory/manager.py` (StorageManager), `app/memory/__init__.py` (exports)
- **Findings**: Pattern is Protocol → two implementations (InMemory + Sqlite) → module-level singleton factory → StorageManager registration → __init__.py export. Factory selects backend based on `storage_backend` config.
- **Implications**: Follow this exact 7-step pattern. `SqliteSqlMemoryStore` uses same DB file as sessions/preferences (shared `storage_file_path`).

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Extend PreferenceBackend | Add SQL text storage to existing `query_preferences` table via `sql_patterns` column | Minimal schema change | Mixes concerns (table frequency vs SQL history), `sql_patterns` column not designed for full SQL+result storage | Rejected: violates single responsibility |
| New independent SqlMemoryBackend | Separate table + Protocol + singleton, follows PreferenceBackend pattern | Clean boundary, independent lifecycle | More code, but all following established patterns | **Selected** |
| External vector DB | Use Chroma/FAISS/Milvus for vector storage | Good for large scale | Heavy dependency, operational complexity, overkill for current scale | Rejected: premature scaling |

## Design Decisions

### Decision: Embedding as JSON in SQLite + Pure Python Cosine Similarity
- **Context**: Need semantic search at ≤1000 record scale with no new infrastructure
- **Alternatives Considered**:
  1. `sqlite-vec` extension — adds C dependency, overkill for scale
  2. External vector DB — operational complexity, premature scaling
  3. Numpy BLOB — heavy dependency for simple math
- **Selected Approach**: Embeddings stored as `TEXT` JSON arrays in SQLite. Cosine similarity computed in pure Python (`sum(a*b) / sqrt(sum(a²)) * sqrt(sum(b²))`). Brute-force scan of 1000 records × 1536 dims ≈ single-digit milliseconds.
- **Rationale**: Zero new dependencies, trivially maintainable, sufficient for current scale. Migration path to `sqlite-vec` is straightforward if scale exceeds 5000+ records.
- **Trade-offs**: No ANN (approximate nearest neighbor) optimization. Brute-force becomes slower at very large scales. Acceptable for current requirements.
- **Follow-up**: Monitor query latency; if search exceeds 50ms at 5000+ records, migrate to `sqlite-vec`.

### Decision: Follow PreferenceBackend Pattern for SqlMemoryBackend
- **Context**: Need storage abstraction for SQL memory with test isolation
- **Alternatives Considered**:
  1. Direct SQLite only (no Protocol) — simpler but no test isolation
  2. Repository pattern with dependency injection — more flexible but inconsistent with existing code
- **Selected Approach**: Protocol + two implementations (InMemory/Sqlite) + module-level singleton factory + StorageManager registration. Exact same pattern as `PreferenceBackend`.
- **Rationale**: Consistency with existing codebase. Test isolation via `InMemorySqlMemoryStore` or `SqliteSqlMemoryStore(":memory:")`. Runtime selection via `storage_backend` config.
- **Trade-offs**: Module-level singleton is not ideal for dependency injection but is the established project convention.

### Decision: SQL Memory Scope via Query-Time Filter
- **Context**: R4 requires per-user and per-database mixed scope
- **Alternatives Considered**:
  1. Separate tables per scope — complex schema, hard to switch at runtime
  2. Single table with scope column — simple, flexible
- **Selected Approach**: Single `sql_memories` table with `user_id` and `database_name` columns. Per-user mode: `WHERE user_id = ?`. Per-database mode: `WHERE database_name = ?`. Mixed mode: `WHERE database_name = ? OR (user_id = ? AND scope = 'user')`. A `scope` column defaults to `'user'`.
- **Rationale**: Simplest schema, runtime-switchable via query filter, no data migration on scope change.

## Risks & Mitigations
- Embedding API availability not yet verified — add graceful fallback (return empty list), verify in integration test
- Pure Python similarity may be slow at scale — add latency metric, define migration threshold (5000 records)
- Scope hot-reload may cause inconsistency between old/new records — document that scope changes apply immediately, existing records keep their original scope
- Token budget overshoot from long SQL examples — enforce hard truncation (1500 chars total) in context formatter

## References
- OpenAI Embeddings API: https://platform.openai.com/docs/guides/embeddings
- sqlite-vec: https://github.com/asg017/sqlite-vec
- Project storage pattern: `app/memory/preferences.py` lines 255-265 (schema), 310-364 (UPSERT), 33-41 (Protocol)
