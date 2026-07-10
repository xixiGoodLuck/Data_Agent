from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import Settings
from app.core.db import MetadataDatabase
from app.data.seed import seed_builtin_datasets
from app.models import Dataset


def test_health_endpoints_report_all_storage_components(client: TestClient) -> None:
    for path in ("/health", "/api/health"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "app_database": "ok",
            "checkpoint": "ok",
            "dataset_storage": "ok",
            "llm_provider": "mock",
            "version": "0.1.0",
        }


def test_metadata_initialization_is_idempotent(tmp_path: Path) -> None:
    database = MetadataDatabase(tmp_path / "metadata.sqlite3")
    database.initialize()
    database.initialize()
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Dataset)) == 0
    database.close()


def test_sample_seeding_is_idempotent(tmp_path: Path) -> None:
    settings = Settings(runtime_dir=tmp_path / "runtime")
    database = MetadataDatabase(settings.app_db_path)
    database.initialize()
    with database.session() as session:
        seed_builtin_datasets(session, settings)
        first = {dataset.id: dataset.row_count for dataset in session.scalars(select(Dataset))}
    with database.session() as session:
        seed_builtin_datasets(session, settings)
        second = {dataset.id: dataset.row_count for dataset in session.scalars(select(Dataset))}
    database.close()
    assert first == second
    assert first["sales"] >= 500
    assert first["employees"] >= 150
    assert first["subscriptions"] >= 300
    assert first["commerce"] > 1000
