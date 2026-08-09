from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import (
    AgentEvent,
    AgentRun,
    ApprovalRequest,
    Conversation,
    ConversationMessage,
    Dataset,
    QueryLog,
)


def _create_query(client: TestClient, conversation_id: str, question: str) -> dict:
    response = client.post(
        "/api/query",
        json={
            "dataset_id": "sales",
            "conversation_id": conversation_id,
            "question": question,
        },
    )
    assert response.status_code == 200
    return response.json()


def _add_approval(metadata, query_log_id: str, thread_id: str) -> str:
    with metadata.session() as session:
        approval = ApprovalRequest(
            query_log_id=query_log_id,
            thread_id=thread_id,
            risk_level="medium",
            reasons_json="[]",
            sql_preview="SELECT 1",
            selected_tables_json="[]",
            selected_columns_json="[]",
        )
        session.add(approval)
        session.flush()
        return approval.id


def test_delete_conversation_removes_only_its_complete_history(
    client: TestClient, metadata
) -> None:
    first = client.post(
        "/api/conversations", json={"dataset_id": "sales", "title": "Delete me"}
    ).json()
    second = client.post(
        "/api/conversations", json={"dataset_id": "sales", "title": "Keep me"}
    ).json()
    first_result = _create_query(client, first["id"], "What is total revenue?")
    second_result = _create_query(client, second["id"], "Which region has the most revenue?")
    approval_id = _add_approval(metadata, first_result["query_log_id"], first["id"])

    checkpoint = client.app.state.checkpoint.connection
    assert (
        checkpoint.execute(
            "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (first["id"],)
        ).fetchone()[0]
        > 0
    )

    response = client.delete(f"/api/conversations/{first['id']}")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted", "conversation_id": first["id"]}
    with metadata.session() as session:
        assert session.get(Conversation, first["id"]) is None
        assert (
            session.scalar(
                select(func.count(ConversationMessage.id)).where(
                    ConversationMessage.conversation_id == first["id"]
                )
            )
            == 0
        )
        assert session.get(QueryLog, first_result["query_log_id"]) is None
        assert (
            session.scalar(
                select(func.count(AgentRun.id)).where(
                    AgentRun.query_log_id == first_result["query_log_id"]
                )
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count(AgentEvent.id)).where(
                    AgentEvent.query_log_id == first_result["query_log_id"]
                )
            )
            == 0
        )
        assert session.get(ApprovalRequest, approval_id) is None
        assert session.get(Conversation, second["id"]) is not None
        assert session.get(QueryLog, second_result["query_log_id"]) is not None
        assert session.get(Dataset, "sales") is not None
    assert (
        checkpoint.execute(
            "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (first["id"],)
        ).fetchone()[0]
        == 0
    )


def test_delete_query_log_removes_trace_but_keeps_conversation_and_dataset(
    client: TestClient, metadata
) -> None:
    conversation = client.post(
        "/api/conversations", json={"dataset_id": "sales", "title": "Keep thread"}
    ).json()
    first_result = _create_query(client, conversation["id"], "What is total revenue?")
    second_result = _create_query(client, conversation["id"], "Show revenue by region.")
    approval_id = _add_approval(metadata, first_result["query_log_id"], conversation["id"])

    response = client.delete(f"/api/logs/{first_result['query_log_id']}")

    assert response.status_code == 200
    assert response.json() == {
        "status": "deleted",
        "query_log_id": first_result["query_log_id"],
    }
    with metadata.session() as session:
        assert session.get(QueryLog, first_result["query_log_id"]) is None
        assert (
            session.scalar(
                select(func.count(AgentRun.id)).where(
                    AgentRun.query_log_id == first_result["query_log_id"]
                )
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count(AgentEvent.id)).where(
                    AgentEvent.query_log_id == first_result["query_log_id"]
                )
            )
            == 0
        )
        assert session.get(ApprovalRequest, approval_id) is None
        assert session.get(QueryLog, second_result["query_log_id"]) is not None
        assert session.get(Conversation, conversation["id"]) is not None
        assert session.get(Dataset, "sales") is not None


def test_delete_missing_query_log_returns_404(client: TestClient) -> None:
    response = client.delete("/api/logs/missing-query-log")

    assert response.status_code == 404
