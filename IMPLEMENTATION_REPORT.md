# InsightOps Agent 实施报告

日期：2026-07-10（Asia/Shanghai）

## 交付结果

项目已在 Git 仓库根目录完成，默认 `LLM_PROVIDER=mock`，无需外部 API Key。实现包括：

- FastAPI + SQLAlchemy metadata 层，独立 LangGraph checkpoint 和每 dataset 独立 SQLite 文件。
- Sales 600 行、Employees 180 行、Subscriptions 360 行、Commerce 2,110 总行的确定性幂等 seed。
- Commerce 五表真实外键、progressive table/schema disclosure 和敏感 sample 脱敏。
- 受限 CSV multipart ingestion、UUID 路径、列名映射、类型/date metadata、transaction 和失败清理。
- LangChain `ChatPromptTemplate`、Pydantic structured output、Mock/OpenAI-compatible model adapter。
- 真实 LangGraph `StateGraph`、17 个显式节点、SQLite checkpointer、reducer state、interrupt/Command resume。
- sqlglot AST Safety Gate、表列白名单、lineage、LIMIT 100、只读 URI、query-only pragma 和 timeout。
- 敏感查询风险分类、持久 ApprovalRequest、同 thread/namespace 恢复和幂等事件/消息。
- REST + POST-SSE、会话、日志、统计、审批、Eval 和 public settings API。
- React 18 strict TypeScript 控制台及全部八个页面；Recharts 七种输出模式和 table fallback。
- 持久化中英文切换、浏览器语言默认值、状态/日期/数字本地化，以及四个内置数据集的双语名称、说明和示例问题。
- 43 条真实 graph Eval case、66 个后端测试、13 个前端测试。
- 生产 backend image、frontend Node/Nginx multi-stage image、Compose、health checks、CI 和中英文 README。

## 最终命令结果

### Backend

工作目录：`backend/`

| Command | Result |
| --- | --- |
| `python -m pip install -e ".[dev]"` | PASS，editable package 安装成功 |
| `python -m ruff check .` | PASS，`All checks passed!` |
| `python -m ruff format --check .` | PASS，70 files formatted |
| `python -m pytest -q` | PASS，端口更新后最终复验 66 passed in 33.21s |

Pytest 仍显示一条第三方 warning：LangGraph checkpoint 在 import 时提示未来会调整 `allowed_objects` 默认值。当前 `JsonPlusSerializer` 版本的构造函数尚未暴露该参数，功能与测试不受影响。

### Frontend

工作目录：`frontend/`

| Command | Result |
| --- | --- |
| `npm.cmd ci` | PASS，287 packages，0 vulnerabilities |
| `npm.cmd run typecheck` | PASS，strict `tsc --noEmit` |
| `npm.cmd run test -- --run` | PASS，6 files / 13 tests（含语言持久化与内置数据集本地化） |
| `npm.cmd run build` | PASS，2,229 modules，production bundle generated |

Vite build 提示主 JS chunk 约 709 kB（gzip 约 199 kB），属于性能 advisory，不影响构建。Roadmap 已记录 route-level code splitting。

### Docker 与静态配置

| Command | Result |
| --- | --- |
| `docker compose config` | NOT AVAILABLE：本机没有 `docker` command |
| Python/PyYAML + structural assertions | PASS：Compose、两个 Dockerfile、Nginx、CI 静态验证通过 |
| `docker compose build` | 未运行：Docker runtime 不可用 |
| `docker compose up -d` / endpoint smoke / `down` | 未运行：Docker runtime 不可用 |

静态验证确认：backend/frontend build context、8002/5175 ports、named runtime volume、backend health dependency、两侧 healthcheck、Nginx SPA fallback、`/api/` 与 `/health` proxy 均存在且结构一致。

### 浏览器验证

- 端口配置更新后使用默认 `8002/5175` 完成隔离运行，不占用本机其他服务端口。
- `http://127.0.0.1:8002/api/health`：HTTP 200 / status ok；`http://127.0.0.1:5175`：HTTP 200。
- Desktop 1280×720：Dashboard 导航、指标和 panel layout 正常。
- 中文 Dashboard、数据集名称、状态、日期、数据问答标题、四个中文推荐问题和 Schema 面板均正确；切换 EN 后导航、状态、日期和内置数据集内容同步恢复英文。
- 语言选择写入 localStorage，`html lang` 在 `zh-CN` / `en` 间同步切换；当前项目页面无 console error。
- Commerce live query：SSE node events 在 result 前到达；5-row bar chart 有实际 SVG marks；SQL、table、lineage、insight、trace 正常。
- Sensitive employee query：UI 显示 high-risk approval；Reject 通过原 LangGraph checkpoint 恢复并显示 rejected。
- Mobile 390×844：导航 drawer 正常，无 document horizontal overflow，无检测到的 text overflow。
- `/datasets`、`/conversations`、`/logs`、`/approvals`、`/evals`、`/settings` 路由均加载，无 internal error 或 horizontal overflow。

