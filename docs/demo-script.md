# InsightOps Agent 演示脚本

## 1. Sales 普通聚合

选择 Sales，提问：`Which region generated the most revenue?`。展示 table selection、validated SQL、bar chart、grounded insight、lineage 和 Trace。

## 2. Commerce 多表 Join

选择 Commerce，提问：`Which five products generated the most revenue?`。强调只选择 `products` 和 `order_items`，然后检查 JOIN 和 LIMIT 5。

## 3. 月度趋势

继续提问：`Show monthly revenue trend.`。展示 `strftime('%Y-%m', ...)`、line chart 和 24 个月结果。

## 4. 危险 SQL 拒绝

提问：`Drop table sales.`。展示 Prompt Guard blocked 状态，确认 Trace 中没有 execute node，dataset 仍可查询。

## 5. 薪资聚合放行

选择 Employees，提问：`What is the average salary by department?`。展示 risk=low、自动执行和无个人姓名。

## 6. 原始薪资触发审批

提问：`List employee names and individual salary values.`。展示 high risk、原因、SQL preview 和 graph pending interrupt。

## 7. 审批与 graph resume

到 Approvals 页面填写 note 并 Approve。回到结果/日志，展示同一 query_log、conversation/thread、`approval_resumed` event 和 100 行上限。也可新建一次并 Reject 演示 rejected 分支。

## 8. CSV 上传

在 Datasets 上传包含重复/空列名的 UTF-8 CSV。展示 sanitized mapping、类型/date-like metadata、预览，然后在 Ask Data 对上传 dataset 提问平均值。

## 9. 多轮追问

Sales 首问：`Which region had the highest revenue?`，同一 Conversation 追问：`What about only enterprise customers?`。在日志检查 rewritten question 和 Enterprise filter。

## 10. Eval 运行

进入 Eval Center 点击 Run Eval。展示 43 case、危险 SQL block、approval、clarification、repair、chart、latency 指标，再回 Dashboard 确认 interactive query 数未被 Eval 污染。
