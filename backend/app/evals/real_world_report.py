from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import urlopen

from app.evals.real_world import REAL_WORLD_MANIFEST_PATH, load_real_world_manifest

ABSOLUTE_TOLERANCE = 0.02
RELATIVE_TOLERANCE = 1e-12


def _get_json(url: str) -> Any:
    with urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _percent(numerator: int, denominator: int) -> float:
    return round(numerator * 100 / denominator, 2) if denominator else 0.0


def _values_equal(expected: Any, actual: Any) -> bool:
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if not isinstance(actual, (int, float)) or isinstance(actual, bool):
            return False
        return math.isclose(
            float(expected),
            float(actual),
            rel_tol=RELATIVE_TOLERANCE,
            abs_tol=ABSOLUTE_TOLERANCE,
        )
    return expected == actual


def compare_rows(expected: list[list[Any]], actual: list[list[Any]]) -> bool:
    if len(expected) != len(actual):
        return False
    return all(
        len(expected_row) == len(actual_row)
        and all(
            _values_equal(expected_value, actual_value)
            for expected_value, actual_value in zip(expected_row, actual_row, strict=True)
        )
        for expected_row, actual_row in zip(expected, actual, strict=True)
    )


def _actual_rows(detail: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    result = detail.get("result") or {}
    columns = result.get("columns") or []
    rows = result.get("rows") or []
    return columns, [[row.get(column) for column in columns] for row in rows]


def assess_case(
    oracle: dict[str, Any],
    detail: dict[str, Any],
    approval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    expected_status = oracle["expected_status"]
    actual_status = detail.get("status")
    status_ok = actual_status == expected_status
    actual_columns, actual_rows = _actual_rows(detail)
    result_ok = status_ok
    if expected_status == "success":
        result_ok = status_ok and compare_rows(oracle["rows"], actual_rows)
    chart_ok = (
        detail.get("chart_type") == oracle["expected_chart_type"]
        if expected_status == "success"
        else True
    )
    provider_ok = detail.get("llm_provider") == "deepseek"
    fallback_ok = not bool(detail.get("used_fallback"))
    result_payload = detail.get("result") or {}
    failure_detail: Any = detail.get("error_message") or result_payload.get(
        "clarification_question"
    )
    if approval and approval.get("reasons"):
        failure_detail = approval["reasons"]
    failures = []
    if not status_ok:
        failures.append("status")
    elif expected_status == "success" and not result_ok:
        failures.append("rows")
    if not chart_ok:
        failures.append("chart")
    if not provider_ok:
        failures.append("provider")
    if not fallback_ok:
        failures.append("fallback")
    return {
        "id": oracle["id"],
        "dataset_id": oracle["dataset_id"],
        "language": oracle["language"],
        "question": oracle["question"],
        "expected_status": expected_status,
        "actual_status": actual_status,
        "generated_sql": detail.get("generated_sql"),
        "validated_sql": detail.get("normalized_sql"),
        "oracle_columns": oracle["columns"],
        "oracle_rows": oracle["rows"],
        "actual_columns": actual_columns,
        "actual_rows": actual_rows,
        "expected_chart_type": oracle["expected_chart_type"],
        "actual_chart_type": detail.get("chart_type"),
        "provider": detail.get("llm_provider"),
        "used_fallback": bool(detail.get("used_fallback")),
        "latency_ms": detail.get("execution_time_ms") or 0.0,
        "error_type": detail.get("error_type"),
        "error_message": detail.get("error_message"),
        "status_ok": status_ok,
        "result_ok": result_ok,
        "chart_ok": chart_ok,
        "passed": not failures,
        "failure_reasons": failures,
        "failure_detail": failure_detail,
        "query_log_id": detail.get("id"),
        "created_at": str(detail.get("created_at")),
    }


def collect_report(
    api_base_url: str,
    manifest: dict[str, Any],
    oracle_payload: dict[str, Any],
) -> dict[str, Any]:
    base = api_base_url.rstrip("/")
    registered = _get_json(f"{base}/api/datasets")
    approvals_payload = _get_json(f"{base}/api/approvals")
    approvals = (
        approvals_payload
        if isinstance(approvals_payload, list)
        else approvals_payload.get("items", [])
    )
    approvals_by_log = {item["query_log_id"]: item for item in approvals}
    registered_by_name = {item["name"]: item["id"] for item in registered}
    dataset_ids = {}
    for definition in manifest["datasets"]:
        upload_name = Path(definition["prepared_filename"]).stem
        if upload_name not in registered_by_name:
            raise RuntimeError(f"Uploaded dataset is missing: {upload_name}")
        dataset_ids[definition["id"]] = registered_by_name[upload_name]

    oracle_by_id = {item["id"]: item for item in oracle_payload["cases"]}
    cases = []
    for definition in manifest["cases"]:
        dataset_id = dataset_ids[definition["dataset_id"]]
        query = urlencode({"dataset_id": dataset_id, "run_mode": "interactive", "page_size": 100})
        logs = _get_json(f"{base}/api/logs?{query}")["items"]
        selected = next(
            (item for item in logs if item["question"] == definition["question"]),
            None,
        )
        if selected is None:
            raise RuntimeError(f"Query log is missing for case: {definition['id']}")
        detail = _get_json(f"{base}/api/logs/{quote(selected['id'])}")
        cases.append(
            assess_case(
                oracle_by_id[definition["id"]],
                detail,
                approvals_by_log.get(detail["id"]),
            )
        )

    analysis_cases = [item for item in cases if item["expected_status"] == "success"]
    safety_cases = [item for item in cases if item["expected_status"] == "blocked"]
    metrics = {
        "total_cases": len(cases),
        "passed_cases": sum(item["passed"] for item in cases),
        "result_accuracy": _percent(
            sum(item["result_ok"] for item in analysis_cases), len(analysis_cases)
        ),
        "chart_selection_accuracy": _percent(
            sum(item["chart_ok"] for item in analysis_cases), len(analysis_cases)
        ),
        "sql_safety_block_rate": _percent(
            sum(item["status_ok"] for item in safety_cases), len(safety_cases)
        ),
        "fallback_rate": _percent(sum(item["used_fallback"] for item in cases), len(cases)),
        "deepseek_provider_rate": _percent(
            sum(item["provider"] == "deepseek" for item in cases), len(cases)
        ),
        "average_latency_ms": round(
            sum(float(item["latency_ms"]) for item in cases) / len(cases), 2
        ),
    }
    return {
        "version": manifest["version"],
        "generated_at": datetime.now(UTC).isoformat(),
        "api_base_url": base,
        "numeric_tolerance": {
            "absolute": ABSOLUTE_TOLERANCE,
            "relative": RELATIVE_TOLERANCE,
        },
        "metrics": metrics,
        "cases": cases,
    }


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _markdown_sql(value: str | None) -> str:
    return "\n".join(line.rstrip() for line in (value or "-- none").splitlines()).strip()


def render_markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        "# 真实 DeepSeek 开放数据评测结果",
        "",
        f"生成时间: `{report['generated_at']}`",
        "",
        "## 汇总",
        "",
        "| 指标 | 结果 |",
        "| --- | ---: |",
        f"| 用例通过 | {metrics['passed_cases']}/{metrics['total_cases']} |",
        f"| 真实数据结果准确率 | {metrics['result_accuracy']:.2f}% |",
        f"| 图表选择准确率 | {metrics['chart_selection_accuracy']:.2f}% |",
        f"| SQL 安全拦截率 | {metrics['sql_safety_block_rate']:.2f}% |",
        f"| DeepSeek provider | {metrics['deepseek_provider_rate']:.2f}% |",
        f"| fallback | {metrics['fallback_rate']:.2f}% |",
        f"| 平均耗时 | {metrics['average_latency_ms']:.2f} ms |",
        "",
        "数值比较使用绝对容差 `0.02`、相对容差 `1e-12`; 行与列按 oracle 顺序比较。",
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
                f"- 数据集: `{item['dataset_id']}`; 语言: `{item['language']}`",
                f"- 问题: {item['question']}",
                f"- 状态: 期望 `{item['expected_status']}`; 实际 `{item['actual_status']}`",
                f"- 图表: 期望 `{item['expected_chart_type']}`; 实际 `{item['actual_chart_type']}`",
                f"- Provider: `{item['provider']}`; fallback: `{str(item['used_fallback']).lower()}`; 耗时: `{float(item['latency_ms']):.1f} ms`",
                f"- Oracle: `{_compact_json({'columns': item['oracle_columns'], 'rows': item['oracle_rows']})}`",
                f"- 实际: `{_compact_json({'columns': item['actual_columns'], 'rows': item['actual_rows']})}`",
                f"- 失败原因: `{','.join(item['failure_reasons']) or 'none'}`",
                f"- 失败详情: `{_compact_json(item['failure_detail'])}`",
                "- 生成 SQL:",
                "",
                "```sql",
                _markdown_sql(item["generated_sql"]),
                "```",
                "",
                "- 校验后 SQL:",
                "",
                "```sql",
                _markdown_sql(item["validated_sql"]),
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect the real-data evaluation report.")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8002")
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=REAL_WORLD_MANIFEST_PATH,
    )
    parser.add_argument(
        "--oracle-path",
        type=Path,
        default=Path("C:/tmp/insightops-real-eval/real_world_oracles.json"),
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("C:/tmp/insightops-real-eval/real_world_results.json"),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path("docs/real-data-evaluation-results.md"),
    )
    args = parser.parse_args()
    manifest = load_real_world_manifest(args.manifest_path)
    oracle = json.loads(args.oracle_path.read_text(encoding="utf-8"))
    report = collect_report(args.api_base_url, manifest, oracle)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
