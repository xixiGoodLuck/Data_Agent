from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import AgentEvent, AgentRun, ApprovalRequest, ConversationMessage, QueryLog


def sensitive_query(client: TestClient) -> dict:
    return client.post(
        "/api/query",
        json={
            "dataset_id": "employees",
            "question": "List employee names and individual salary values.",
        },
    ).json()


def test_sensitive_query_interrupts_and_persists_approval(client: TestClient, metadata) -> None:
    pending = sensitive_query(client)
    assert pending["status"] == "pending_approval"
    assert pending["approval"]["risk_level"] == "high"
    listed = client.get("/api/approvals?status=pending").json()
    assert [item["id"] for item in listed] == [pending["approval"]["id"]]
    with metadata.session() as session:
        approval = session.get(ApprovalRequest, pending["approval"]["id"])
        query_log = session.get(QueryLog, pending["query_log_id"])
        run = session.scalar(select(AgentRun).where(AgentRun.query_log_id == query_log.id))
        assert approval.thread_id == pending["conversation_id"]
        assert run.thread_id == approval.thread_id


def test_approve_resumes_same_run_without_duplicate_side_effects(
    client: TestClient, metadata
) -> None:
    pending = sensitive_query(client)
    approval_id = pending["approval"]["id"]
    resumed = client.post(f"/api/approvals/{approval_id}/approve", json={"note": "Reviewed"})
    assert resumed.status_code == 200
    body = resumed.json()
    assert body["status"] == "success"
    assert body["query_log_id"] == pending["query_log_id"]
    assert body["row_count"] == 100
    with metadata.session() as session:
        approval = session.get(ApprovalRequest, approval_id)
        assert approval.status == "approved"
        assert approval.decision_note == "Reviewed"
        assert (
            session.scalar(
                select(func.count(ConversationMessage.id)).where(
                    ConversationMessage.query_log_id == body["query_log_id"],
                    ConversationMessage.role == "assistant",
                )
            )
            == 1
        )
        event_ids = list(
            session.scalars(
                select(AgentEvent.id).where(AgentEvent.query_log_id == body["query_log_id"])
            )
        )
        assert len(event_ids) == len(set(event_ids))


def test_reject_resumes_same_thread_and_finishes_rejected(client: TestClient) -> None:
    pending = sensitive_query(client)
    response = client.post(
        f"/api/approvals/{pending['approval']['id']}/reject",
        json={"note": "Not required"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["query_log_id"] == pending["query_log_id"]


def test_approval_cannot_be_decided_twice(client: TestClient) -> None:
    pending = sensitive_query(client)
    approval_id = pending["approval"]["id"]
    assert client.post(f"/api/approvals/{approval_id}/reject", json={}).status_code == 200
    assert client.post(f"/api/approvals/{approval_id}/approve", json={}).status_code == 409


def test_aggregate_salary_query_does_not_require_approval(client: TestClient) -> None:
    response = client.post(
        "/api/query",
        json={"dataset_id": "employees", "question": "What is the average salary by department?"},
    )
    assert response.json()["status"] == "success"
    assert response.json()["risk_level"] == "low"
