# 安全模型

## 保护目标

- 业务 dataset 不能读取/修改 metadata、checkpoint、另一 dataset 或任意文件。
- Model/prompt 不能绕过确定性 SQL 校验。
- 敏感行级输出必须被识别并在执行前中断审批。
- API、Trace 和错误不能泄露 Key、完整路径、stack trace 或大结果 payload。
- 上传内容不能控制文件路径、应用配置或 SQL table name。

## 输入防护

Prompt guard 使用上下文正则检测 system prompt 泄露、绕过校验、原始数据库命令、filesystem 和应用日志访问。规则要求命令上下文，例如 `drop table`，不会把 “drop in revenue” 当作 DDL。

CSV 仅接受 `.csv` 和 UTF-8/UTF-8-SIG。服务先检查 bytes，再限制行列；每行必须与 header 等宽。数据库和原始上传使用服务端 UUID。展示名称只取 basename 并移除控制字符。

## SQL 防护链

1. 扫描 string literal 之外的 comment/semicolon。
2. `sqlglot.parse(..., read="sqlite")` 必须得到单一 query AST。
3. 根节点必须是 Select/SetOperation，AST 不得含 write/admin 节点。
4. function denylist 阻止 extension/file helper。
5. Table 必须属于 graph-selected tables；拒绝 catalog/db qualifier、`sqlite_` 和 `pragma_`。
6. Column 必须属于 selected schema；CTE alias 和 select alias 受控处理。
7. AST 重写 LIMIT，输出 normalized SQLite SQL 和 lineage。

## 执行防护

- Path resolve 后 parent 必须严格等于 configured datasets directory。
- metadata/checkpoint path 始终拒绝。
- 使用 `file:<URI>?mode=ro` 打开连接，再执行 `PRAGMA query_only = ON`。
- SQLite progress handler 超时返回 `query_timeout`。
- 只执行 validator 输出的 normalized SQL，最多 fetch 100 行。
- 所有 connection 显式关闭；异常只返回 sanitized type/message。

## 敏感分类

Schema column metadata 标记：

- `employees.employee_name`, `employees.salary`
- `subscriptions.customer_name`
- `customers.customer_name`, `customers.email`

聚合函数包裹的敏感列不会自动触发行级审批。非聚合敏感列、直接 `SELECT *` 或大范围非聚合结果触发 medium；email 或多个敏感标识组合升级 high。

## Approval 风险

Approval 是应用层 human-in-the-loop，不是用户认证。当前实现适合单组织演示；生产系统必须增加身份、角色、审批者授权、审计保留策略和 CSRF/SSO 边界。

## Secrets 与日志

- `.env`、runtime、database、upload、node_modules 和 build output 均 gitignored。
- `/api/settings/public` 只返回 provider 名、非敏感 model 名和限制。
- 一次性 DeepSeek Key 只通过 `X-DeepSeek-API-Key` Header 进入单次请求内存；不写 body、graph state、checkpoint、metadata、AgentEvent、QueryLog 或响应。
- 前端不使用 localStorage、sessionStorage、Cookie 或 IndexedDB 保存 Key，并在 `pagehide`/刷新/关闭时清空内存状态。
- 临时客户端按 request ID 隔离，并在 graph 成功、失败、中断或客户端断开后的 `finally` 中移除。
- AgentEvent summary 截断到 500 字符，节点不写 rows 或 schema sensitive sample。
- 全局异常 handler 记录 server-side stack，但客户端只收到 `internal_error`。

## 剩余风险

- SQLite 与本地文件权限依赖容器/主机边界。
- 复杂只读查询可能消耗资源；已有 AST node cap、LIMIT 和 progress timeout，但生产仍需资源配额。
- 结构化 LLM fallback 可能降低语义准确率；任何 fallback SQL 仍经过完整 validator/risk。
- 上传数据本身可能包含敏感值；当前自动敏感识别只覆盖内置 metadata，生产应接入分类器或人工登记。
- 远程 HTTP 部署无法保护临时 Key 的传输；任何非 localhost 环境都必须终止 HTTPS，并评估 DeepSeek 的数据处理与保留条款。
