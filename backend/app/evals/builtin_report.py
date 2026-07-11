from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import urlopen

from app.evals.runner import load_eval_cases


def _get_json(url: str) -> Any:
    with urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def collect_builtin_report(api_base_url: str, run_id: str | None = None) -> dict[str, Any]:
    base = api_base_url.rstrip("/")
    runs = _get_json(f"{base}/api/evals")
    selected = next((item for item in runs if run_id is None or item["id"] == run_id), None)
    if selected is None:
        raise RuntimeError("The requested Eval run does not exist.")
    detail = _get_json(f"{base}/api/evals/{quote(selected['id'])}")
    actual_by_id = {item["case_id"]: item for item in detail["cases"]}
    cases = []
    for definition in load_eval_cases():
        actual = actual_by_id[definition.id]
        cases.append(
            {
                "id": definition.id,
                "category": definition.category,
                "dataset_id": definition.dataset_id,
                "question": definition.question,
                "oracle": {
                    "status": definition.expected_status,
                    "tables": definition.expected_tables,
                    "columns_any": definition.expected_columns_any,
                    "chart_type": definition.expected_chart_type,
                    "blocked": definition.should_be_blocked,
                    "approval": definition.should_require_approval,
                    "repair": definition.expected_repair,
                    "result_assertion": definition.result_assertion,
                },
                "actual": actual["actual"],
                "generated_sql": actual["generated_sql"],
                "expected_chart_type": definition.expected_chart_type,
                "actual_chart_type": actual["actual_chart_type"],
                "used_fallback": False if detail["fallback_rate"] == 0 else None,
                "latency_ms": actual["latency_ms"],
                "passed": actual["passed"],
                "failure_reasons": actual["failure_reasons"],
            }
        )
    return {"run": {key: value for key, value in detail.items() if key != "cases"}, "cases": cases}


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _markdown_sql(value: str | None) -> str:
    return "\n".join(line.rstrip() for line in (value or "-- none").splitlines()).strip()


def render_builtin_markdown(report: dict[str, Any]) -> str:
    run = report["run"]
    lines = [
        "# 真实 DeepSeek 内置回归评测结果",
        "",
        f"Eval run: `{run['id']}`; 时间: `{run['created_at']}`",
        "",
        "## 汇总",
        "",
        "| 指标 | 结果 |",
        "| --- | ---: |",
        f"| 用例通过 | {run['passed_cases']}/{run['total_cases']} |",
        f"| 结果准确率 | {run['result_accuracy']:.2f}% |",
        f"| 选表准确率 | {run['table_selection_accuracy']:.2f}% |",
        f"| SQL 安全准确率 | {run['sql_safety_accuracy']:.2f}% |",
        f"| 危险查询拦截率 | {run['dangerous_sql_block_rate']:.2f}% |",
        f"| 图表选择准确率 | {run['chart_selection_accuracy']:.2f}% |",
        f"| fallback | {run['fallback_rate']:.2f}% |",
        f"| 平均耗时 | {run['average_latency_ms']:.2f} ms |",
        "",
        "## 逐条结果",
        "",
    ]
    for item in report["cases"]:
        verdict = "PASS" if item["passed"] else "FAIL"
        lines.extend(
            [
                f"### `{item['id']}` - {verdict}",
                "",
                f"- 数据集: `{item['dataset_id']}`; 类别: `{item['category']}`",
                f"- 问题: {item['question']}",
                f"- Oracle: `{_compact_json(item['oracle'])}`",
                f"- 实际: `{_compact_json(item['actual'])}`",
                f"- 图表: 期望 `{item['expected_chart_type']}`; 实际 `{item['actual_chart_type']}`",
                f"- fallback: `{str(item['used_fallback']).lower()}`; 耗时: `{float(item['latency_ms']):.1f} ms`",
                f"- 失败原因: `{','.join(item['failure_reasons']) or 'none'}`",
                "- 生成 SQL:",
                "",
                "```sql",
                _markdown_sql(item["generated_sql"]),
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect a persisted built-in Eval report.")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8002")
    parser.add_argument("--run-id")
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path("docs/deepseek-builtin-evaluation-results.md"),
    )
    args = parser.parse_args()
    report = collect_builtin_report(args.api_base_url, args.run_id)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(render_builtin_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "run_id": report["run"]["id"],
                "passed_cases": report["run"]["passed_cases"],
                "total_cases": report["run"]["total_cases"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
