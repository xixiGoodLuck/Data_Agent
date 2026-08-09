from __future__ import annotations

import json
import re
from io import BytesIO
from typing import Any

from fastapi.testclient import TestClient
from openpyxl import Workbook

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def contains_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def _visible_analysis_text(body: dict[str, Any]) -> list[str]:
    intent = body["analysis_intent"]
    plan = body["analysis_plan"]
    final = body["final_analysis"]
    texts = [intent["objective"], intent["reason"], plan["objective"]]
    texts.extend(value for step in plan["steps"] for value in (step["question"], step["purpose"]))
    texts.extend(item["result_summary"] for item in body["evidence"])
    texts.extend(item for evidence in body["evidence"] for item in evidence["limitations"])
    critic = body["critic_result"]
    texts.extend(critic["missing_evidence"] + critic["conflicts"] + critic["limitations"])
    if critic["recommended_next_step"]:
        texts.append(critic["recommended_next_step"])
    texts.append(final["executive_summary"])
    texts.extend(item["statement"] for item in final["key_findings"])
    texts.extend(final["limitations"] + final["recommended_actions"])
    decision_events = [
        event for event in body["trace"] if event["event_type"] == "analysis_decision"
    ]
    texts.extend(json.loads(event["output_summary"])["reason"] for event in decision_events)
    return [text for text in texts if text]


def _investigate(client: TestClient, question: str, dataset_id: str = "sales") -> dict[str, Any]:
    response = client.post("/api/query", json={"dataset_id": dataset_id, "question": question})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["analysis_mode"] == "investigative_analysis"
    return body


def _xlsx_dataset(client: TestClient, name: str) -> str:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Analysis"
    sheet.append(["month", "region", "channel", "category", "product", "orders", "revenue"])
    sheet.append(["2026-01", "East", "Online", "Core", "A", 100, 10000])
    sheet.append(["2026-02", "East", "Online", "Core", "A", 99, 8019])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    response = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                f"{name}.xlsx",
                output.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_chinese_investigation_uses_chinese_for_all_visible_analysis_text(
    client: TestClient,
) -> None:
    body = _investigate(client, "为什么最近收入下降?")

    assert body["response_language"] == "zh-CN"
    assert all(contains_cjk(text) for text in _visible_analysis_text(body))
    assert any("total_revenue" in item["sql"] for item in body["evidence"])
    assert "average_order_value" in json.dumps(body["evidence"], ensure_ascii=False)


def test_english_investigation_uses_english_for_all_visible_analysis_text(
    client: TestClient,
) -> None:
    body = _investigate(client, "Why did revenue decline?")

    assert body["response_language"] == "en"
    assert all(not contains_cjk(text) for text in _visible_analysis_text(body))


def test_mixed_question_prefers_chinese(client: TestClient) -> None:
    body = _investigate(client, "Revenue 为什么下降?")

    assert body["response_language"] == "zh-CN"
    assert contains_cjk(body["analysis_intent"]["reason"])


def test_simple_query_insight_follows_question_language(client: TestClient) -> None:
    chinese = client.post(
        "/api/query",
        json={"dataset_id": "commerce", "question": "哪个城市的订单收入最高?"},
    ).json()
    english = client.post(
        "/api/query",
        json={
            "dataset_id": "commerce",
            "question": "Which city has the highest order revenue?",
        },
    ).json()

    assert chinese["response_language"] == "zh-CN"
    assert contains_cjk(chinese["insight"])
    assert english["response_language"] == "en"
    assert not contains_cjk(english["insight"])
    assert "total_revenue" in chinese["sql"]


def test_xlsx_investigation_follows_chinese_and_english(client: TestClient) -> None:
    dataset_id = _xlsx_dataset(client, "response-language")
    try:
        chinese = _investigate(client, "为什么最近收入下降?", dataset_id)
        english = _investigate(client, "Why did revenue decline?", dataset_id)

        assert all(contains_cjk(text) for text in _visible_analysis_text(chinese))
        assert all(not contains_cjk(text) for text in _visible_analysis_text(english))
        assert chinese["response_language"] == "zh-CN"
        assert english["response_language"] == "en"
    finally:
        assert client.delete(f"/api/datasets/{dataset_id}").status_code == 200
