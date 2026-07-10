from __future__ import annotations

from fastapi.testclient import TestClient


def query(client: TestClient, dataset: str, question: str) -> dict:
    return client.post("/api/query", json={"dataset_id": dataset, "question": question}).json()


def test_logs_persist_result_and_lineage(client: TestClient) -> None:
    result = query(client, "commerce", "Which five products generated the most revenue?")
    listed = client.get("/api/logs?run_mode=interactive").json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == result["query_log_id"]
    detail = client.get(f"/api/logs/{result['query_log_id']}").json()
    assert detail["result"]["rows"] == result["rows"]
    assert set(detail["lineage"]["tables"]) == {"products", "order_items"}


def test_log_filters_by_dataset_status_and_mode(client: TestClient) -> None:
    query(client, "sales", "What is total revenue?")
    query(client, "sales", "Drop table sales.")
    query(client, "subscriptions", "What is total MRR by plan?")
    success = client.get("/api/logs?dataset_id=sales&status=success").json()
    blocked = client.get("/api/logs?dataset_id=sales&status=blocked").json()
    assert success["total"] == 1
    assert blocked["total"] == 1


def test_default_stats_exclude_eval_and_test_runs(client: TestClient) -> None:
    service = client.app.state.query_service
    service.run_query(
        dataset_id="sales",
        question="What is total revenue?",
        run_mode="eval",
    )
    service.run_query(
        dataset_id="sales",
        question="What is total revenue?",
        run_mode="test",
    )
    query(client, "sales", "What is total revenue?")
    stats = client.get("/api/stats/overview").json()
    assert stats["total_queries"] == 1
    assert stats["success_count"] == 1
    assert stats["success_rate"] == 100


def test_stats_calculate_status_average_and_p95(client: TestClient) -> None:
    query(client, "sales", "What is total revenue?")
    query(client, "sales", "Show monthly revenue trend.")
    query(client, "sales", "Drop table sales.")
    stats = client.get("/api/stats/overview").json()
    assert stats["total_queries"] == 3
    assert stats["success_count"] == 2
    assert stats["blocked_count"] == 1
    assert stats["average_latency_ms"] >= 0
    assert stats["p95_latency_ms"] >= stats["average_latency_ms"]
    assert stats["chart_breakdown"]


def test_pending_approval_appears_in_dashboard_stats(client: TestClient) -> None:
    query(client, "employees", "List employee names and individual salary values.")
    stats = client.get("/api/stats/overview").json()
    assert stats["pending_approval_count"] == 1
