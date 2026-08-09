from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import func, select

from app.core.config import Settings
from app.main import create_app
from app.models import AgentEvent, AgentRun, ApprovalRequest, Conversation, Dataset, QueryLog


def _xlsx_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["name", "value"])
    sheet.append(["qa", 1])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_uploaded_dataset_delete_removes_files_history_and_checkpoints(
    client: TestClient, metadata, test_settings: Settings
) -> None:
    uploaded = client.post(
        "/api/datasets/upload",
        files={"file": ("remove.csv", b"name,value\nqa,1\n", "text/csv")},
    ).json()
    dataset_id = uploaded["id"]
    conversation = client.post(
        "/api/conversations", json={"dataset_id": dataset_id, "title": "Remove dataset"}
    ).json()
    query = client.post(
        "/api/query",
        json={
            "dataset_id": dataset_id,
            "conversation_id": conversation["id"],
            "question": "How many rows are in this dataset?",
        },
    )
    assert query.status_code == 200
    query_log_id = query.json()["query_log_id"]
    with metadata.session() as session:
        approval = ApprovalRequest(
            query_log_id=query_log_id,
            thread_id=conversation["id"],
            risk_level="medium",
            reasons_json="[]",
            sql_preview="SELECT 1",
            selected_tables_json="[]",
            selected_columns_json="[]",
        )
        session.add(approval)
        session.flush()
        approval_id = approval.id

    dataset_path = test_settings.datasets_dir / f"{dataset_id}.sqlite3"
    upload_path = test_settings.uploads_dir / f"{dataset_id}.csv"
    assert dataset_path.exists()
    assert upload_path.exists()
    checkpoint = client.app.state.checkpoint.connection
    assert (
        checkpoint.execute(
            "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (conversation["id"],)
        ).fetchone()[0]
        > 0
    )

    response = client.delete(f"/api/datasets/{dataset_id}")

    assert response.status_code == 200
    assert client.get(f"/api/datasets/{dataset_id}").status_code == 404
    assert not dataset_path.exists()
    assert not upload_path.exists()
    with metadata.session() as session:
        assert session.get(Conversation, conversation["id"]) is None
        assert session.get(QueryLog, query_log_id) is None
        assert (
            session.scalar(
                select(func.count(AgentRun.id)).where(AgentRun.query_log_id == query_log_id)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count(AgentEvent.id)).where(AgentEvent.query_log_id == query_log_id)
            )
            == 0
        )
        assert session.get(ApprovalRequest, approval_id) is None
        assert session.get(Dataset, "sales") is not None
    assert (
        checkpoint.execute(
            "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (conversation["id"],)
        ).fetchone()[0]
        == 0
    )


def test_uploaded_xlsx_delete_removes_original_and_dataset_files(
    client: TestClient, test_settings: Settings
) -> None:
    uploaded = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "remove.xlsx",
                _xlsx_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    ).json()
    dataset_id = uploaded["id"]

    assert client.delete(f"/api/datasets/{dataset_id}").status_code == 200
    assert not (test_settings.datasets_dir / f"{dataset_id}.sqlite3").exists()
    assert not (test_settings.uploads_dir / f"{dataset_id}.xlsx").exists()


def test_builtin_disable_persists_across_restart_and_restore_keeps_upload(
    test_settings: Settings,
) -> None:
    with TestClient(create_app(test_settings)) as client:
        uploaded = client.post(
            "/api/datasets/upload",
            files={"file": ("keep.csv", b"name,value\nqa,1\n", "text/csv")},
        ).json()
        conversation = client.post(
            "/api/conversations",
            json={"dataset_id": "sales", "title": "Disabled builtin history"},
        ).json()
        query = client.post(
            "/api/query",
            json={
                "dataset_id": "sales",
                "conversation_id": conversation["id"],
                "question": "What is total revenue?",
            },
        ).json()
        checkpoint = client.app.state.checkpoint.connection
        assert (
            checkpoint.execute(
                "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (conversation["id"],)
            ).fetchone()[0]
            > 0
        )
        response = client.delete("/api/datasets/sales")
        assert response.status_code == 200
        assert response.json()["status"] == "disabled"
        assert "sales" not in {item["id"] for item in client.get("/api/datasets").json()}
        assert client.get("/api/datasets/sales").status_code == 404
        rejected = client.post(
            "/api/query",
            json={"dataset_id": "sales", "question": "What is total revenue?"},
        )
        assert rejected.status_code == 404
        assert rejected.json()["error"]["type"] == "dataset_not_found"
        assert client.get(f"/api/conversations/{conversation['id']}").status_code == 404
        assert client.get(f"/api/logs/{query['query_log_id']}").status_code == 404
        assert (
            checkpoint.execute(
                "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (conversation["id"],)
            ).fetchone()[0]
            == 0
        )
        assert client.get(f"/api/datasets/{uploaded['id']}").status_code == 200

    with TestClient(create_app(test_settings)) as restarted:
        ids = {item["id"] for item in restarted.get("/api/datasets").json()}
        assert "sales" not in ids
        assert {"employees", "subscriptions", "commerce", uploaded["id"]} <= ids

        restored = restarted.post("/api/datasets/builtins/restore")
        assert restored.status_code == 200
        assert "sales" in restored.json()["dataset_ids"]
        ids = {item["id"] for item in restarted.get("/api/datasets").json()}
        assert {"sales", "employees", "subscriptions", "commerce", uploaded["id"]} <= ids
