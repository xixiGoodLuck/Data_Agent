# InsightOps Agent Delivery Checklist

## 1. Repository and dependency setup

- [x] Work at the fresh Git repository root with no nested project directory.
- [x] Add project-level `AGENTS.md` with architecture, verification, security, no-copy, and API-contract rules.
- [x] Add this complete implementation checklist and update it throughout delivery.
- [x] Add pinned compatible Python 3.11+ dependencies and development tools in `backend/pyproject.toml`.
- [x] Add React 18, strict TypeScript, Vite, Router, Tailwind, Recharts, Vitest, and Testing Library dependencies.
- [x] Generate and commit `frontend/package-lock.json`.
- [x] Add safe environment examples and ignore secrets/runtime artifacts.

## 2. Metadata database and dataset storage

- [x] Keep metadata, checkpoints, and each business dataset in separate SQLite files under ignored `runtime/`.
- [x] Implement metadata models for datasets, conversations/messages, query logs, agent runs/events, approvals, eval runs/cases.
- [x] Use public UUID strings, timestamps, constraints, cascades, unique request IDs, and idempotent event keys.
- [x] Initialize metadata and checkpoint storage idempotently.
- [x] Compile the real LangGraph graph with a SQLite checkpointer and close it during application shutdown.
- [x] Restrict dataset resolution to the configured dataset directory and deny metadata/checkpoint/cross-dataset access.

## 3. Built-in and uploaded datasets

- [x] Deterministically seed idempotent Sales data with at least 500 rows.
- [x] Deterministically seed idempotent Employees data with at least 150 rows and sensitive name/salary metadata.
- [x] Deterministically seed idempotent SaaS Subscriptions data with at least 300 rows and sensitive customer-name metadata.
- [x] Deterministically seed coherent relational Commerce customers/products/orders/order-items/refunds data and foreign keys.
- [x] Mark Commerce customer names/emails as sensitive and expose useful suggested questions.
- [x] Implement progressive schema inspection with keys, foreign keys, at most three safe samples, and a stable hash.
- [x] Implement CSV multipart upload with 10 MB, 100,000-row, and 100-column limits.
- [x] Accept UTF-8/UTF-8-SIG `.csv`; reject empty, headerless, malformed, or data-less files.
- [x] Generate UUID storage names, sanitize/uniquify blank and duplicate columns, preserve mappings, and infer conservative types/date metadata.
- [x] Use transactional ingestion, remove partial files on failure, return schema/mapping/preview, and query uploads through the same graph.
- [x] Permit deletion only for uploaded datasets and resist filename/path traversal.

## 4. LangChain LLM layer

- [x] Use `ChatPromptTemplate`, Pydantic structured outputs, provider abstraction, and retry-safe parsing.
- [x] Implement `BaseLLMClient`, deterministic `MockLLMClient`, and `ChatOpenAI`-based compatible provider.
- [x] Configure provider, key, base URL, model, timeout, retry, and zero temperature safely through environment variables.
- [x] Implement bounded structured-output recovery and deterministic fallbacks without ever executing unvalidated text.
- [x] Make mock mode understand English/Chinese analytics, all built-in datasets, joins, aggregates, ranking, trends, rates, comparisons, and eval cases.
- [x] Generate mock insights from actual result values.

## 5. Real LangGraph workflow and persistence

- [x] Implement reducer-backed JSON-serializable `DataAnalysisState`.
- [x] Implement all 17 required explicit graph nodes with partial-state returns.
- [x] Implement conditional branches for prompt blocking, missing datasets, clarification, SQL blocking, risk, approval, execution, and one repair.
- [x] Use real `StateGraph`, `interrupt()`, and `Command(resume=...)` on the same checkpointed conversation thread.
- [x] Use conversation IDs as `thread_id` and bound loaded history size.
- [x] Create QueryLog/AgentRun before execution and make request, event, approval, resume, and final persistence idempotent.
- [x] Persist structured node/run/SQL/approval/chart/insight events without secrets or large row payloads.
- [x] Persist user/assistant messages and support context-aware follow-up questions.

## 6. SQL safety, risk, repair, and execution

- [x] Implement contextual prompt-injection/data-modification guard without blocking ordinary phrases such as revenue drops.
- [x] Validate one read-only SELECT/CTE/UNION AST with `sqlglot` in SQLite dialect.
- [x] Block DDL/DML, PRAGMA, ATTACH, comments, multiple statements, extensions, unknown/internal/other-dataset tables, invalid columns, and excessive complexity.
- [x] Normalize harmless trailing semicolons and append/clamp LIMIT 100 while preserving smaller limits.
- [x] Extract tables/columns and stable lineage from validated SQL.
- [x] Classify aggregate analytics as low risk and sensitive/raw/broad exports as medium/high risk.
- [x] Require human approval for raw employee/customer identifiers, salaries, emails, `SELECT *`, and broad row-level output.
- [x] Allow aggregate salary analytics without approval.
- [x] Execute only normalized approved SQL through SQLite read-only URI mode with query-only pragma, progress timeout, 100-row cap, sanitized errors, and closed connections.
- [x] Allow at most one repair for repairable database errors and route repaired SQL through validation/risk again.

