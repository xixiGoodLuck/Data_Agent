# InsightOps Agent 架构说明

## 边界

InsightOps Agent 分为浏览器、API/服务、Agent 编排、安全执行和存储五层。

- React 只处理交互、SSE 增量状态和可视化，不生成 SQL；可在根组件内存中短暂持有用户主动输入的 DeepSeek Key，但不写入任何浏览器存储。
- FastAPI 路由负责 HTTP contract、输入验证和依赖获取；QueryService 负责运行生命周期。
- LangChain adapter 负责 question rewrite、table selection、SQL generation/repair 和 insight structured output。
- LangGraph 负责显式节点、条件边、checkpoint、interrupt 和 resume；节点只返回 partial state。
- `sqlglot` validator、risk classifier 和 read-only executor 是独立于 LLM 的安全边界。
- metadata、checkpoints 和每个 business dataset 使用不同 SQLite 文件。

## 请求生命周期

1. QueryService 创建或加载 Conversation。
2. 使用唯一 request ID 创建 `QueryLog(status=processing)` 和唯一 `AgentRun`。
3. 用户消息落库，再初始化 `DataAnalysisState`。
4. graph 使用 conversation ID 作为 `thread_id`、request ID 作为 `checkpoint_ns`。
5. 每个节点先持久化并流式发送 start event，再发送领域/complete event。
6. 风险查询创建唯一 ApprovalRequest，然后 `interrupt()`；HTTP 返回 pending response。
7. approve/reject 更新同一 ApprovalRequest，并用 `Command(resume=...)` 恢复相同 namespace。
8. persist/finalize 幂等更新 QueryLog、AgentRun、events 和 assistant message。

临时 DeepSeek 请求使用独立 Header 传递 Key。QueryService 按 request ID 把临时客户端注册到 `LLMClientResolver`，节点只通过 request ID 解析客户端；Key 不进入 `DataAnalysisState` 或 checkpoint。运行结束后 context manager 无条件移除客户端。审批批准会重新要求当前页面内存中的 Key。

Eval 的同步接口和 SSE 接口共用 `EvalRunner.stream()`。Runner 逐 case 消费 QueryService 的节点流，SSE 发出 `progress`、`case_result`、`result` 和 `done`；外层生成器关闭时会显式关闭当前 query generator，因此不会继续创建新的 DeepSeek 请求。真实 provider 的认证、余额、限流、请求格式和服务端错误直接终止评测，不会静默切换 Mock。

## Progressive schema disclosure

`load_dataset_node` 只加载 dataset 名称、路径和可用表名。`select_tables_node` 从 metadata 读取轻量列/外键信息并选择最小表集合。只有 `read_schema_node` 才从选中 dataset 文件读取完整 column/type/key/foreign-key 和最多三条安全 sample。敏感 sample 值会替换为 `[REDACTED]`。

上传 CSV 的 SQL identifier 始终是 ASCII 安全名。`read_schema_node` 会将持久化的原始表头映射附加为 `source_name`，`compact_schema_context` 用 JSON 字符串编码后提供给模型；SQL validator 的 allowed columns 仍只接受安全 identifier。这样中文表头保留语义，又不能改变 SQL 白名单或提示结构。

## Checkpoint 设计

同一会话可能连续提交多个问题。`events` reducer 使用 `operator.add`，因此每个请求使用独立 `checkpoint_ns=request_id`，避免前一 run 的累计事件混入下一 run。所有 namespace 仍归属 `thread_id=conversation_id`；对话语义上下文来自持久消息并受数量限制。审批恢复必须同时复用 thread ID 和 namespace。

## 事件与幂等

AgentEvent ID 由 `run_id + step_index + node_name + event_type` 生成 UUID5。数据库同时有同字段唯一约束。ApprovalRequest 对 query_log_id 唯一；AgentRun 对 query_log_id 唯一；QueryLog request_id 唯一；assistant message 会按 query_log_id 检查后再写入。

## 前端数据流

`useQueryStream` 发起 POST fetch 并逐块交给 `TextDecoder(stream=true)`。SSE parser 保留未完成 block，支持 CRLF、多 data line 和 malformed marker。事件按 ID 或 step/node/type 合成键去重。最终 QueryResponse 与 live trace 合并，不重复展示。

## 扩展点

- 新模型 provider：实现 `BaseLLMClient`。
- 新数据集：写入独立 SQLite 并注册 Dataset schema。
- 新风险规则：扩展 `sql/risk.py`，不修改 model prompt。
- 新图表：扩展 typed ChartConfig、planner、frontend `DynamicChart` 和测试。
- 生产存储：保持 QueryService/graph contract，替换 metadata/checkpoint adapter。
