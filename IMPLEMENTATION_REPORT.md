# InsightOps Agent 实施报告

日期：2026-07-11（Asia/Shanghai）

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
- Settings 页面提供一次性 DeepSeek API Key：仅保存在当前 React 内存中，刷新或关闭页面即清除；后端按请求创建并销毁临时模型客户端，不写入日志、数据库、graph state 或 checkpoint。
- 43 条真实 graph Eval case、25 条中外开放数据 case、91 个后端测试、19 个前端测试。
- DeepSeek V4 Flash 非思考模式、2,048-token 上限、provider-compatible function calling、请求级密钥转发和逐 case SSE Eval。
- USGS、NOAA、World Bank 与国家统计局独立 SQLite oracle、来源/哈希清单，以及两份逐条脱敏结果报告。
- 生产 backend image、frontend Node/Nginx multi-stage image、Compose、health checks、CI 和中英文 README。

## 最终命令结果

### Backend

工作目录：`backend/`

| Command | Result |
| --- | --- |
| `python -m pip install -e ".[dev]"` | PASS，editable package 安装成功 |
| `python -m ruff check .` | PASS，`All checks passed!` |
| `python -m ruff format --check .` | PASS，78 files already formatted |
| `python -m pytest -q` | PASS，91 passed in 34.99s |

Pytest 仍显示一条第三方 warning：LangGraph checkpoint 在 import 时提示未来会调整 `allowed_objects` 默认值。当前 `JsonPlusSerializer` 版本的构造函数尚未暴露该参数，功能与测试不受影响。

### Frontend

工作目录：`frontend/`

| Command | Result |
| --- | --- |
| `npm.cmd ci` | PASS，287 packages，0 vulnerabilities |
| `npm.cmd run typecheck` | PASS，strict `tsc --noEmit` |
| `npm.cmd run test -- --run` | PASS，9 files / 19 tests（含临时密钥生命周期、Eval SSE/取消、Settings 控件和双语功能） |
| `npm.cmd run build` | PASS，2,230 modules，production bundle generated |

Vite build 提示主 JS chunk 717.54 kB（gzip 201.18 kB），属于性能 advisory，不影响构建。Roadmap 已记录 route-level code splitting。

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
- Settings 临时 DeepSeek Key：默认掩码，显示/隐藏与清除按钮正常；SPA 路由切换后仍保留，刷新页面后立即清空；桌面和移动布局均无溢出。
- 临时密钥通过专用请求头传给后端；真实 DeepSeek 预检返回 535，与 USGS oracle 一致，provider 为 DeepSeek 且 fallback=false。
- 真实内置 Eval 为 35/43；结果/选表/SQL 安全准确率均 100%，危险查询拦截率 100%，图表准确率 81.48%，fallback 0%。
- 25 条开放数据为 16/25 全指标通过；结果准确率 80.95%，SQL 安全拦截率 100%，DeepSeek provider 100%，fallback 0%，图表准确率 66.67% 未达 80% 目标。
- 国家统计局专项 6 条分析中 5 条结果与图表正确；中英混合出生率用例因数据无显式年份列而要求澄清，危险 DELETE 被安全层拦截。
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
- 临时密钥前端定向测试首次因 Testing Library cleanup 隔离不足失败；增加显式 cleanup 后，4 个新增前端测试全部通过。
- 临时 DeepSeek 后端新增隔离测试，覆盖请求级清理、审批续传重新提供密钥、持久化与响应无密钥泄露；该阶段 backend suite 为 69/69。
- 临时密钥阶段 frontend suite 为 8 files / 17 tests；加入 Eval 流式进度/取消后最终为 9 files / 19 tests。
- DeepSeek 预检首次被网络 sandbox 阻断；后端以获准网络权限重启后确认不是认证或余额问题。
- LangChain 默认 `json_schema` 导致 DeepSeek 400；显式改为受支持的 function calling 并新增回归测试后预检通过。
- 中文别名最初仅进入 SQL schema context，选表 catalog 仍显示 `column_*`；补齐 JSON 转义别名后，国家统计局前三条由 clarification 变为 success。
- 浏览器 QA 前的首个 detached launch 因 Windows 环境中同时存在 `Path`/`PATH` 而失败；清理子进程环境中的重复键后启动成功。
- 最终 `npm ci` 首次被仍运行的 Vite/esbuild/Rollup binary lock 拒绝；仅终止本 workspace 的两个 Node child 后，clean install 成功。
- 默认端口调整为 8002/5175，避开本机其他服务端口；Vite 开发代理继续支持 `VITE_API_TARGET` 覆盖。
- Docker command 不存在，因此 Docker build/runtime 不能在本机验证；静态验证通过，CI 会在 Ubuntu Docker runner 上执行 config 和 build。
- 本轮 Compose 静态断言首次因 PowerShell 展开 Nginx 配置中的 `$uri` 而失败；改用不含 shell 变量的结构断言后通过，配置文件未改动。

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
- 密钥扫描仅发现明确标注的测试占位值，没有真实 API Key；所有 committed `OPENAI_API_KEY` 示例值为空；`.env`、runtime、database、upload 均 ignored。
- 临时 DeepSeek Key 没有 localStorage、sessionStorage、cookie 或 IndexedDB 写入路径，也不进入 graph state、checkpoint、metadata 数据库或日志；刷新后状态为“未设置”，通用真实 Key 模式扫描为 0 命中。
- 四个外部上传数据集、关联查询日志、审批记录与 `C:\tmp` 原始文件/快照均已清理；来源、哈希、规范和脱敏报告保留在 Git。
- 逐条结果见 `docs/deepseek-builtin-evaluation-results.md` 与 `docs/real-data-evaluation-results.md`。
- `runtime/`、`node_modules/`、`dist/`、cache、egg-info、tsbuildinfo 均不在交付文件列表。
- 前端 `/api` paths 与 FastAPI routers 逐页通过 live browser/API smoke。
- README 命令与最终执行命令一致；没有虚构 screenshot 或 Docker pass。

## 已知限制

- Docker runtime verification unavailable in this environment。
- 外部数据图表选择准确率为 66.67%，未达到计划的 80% 目标；报告保留全部失败，不以 Mock 替代。
- LangGraph dependency emits one pending-deprecation warning described above。
- Frontend main chunk has a non-blocking size warning。
- Mock planner is deterministic and intentionally bounded；真实 provider 质量取决于 configured model。
- 单进程 SQLite metadata/checkpoint 适合 demo/小规模部署，高并发应迁移 PostgreSQL。