## 7. API, streaming, conversations, and approvals

- [x] Implement `/health` and `/api/health` with sanitized component/provider/version status.
- [x] Implement dataset list/detail/upload/delete APIs with metadata, schema, mapping, preview, and suggestions.
- [x] Implement conversation create/list/detail/delete APIs and persistent messages.
- [x] Implement `/api/query` stable success/blocked/clarification/approval/error responses and request idempotency.
- [x] Implement fetch-compatible POST `/api/query/stream` SSE with live graph progress, result/error/done events, event IDs, and disconnect cleanup.
- [x] Implement approval list/detail/approve/reject APIs that resume the interrupted graph thread without duplicate effects.
- [x] Implement paginated/filterable logs, log detail, and persisted event endpoints.
- [x] Implement default-interactive stats with counts/rates, fallback, average/p95 latency, charts, datasets, recent queries, and failures.
- [x] Implement eval run/list/latest/detail APIs.
- [x] Implement safe public settings API with no secrets.
- [x] Return stable sanitized domain error types and configure safe local CORS.

## 8. Frontend

- [x] Build a restrained responsive SaaS shell with React Router and typed relative-URL API client.
- [x] Build Dashboard with all required operational metrics, distributions, datasets, and recent/failure activity.
- [x] Build Ask Data with conversations, dataset/schema/examples, live trace, approval state, SQL safety, lineage, chart/table, insight, retry/cancel/new actions.
- [x] Build Datasets with relational schema, mapping, preview, drag/drop upload progress, suggestions, and upload-only deletion.
- [x] Build Conversations with list, messages, timestamps, and deletion.
- [x] Build Query Logs with filters, core fields, SQL, and trace/lineage detail.
- [x] Build Approvals with pending/history risk details, SQL, reasons, notes, approve, and reject.
- [x] Build Eval Center with run action, loading/progress state, metrics, failures, expected/actual, latency, and category filtering.
- [x] Build Settings with safe provider/model/limits and environment setup guidance; never store browser API keys.
- [x] Implement POST fetch-SSE parsing for partial UTF-8 chunks, abort/unmount/cancel, malformed data, final/approval states, and trace deduplication.
- [x] Implement Recharts bar/line/area/pie/scatter, scalar number, responsive tooltips/formatting, and robust table fallback.
- [x] Implement polished loading, empty, blocked, pending approval, success, and error states without hardcoded result data.

## 9. Evaluation system

- [x] Add at least 30 meaningful cases spanning aggregations, joins, ranking, trends, rates, scalar/table/chart outputs, safety attacks, approvals, clarification, follow-up, repair, and empty results.
- [x] Execute eval cases through the actual graph/service in mock mode with `run_mode=eval`.
- [x] Evaluate behavior and results rather than raw SQL string equality.
- [x] Persist run metrics and per-case results/failure reasons including repair and latency metrics.
- [x] Exclude eval/test runs from default Dashboard statistics.

## 10. Backend and frontend tests

- [x] Test health, idempotent metadata initialization, and idempotent seeding.
- [x] Test built-in/relational datasets, preview, CSV edge cases/limits/deletion/path safety.
- [x] Test SELECT/CTE/JOIN normalization and all dangerous/unknown/cross-dataset/internal SQL rejections.
- [x] Test graph normal/join/table-selection/clarification/guard/block/repair/final/trace/events/idempotency paths.
- [x] Test conversations, follow-up context, messages, and deletion.
- [x] Test approval interrupt, persistence, same-thread approve/reject resume, idempotency, and aggregate-sensitive allowance.
- [x] Test live SSE order/events/result/approval/error behavior.
- [x] Test log persistence/filters and interactive-only average/p95 stats.
- [x] Test 30+ case eval execution, metrics, failure persistence, and stats isolation.
- [x] Test frontend SSE parser, chart fallback, response parsing, trace deduplication, and approval rendering.

## 11. Docker, CI, documentation, and final review

- [x] Add production backend image and frontend Node-build/Nginx-runtime image.
- [x] Configure Nginx SPA fallback plus `/api/` and `/health` backend proxies.
- [x] Configure Compose ports 8000/5173, mock mode, persistent runtime volume, health checks, dependency health, and production-only mounts.
- [x] Add Vite `/api` and `/health` development proxies.
- [x] Add GitHub Actions backend, frontend, and Docker validation jobs using mock mode and no secrets.
- [x] Add MIT License.
- [x] Write Chinese-first README with positioning, differentiators, features, diagrams, safety, memory, trace, examples, setup, tests, limits, roadmap, resume bullets, and interview guide.
- [x] Write architecture, security, and ten-step demo documentation.
- [x] Run backend install, Ruff check/format check, and Pytest; fix all failures.
- [x] Run frontend clean install, typecheck, Vitest, and production build; fix all failures.
- [ ] Validate Compose with the Docker CLI and build/start/smoke-test/stop services (blocked: Docker is not installed; static validation passed).
- [x] Inspect status/diff and search for TODO, FIXME, placeholders, secrets, copied branding, dead code, API/type drift, and documentation mismatch.
- [x] Record exact dependency versions, commands/results, features, limitations, and runtime verification in `IMPLEMENTATION_REPORT.md`.
