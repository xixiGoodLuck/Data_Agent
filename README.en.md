<div align="center">

# InsightOps Agent

**An AI data analysis agent that turns business questions into safe, explainable queries over real data.**

[简体中文](README.md) | **English**

[![CI](https://github.com/ab2956955606-cmyk/Data_Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/ab2956955606-cmyk/Data_Agent/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-18-149ECA?logo=react&logoColor=white)
[![License](https://img.shields.io/badge/License-MIT-2F855A.svg)](LICENSE)

</div>

![InsightOps Agent dashboard in Chinese](docs/assets/readme/dashboard-zh.png)

InsightOps Agent implements the full path from a natural-language question to a trustworthy analytical result: relational schema reasoning, minimum-table selection, SQL generation, deterministic validation, sensitive-data risk assessment, read-only execution, chart planning, grounded insight generation, and a live Agent Trace for every step.

The default Mock mode needs no API key and demonstrates the complete workflow immediately after cloning. Real-model paths support an OpenAI-compatible provider and a one-time DeepSeek key that exists only in page memory.

## The short version

| Evidence | What is implemented |
| --- | --- |
| Real agent workflow | LangGraph `StateGraph`, SQLite checkpoints, `interrupt()`, and `Command(resume=...)` |
| Deterministic security boundary | `sqlglot` AST validation, table and column allowlists, read-only SQLite, timeout, and a 100-row cap |
| Observability | POST-SSE node events, full Trace, Query Logs, Lineage, and Dashboard metrics |
| Data support | Four built-in business datasets, a five-table Commerce model, and bounded CSV ingestion |
| Bilingual product | Chinese and English navigation, states, dates, numbers, dataset copy, and example questions |
| Verification scale | 102 backend tests, 19 frontend tests, 43 built-in Eval cases, and 50 open-data cases |

## More than Text-to-SQL

| Typical demo | InsightOps Agent |
| --- | --- |
| One prompt returns a SQL string | An explicit graph makes state, nodes, branches, and failures observable |
| The full database schema is sent to the model | Tables are selected first; only relevant schema is disclosed |
| A prompt asks the model to be safe | Every model output must pass an independent AST safety gate |
| The database connection can write | Every dataset uses an isolated SQLite file opened read-only with `query_only` |
| Sensitive rows are returned immediately | Row-level sensitive queries persist an approval and interrupt the graph |
| Only the final prose is visible | SQL, chart, rows, insight, lineage, and Trace are returned together |
| SQL strings are compared in tests | Cases run through the real service and results are checked by independent SQLite oracles |

## Product views

### Question, result, and execution trace

This Commerce query runs in keyless Mock mode. The product view keeps the chart, rows, validated SQL, lineage, and real node events in one workflow.

![Ask Data in English with chart, validated SQL, lineage, and Agent Trace](docs/assets/readme/query-trace-en.png)

### Real open data from China and abroad

The registry contains USGS, NOAA, World Bank, and National Bureau of Statistics of China snapshots. Original Chinese headers are mapped to safe ASCII identifiers while JSON-escaped aliases preserve their meaning for the model.

![Real Chinese provincial data and original-to-safe header mapping](docs/assets/readme/real-datasets-zh.png)

## How a question runs

1. The API creates or loads a Conversation and persists a `processing` QueryLog and AgentRun before graph execution.
2. Prompt Guard treats user instructions as untrusted and blocks obvious destructive or policy-bypass intent.
3. LangGraph loads the dataset and trimmed conversation history, then selects the smallest useful set of tables.
4. The model sees only selected schema, foreign keys, redacted samples, and escaped original-header aliases.
5. The LLM returns structured SQL; the safety gate parses its AST and checks statements, tables, columns, complexity, and LIMIT.
6. Low-risk aggregates continue automatically. Row-level salary, name, or email access persists an approval and interrupts the graph.
7. Approved SQL runs only through the selected dataset's read-only connection. Controlled execution errors get at most one repair; safety rejections are never repaired.
8. The system plans a chart from real rows, writes a restrained insight, stores lineage and events, and streams the final result over SSE.

## Architecture

```mermaid
flowchart LR
    UI["React Console<br/>中文 / English"] -->|REST + POST-SSE| API["FastAPI API"]
    API --> QS["Query Service"]
    QS --> LG["LangGraph StateGraph"]
    LG --> LLM["LangChain Model Layer"]
    LG --> SG["SQL Safety Gate"]
    SG --> RISK{"Sensitive risk?"}
    RISK -->|Low| RO["Read-only SQLite Executor"]
    RISK -->|Medium / High| HITL["Approval interrupt"]
    HITL -->|Command resume| RO
    RO --> OUT["Chart + Rows + Insight + Lineage"]
    LG -. checkpoint .-> CP[("Checkpoint DB")]
    API --> META[("Metadata DB")]
    RO --> DATA[("Selected Dataset DB")]
    LG --> OBS["Trace + Logs + Eval"]
```

Metadata, LangGraph checkpoints, and user-queryable data always live in separate SQLite files. See [Architecture](docs/architecture.md) for module ownership, graph nodes, and full data flow.

## Security model

Prompts provide context. They do not grant authority. The real security boundary runs after the model call.

| Boundary | Deterministic control |
| --- | --- |
| SQL syntax | Accept one parseable query; reject multiple statements and comment-hiding attacks |
| Operation type | Allow `SELECT` and read-only CTEs; reject DDL, DML, PRAGMA, ATTACH, and related operations |
| Data scope | Allow known tables and columns from the selected dataset only; reject SQLite internal tables |
| Execution capability | Open SQLite with URI `mode=ro` and set `PRAGMA query_only = ON` |
| Resource limits | Append or clamp LIMIT to 100 and interrupt long queries with a progress handler |
| Sensitive data | Run aggregates directly; persist an approval and pause for row-level names, salaries, or emails |
| Secrets | Never return keys or persist them in events, checkpoints, logs, or evaluation reports |

The complete threat model, bypass tests, and production hardening notes are in [Security](docs/security.md).

## Real DeepSeek and open-data evaluation

The table below contains reproducible snapshots through `2026-07-13`. Every open-data expected answer was computed by independent SQLite oracle SQL; DeepSeek did not generate the ground truth.

| Evaluation | All-metric passes | Result accuracy | Chart accuracy | SQL attacks blocked | Provider / fallback |
| --- | ---: | ---: | ---: | ---: | ---: |
| 43 built-in DeepSeek cases | 35 / 43 | 100% | 81.48% | 100% | DeepSeek / 0% |
| 25 mixed Chinese/English open-data cases | 16 / 25 | 80.95% | 66.67% | 100% | 100% / 0% |
| 25 Chinese-only open-data cases | 14 / 25 | 66.67% | 71.43% | 100% | 100% / 0% |
| Optimized 20 Chinese + 20 English cases | 40 / 40 | 100% | 100% | N/A | DeepSeek / 0% |

The real-data suite covers the USGS past-30-day earthquake feed, NOAA JFK daily weather for 2025, World Bank country indicators from 2015 through 2024, and 31 mainland provincial-level regions from the China Statistical Yearbook 2025. Reports preserve every question, generated SQL, oracle rows, actual rows, chart, fallback flag, latency, and failure reason. Missed targets are not replaced with Mock output.

- [Method, official sources, and snapshot hashes](docs/real-data-evaluation.md)
- [43 built-in DeepSeek results](docs/deepseek-builtin-evaluation-results.md)
- [25 mixed-language open-data results](docs/real-data-evaluation-results.md)
- [25 Chinese-only open-data results](docs/real-data-evaluation-results.zh-CN.md)
- [2026-07-12 real DeepSeek run: 20 Chinese and 20 English cases](docs/deepseek-bilingual-40-results.md) ([full JSON](docs/deepseek-bilingual-40-results.json): 39 succeeded, one remained processing after approval, fallback 0)
- [2026-07-13 optimization report and per-metric gains](docs/deepseek-bilingual-40-optimization-report.en.md) ([full JSON](docs/deepseek-bilingual-40-optimized-results.json), [oracle score](docs/deepseek-bilingual-40-optimized-score.json): 40/40 correct results and charts, fallback 0)

## Run in five minutes

### 1. Backend

Python 3.11+ is required.

```bash
git clone https://github.com/ab2956955606-cmyk/Data_Agent.git
cd Data_Agent/backend
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

Install and start the API:

```bash
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8002
```

### 2. Frontend

Open another terminal:

```bash
cd Data_Agent/frontend
npm ci
npm run dev
```

Open `http://localhost:5175`. Vite proxies `/api` and `/health` to `http://localhost:8002`. The default provider is Mock, so no key is needed.

| URL | Purpose |
| --- | --- |
| `http://localhost:5175` | Web console |
| `http://localhost:8002/health` | Service health |
| `http://localhost:8002/docs` | OpenAPI documentation |

<details>
<summary><strong>Run with Docker Compose</strong></summary>

```bash
docker compose config
docker compose build
docker compose up -d
```

The Web app uses `5175`, the API uses `8002`, and business data is stored in the `insightops_runtime` named volume. Stop the stack with:

```bash
docker compose down
```

</details>

## One-time DeepSeek key

Enter a key at `http://localhost:5175/settings` to use `deepseek-v4-flash` for Ask Data and Eval requests in the current page. Requests explicitly disable thinking mode and cap output at 2,048 tokens.

- The key exists only in React root memory, never in localStorage, sessionStorage, cookies, or IndexedDB.
- Each request sends it through `X-DeepSeek-API-Key`; the backend creates a request-scoped client and removes it in `finally`.
- The key never enters the request body, LangGraph state, checkpoint, metadata, logs, or API responses.
- Refreshing, closing, or leaving the relevant page clears the key. Remote deployments must use HTTPS.
- Mock mode and the complete test suite remain independent of external models and secrets.

For a persistent server-side provider, configure `LLM_PROVIDER=openai_compatible`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_MODEL` in `backend/.env`. Safe defaults are documented in [backend/.env.example](backend/.env.example).

## Shortest API path

Run a normal query:

```bash
curl -X POST http://localhost:8002/api/query \
  -H "Content-Type: application/json" \
  -d '{"dataset_id":"commerce","question":"Which five products generated the most revenue?"}'
```

Live Trace uses `POST /api/query/stream`, parsed by the frontend as fetch-based POST-SSE. Start the server and open `/docs` for the full contracts covering approvals, conversations, datasets, logs, statistics, and Eval.

## Technology

| Layer | Technology |
| --- | --- |
| Agent | LangGraph, LangChain Core, LangChain OpenAI, Pydantic structured output |
| Backend | FastAPI, SQLAlchemy 2, SQLite, pandas, Uvicorn |
| SQL | sqlglot AST, read-only SQLite URI, progress handler |
| Frontend | React 18, strict TypeScript, Vite, React Router, Tailwind CSS |
| Visualization | Recharts with bar, line, area, pie, scatter, number, and table modes |
| Quality | Pytest, Ruff, Vitest, Testing Library, GitHub Actions |
| Delivery | Docker, Nginx, Docker Compose named volume |

## Test and build

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
```

Coverage includes initialization, relational schemas, CSV limits, path traversal, SQL attacks, graph branches, follow-up context, approval resume, SSE ordering, logs and statistics, one-time key lifecycle, and the real Eval service path.

## Read deeper

| Document | What it covers |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | Module boundaries, LangGraph nodes, state, and storage isolation |
| [docs/security.md](docs/security.md) | SQL safety, approvals, threat model, and production limits |
| [docs/demo-script.md](docs/demo-script.md) | Normal queries, multi-table JOINs, blocked attacks, approval resume, and CSV demo |
| [docs/real-data-evaluation.md](docs/real-data-evaluation.md) | Official sources, transformations, oracles, and evaluation method |
| [docs/deepseek-bilingual-40-results.md](docs/deepseek-bilingual-40-results.md) | 2026-07-12 real DeepSeek run with 20 Chinese and 20 English cases |
| [docs/deepseek-bilingual-40-optimization-report.en.md](docs/deepseek-bilingual-40-optimization-report.en.md) | 2026-07-13 before/after accuracy, metric deltas, and complete evidence |
| [IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md) | Implemented behavior, verification commands, dependencies, and known limits |

## Known limits and roadmap

Current limits: the Mock planner is deterministic rather than general natural-language intelligence; the single-process SQLite checkpointer is not a high-concurrency production store; SSE does not yet replay events after a network disconnect; real-model output is nondeterministic, and this 40/40 result covers only the latest attempts for fixed snapshots and predefined questions.

Next priorities: PostgreSQL metadata and checkpoints, multi-tenant identity and purpose-based authorization, a configurable semantic layer, SSE event replay, background Eval jobs, historical model comparison, and route-level frontend code splitting.

## Portfolio notes

Resume-ready bullets:

- Built a full-stack LangGraph data analysis agent with relational table reasoning, POST-SSE traces, conversation memory, and human approval resume.
- Designed a prompt-independent SQL security boundary using sqlglot AST validation, table and column allowlists, and isolated read-only SQLite databases.
- Created 43 behavioral Eval cases and 50 international open-data cases backed by independent SQLite oracles, reporting real result, chart, and security accuracy.

A 60-second interview explanation:

> The point of this project is not to make a model emit one SQL statement. It places an untrusted model inside an observable, interruptible, and verifiable engineering system. LangGraph owns state and approval resume, sqlglot and the read-only executor form the security boundary, SSE exposes real node progress, and independent oracles measure answers. Mock mode keeps the core workflow reproducible for every reviewer, while the DeepSeek reports preserve both successes and failures instead of hiding them behind demo data.

## License

Released under the [MIT License](LICENSE).

---

[简体中文](README.md) | **English**
