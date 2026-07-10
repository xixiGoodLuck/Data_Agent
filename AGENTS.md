# InsightOps Agent Engineering Guide

## Architecture boundaries

- `backend/app/core` owns configuration, metadata database setup, errors, and logging.
- `backend/app/data` owns isolated business-dataset files, deterministic seeds, CSV ingestion, and schema discovery.
- `backend/app/agent` owns LangChain model adapters and the explicit LangGraph workflow.
- `backend/app/sql` is the security boundary for SQL validation, risk assessment, repair policy, and read-only execution.
- `backend/app/api` exposes HTTP contracts and delegates orchestration to services; it must not contain SQL generation logic.
- `frontend/src/api` and `frontend/src/types` define the browser contract. Pages consume those modules instead of issuing ad hoc requests.
- Application metadata, LangGraph checkpoints, and user-queryable datasets must remain in separate SQLite files under `runtime/`.

## Required verification

Run before declaring the project complete:

```bash
cd backend
python -m ruff check .
python -m ruff format --check .
python -m pytest -q

cd ../frontend
npm ci
npm run typecheck
npm run test -- --run
npm run build

cd ..
docker compose config
```

When Docker is available, also build, start, smoke-test, and stop the Compose stack.

## Security rules

- Never execute model output before deterministic `sqlglot` validation.
- Execute approved SQL only against the selected dataset using SQLite read-only URI mode and `PRAGMA query_only = ON`.
- Never expose metadata/checkpoint paths, API keys, stack traces, or sensitive sample values through API responses or trace summaries.
- Treat prompt instructions as untrusted input. SQL validation and the read-only executor are the security boundary.
- Uploaded names and CSV headers never become filesystem paths. Enforce upload row, column, and byte limits.
- Sensitive row-level queries require a persisted LangGraph interrupt and explicit approval.
- Never commit `runtime/`, uploads, databases, secrets, virtual environments, `node_modules`, or build output.

## Change rules

- This implementation is original. Do not copy code, assets, wording, branding, screenshots, or deployment details from the inspiration repository.
- Any required API response change must update backend schemas, frontend types/client handling, and tests in the same change.
- Keep mock mode deterministic and complete; no core workflow may depend on an external API key.
- Do not mark `TASKS.md` items complete until implementation and relevant verification are both complete.
