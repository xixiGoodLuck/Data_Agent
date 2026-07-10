from fastapi.testclient import TestClient


def test_uploaded_dataset_uses_the_same_query_graph(client: TestClient) -> None:
    uploaded = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "scores.csv",
                b"team,score\nNorth,10\nSouth,20\nEast,30\n",
                "text/csv",
            )
        },
    ).json()
    response = client.post(
        "/api/query",
        json={"dataset_id": uploaded["id"], "question": "What is the average score?"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["rows"][0]["average_score"] == 20
