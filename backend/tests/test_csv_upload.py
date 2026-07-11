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


def test_uploaded_chinese_headers_reach_model_as_escaped_aliases(
    client: TestClient, monkeypatch
) -> None:
    uploaded = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "china.csv",
                "地区,地区生产总值_亿元\n北京,49843.1\n上海,53926.7\n".encode(),
                "text/csv",
            )
        },
    ).json()
    assert uploaded["column_mapping"] == [
        {"original": "地区", "sanitized": "column_1"},
        {"original": "地区生产总值_亿元", "sanitized": "column_2"},
    ]
    catalogs: list[dict] = []
    contexts: list[str] = []
    llm = client.app.state.llm_resolver.default_client
    original_select = llm.select_tables
    original = llm.generate_sql

    def capture_select(dataset_id, question, catalog):
        catalogs.append(catalog)
        return original_select(dataset_id, question, catalog)

    def capture(*args):
        contexts.append(args[-1])
        return original(*args)

    monkeypatch.setattr(llm, "select_tables", capture_select)
    monkeypatch.setattr(llm, "generate_sql", capture)

    response = client.post(
        "/api/query",
        json={
            "dataset_id": uploaded["id"],
            "question": "How many rows are in this dataset?",
        },
    )

    assert response.status_code == 200
    assert catalogs[0]["data"]["columns"][:2] == [
        {"name": "column_1", "type": "TEXT", "source_name": "地区"},
        {"name": "column_2", "type": "REAL", "source_name": "地区生产总值_亿元"},
    ]
    assert contexts
    assert 'column_1 TEXT [source_name="地区"]' in contexts[0]
    assert 'column_2 REAL [source_name="地区生产总值_亿元"]' in contexts[0]
