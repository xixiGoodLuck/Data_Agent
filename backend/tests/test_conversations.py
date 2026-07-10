from fastapi.testclient import TestClient


def test_conversation_creation_listing_and_messages(client: TestClient) -> None:
    created = client.post(
        "/api/conversations",
        json={"dataset_id": "sales", "title": "Regional review"},
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]
    client.post(
        "/api/query",
        json={
            "dataset_id": "sales",
            "conversation_id": conversation_id,
            "question": "Which region generated the most revenue?",
        },
    )
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
    assert any(item["id"] == conversation_id for item in client.get("/api/conversations").json())


def test_query_without_conversation_creates_one(client: TestClient) -> None:
    result = client.post(
        "/api/query",
        json={"dataset_id": "sales", "question": "What is total revenue?"},
    ).json()
    assert result["conversation_id"]
    assert client.get(f"/api/conversations/{result['conversation_id']}").status_code == 200


def test_follow_up_uses_recent_conversation_context(client: TestClient) -> None:
    first = client.post(
        "/api/query",
        json={"dataset_id": "sales", "question": "Which region had the highest revenue?"},
    ).json()
    second = client.post(
        "/api/query",
        json={
            "dataset_id": "sales",
            "conversation_id": first["conversation_id"],
            "question": "What about only enterprise customers?",
        },
    ).json()
    assert second["status"] == "success"
    assert "Follow-up constraint" in second["rewritten_question"]
    assert "customer_segment = 'Enterprise'" in second["sql"]


def test_conversation_cannot_switch_datasets(client: TestClient) -> None:
    conversation = client.post("/api/conversations", json={"dataset_id": "sales"}).json()
    response = client.post(
        "/api/query",
        json={
            "dataset_id": "employees",
            "conversation_id": conversation["id"],
            "question": "Show headcount by location.",
        },
    )
    assert response.status_code == 409


def test_conversation_deletion_removes_user_facing_messages(client: TestClient) -> None:
    result = client.post(
        "/api/query",
        json={"dataset_id": "sales", "question": "What is total revenue?"},
    ).json()
    conversation_id = result["conversation_id"]
    assert client.delete(f"/api/conversations/{conversation_id}").status_code == 200
    assert client.get(f"/api/conversations/{conversation_id}").status_code == 404
