from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_lists_all_built_in_datasets(client: TestClient) -> None:
    response = client.get("/api/datasets")
    assert response.status_code == 200
    datasets = {item["id"]: item for item in response.json()}
    assert set(datasets) == {"sales", "employees", "subscriptions", "commerce"}
    assert datasets["sales"]["row_count"] >= 500
    assert all(item["is_builtin"] for item in datasets.values())


def test_commerce_detail_has_relational_schema_and_redacted_preview(client: TestClient) -> None:
    detail = client.get("/api/datasets/commerce").json()
    assert set(detail["schema"]) == {"customers", "products", "orders", "order_items", "refunds"}
    assert {fk["to_table"] for fk in detail["schema"]["order_items"]["foreign_keys"]} == {
        "orders",
        "products",
    }
    assert detail["preview"][0]["customer_name"] == "[REDACTED]"
    assert detail["preview"][0]["email"] == "[REDACTED]"


def test_dataset_preview_is_limited_to_ten_rows(client: TestClient) -> None:
    detail = client.get("/api/datasets/sales").json()
    assert len(detail["preview"]) == 10
    assert set(detail["preview"][0]) >= {"order_date", "product", "revenue"}


def test_csv_upload_sanitizes_duplicate_and_blank_columns(client: TestClient) -> None:
    csv = b"Name,Name,,Amount,Event Date\nAlpha,A,one,12.5,2025-01-01\nBeta,B,two,9,2025-01-02\n"
    response = client.post(
        "/api/datasets/upload",
        files={"file": ("metrics.csv", csv, "text/csv")},
    )
    assert response.status_code == 201
    body = response.json()
    mapping = body["column_mapping"]
    assert [item["sanitized"] for item in mapping] == [
        "name",
        "name_2",
        "column_3",
        "amount",
        "event_date",
    ]
    assert body["schema"]["data"]["columns"][3]["type"] == "REAL"
    assert body["schema"]["data"]["columns"][4]["date_like"] is True
    assert len(body["preview"]) == 2


def test_csv_upload_supports_utf8_sig(client: TestClient) -> None:
    content = "城市,收入\n上海,100\n北京,80\n".encode("utf-8-sig")
    response = client.post(
        "/api/datasets/upload",
        files={"file": ("cities.csv", content, "text/csv")},
    )
    assert response.status_code == 201
    assert response.json()["row_count"] == 2


def test_csv_upload_rejects_invalid_inputs(client: TestClient) -> None:
    cases = [
        ("empty.csv", b""),
        ("no-data.csv", b"name,value\n"),
        ("no-header.csv", b"1,2\n3,4\n"),
        ("wrong.txt", b"name,value\na,1\n"),
        ("ragged.csv", b"name,value\na,1,extra\n"),
    ]
    for filename, content in cases:
        response = client.post(
            "/api/datasets/upload",
            files={"file": (filename, content, "text/csv")},
        )
        assert response.status_code in {400, 413}, (filename, response.text)
        assert response.json()["error"]["type"] == "invalid_upload"


def test_csv_upload_enforces_byte_and_column_limits(tmp_path: Path) -> None:
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        max_upload_bytes=1024,
        max_upload_columns=2,
        log_level="WARNING",
    )
    with TestClient(create_app(settings)) as limited:
        too_large = limited.post(
            "/api/datasets/upload",
            files={"file": ("large.csv", b"name,value\n" + b"x,1\n" * 300, "text/csv")},
        )
        assert too_large.status_code == 413
        too_wide = limited.post(
            "/api/datasets/upload",
            files={"file": ("wide.csv", b"a,b,c\n1,2,3\n", "text/csv")},
        )
        assert too_wide.status_code == 400


def test_builtin_datasets_can_be_disabled_and_uploaded_datasets_deleted(
    client: TestClient,
) -> None:
    disabled = client.delete("/api/datasets/sales")
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
    assert client.get("/api/datasets/sales").status_code == 404
    assert client.post("/api/datasets/builtins/restore").status_code == 200
    assert client.get("/api/datasets/sales").status_code == 200
    uploaded = client.post(
        "/api/datasets/upload",
        files={"file": ("delete.csv", b"name,value\na,1\n", "text/csv")},
    ).json()
    assert client.delete(f"/api/datasets/{uploaded['id']}").status_code == 200
    assert client.get(f"/api/datasets/{uploaded['id']}").status_code == 404


def test_upload_filename_cannot_escape_runtime(client: TestClient, test_settings: Settings) -> None:
    response = client.post(
        "/api/datasets/upload",
        files={"file": ("../../outside.csv", b"name,value\na,1\n", "text/csv")},
    )
    assert response.status_code == 201
    dataset_id = response.json()["id"]
    assert (test_settings.datasets_dir / f"{dataset_id}.sqlite3").exists()
    assert not (test_settings.runtime_dir.parent / "outside.csv").exists()