以上服务均在浏览器 QA 时实际运行。本地默认端口为后端 `8002`、前端 `5175`，仍可通过 `frontend/.env` 的 `VITE_API_TARGET` 调整开发代理目标。

## 中间失败与修复

以下失败均未隐藏，并已修复或明确归因：

- 初次 pip/npm 下载被网络 sandbox 阻止；经用户授权后安装成功。
- 本机 Python 报告 user site 但未加入 `sys.path`，导致 `packaging`、NumPy/dateutil、Pytest 不可见；最终安装到 active interpreter path，版本约束恢复为兼容范围。
- 初次 backend suite：62 passed / 4 failed。修复 approval retry contract、Commerce 最小表选择、anonymous SQLite function denylist 和 upload-limit fixture 后为 66/66。
- 初次 frontend suite：11 passed / 1 failed。修正 Testing Library 文本匹配后为 12/12。
- 双语更新新增语言切换测试后，最终 frontend suite 为 6 files / 13 tests 全部通过。
- 浏览器 QA 前的首个 detached launch 因 Windows 环境中同时存在 `Path`/`PATH` 而失败；清理子进程环境中的重复键后启动成功。
- 最终 `npm ci` 首次被仍运行的 Vite/esbuild/Rollup binary lock 拒绝；仅终止本 workspace 的两个 Node child 后，clean install 成功。
- 默认端口调整为 8002/5175，避开本机其他服务端口；Vite 开发代理继续支持 `VITE_API_TARGET` 覆盖。
- Docker command 不存在，因此 Docker build/runtime 不能在本机验证；静态验证通过，CI 会在 Ubuntu Docker runner 上执行 config 和 build。

## 实际依赖版本

本机：Python 3.13.2，Node 24.18.0。

Backend 关键版本：

```text
fastapi==0.116.2
pydantic==2.13.4
SQLAlchemy==2.0.51
langgraph==0.6.11
langgraph-checkpoint-sqlite==2.0.11
langchain-core==0.3.86
langchain-openai==0.3.35
sqlglot==27.29.0
pandas==2.3.3
aiosqlite==0.21.0
uvicorn==0.35.0
pytest==8.4.2
ruff==0.11.13
```

Frontend 关键版本：

```text
react==18.3.1
react-dom==18.3.1
react-router-dom==6.30.4
recharts==2.15.4
lucide-react==0.468.0
typescript==5.9.3
vite==6.4.3
vitest==3.2.7
tailwindcss==3.4.19
@testing-library/react==16.3.2
```

完整 Node dependency tree 固定在 `frontend/package-lock.json`；Python 使用 `backend/pyproject.toml` 的兼容上/下界。

## 最终审计

- Ruff、TypeScript 和测试未发现 unused import、未定义符号或 contract drift。
- TODO/FIXME/placeholder/copied branding scan 无匹配。
- `sk-...` token scan 无匹配；所有 committed `OPENAI_API_KEY` 示例值为空；`.env`、runtime、database、upload 均 ignored。
- `runtime/`、`node_modules/`、`dist/`、cache、egg-info、tsbuildinfo 均不在交付文件列表。
- 前端 `/api` paths 与 FastAPI routers 逐页通过 live browser/API smoke。
- README 命令与最终执行命令一致；没有虚构 screenshot 或 Docker pass。

## 已知限制

- Docker runtime verification unavailable in this environment。
- 最终后台 server restart 被平台 escalation usage limit 拒绝；此前 localhost browser QA 已完成。
- LangGraph dependency emits one pending-deprecation warning described above。
- Frontend main chunk has a non-blocking size warning。
- Mock planner is deterministic and intentionally bounded；真实 provider 质量取决于 configured model。
- 单进程 SQLite metadata/checkpoint 适合 demo/小规模部署，高并发应迁移 PostgreSQL。
