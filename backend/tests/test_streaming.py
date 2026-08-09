from __future__ import annotations

import re

from fastapi.testclient import TestClient


def event_names(stream_text: str) -> list[str]:
    return re.findall(r"^event: ([^\r\n]+)", stream_text, flags=re.MULTILINE)


def test_sse_stream_orders_live_events_before_result(client: TestClient) -> None:
    response = client.post(
        "/api/query/stream",
        json={"dataset_id": "sales", "question": "Which region generated the most revenue?"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    names = event_names(response.text)
    assert names[0] == "run_started"
    assert "node" in names
    assert names[-2:] == ["result", "done"]
    assert response.text.index("generate_sql_node") < response.text.index("event: result")


def test_sse_contains_persisted_step_ids_without_duplicates(client: TestClient) -> None:
    response = client.post(
        "/api/query/stream",
        json={"dataset_id": "subscriptions", "question": "What is total MRR by plan?"},
    )
    ids = re.findall(r"^id: ([^\r\n]+)", response.text, flags=re.MULTILINE)
    assert ids
    assert len(ids) == len(set(ids))


def test_sse_streams_structured_investigation_progress(client: TestClient) -> None:
    response = client.post(
        "/api/query/stream",
        json={"dataset_id": "sales", "question": "Why did revenue decline?"},
    )
    names = event_names(response.text)
    for expected in (
        "analysis_step_started",
        "evidence_created",
        "analysis_decision",
        "final_synthesis_started",
        "final_synthesis_completed",
        "final_grounding_validated",
        "supporting_charts_selected",
    ):
        assert expected in names
    assert names.index("evidence_created") < names.index("final_synthesis_started")


def test_sse_emits_approval_interruption(client: TestClient) -> None:
    response = client.post(
        "/api/query/stream",
        json={
            "dataset_id": "employees",
            "question": "List employee names and individual salary values.",
        },
    )
    names = event_names(response.text)
    assert "approval_required" in names
    assert names[-2:] == ["result", "done"]
    assert '"status": "pending_approval"' in response.text


def test_sse_turns_internal_stream_failure_into_sanitized_error(
    client: TestClient, monkeypatch
) -> None:
    graph = client.app.state.query_service.graph

    def fail_stream(*_args, **_kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(graph, "stream", fail_stream)
    response = client.post(
        "/api/query/stream",
        json={"dataset_id": "sales", "question": "What is total revenue?"},
    )
    assert event_names(response.text)[-2:] == ["error", "done"]
    assert "secret internal detail" not in response.text
    assert "internal_error" in response.text
