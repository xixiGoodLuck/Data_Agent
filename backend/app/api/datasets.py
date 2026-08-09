from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import delete

from app.api.dependencies import get_metadata, get_settings
from app.core.config import Settings
from app.core.db import MetadataDatabase
from app.core.errors import AppError
from app.data.csv_loader import delete_uploaded_dataset, ingest_tabular_file
from app.data.registry import dataset_detail, dataset_summary, list_datasets
from app.models import Conversation, Dataset, QueryLog
from app.schemas.dataset import DatasetDetail, DatasetSummary

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.get("", response_model=list[DatasetSummary])
def datasets(metadata: MetadataDatabase = Depends(get_metadata)) -> list[dict]:
    with metadata.session() as session:
        return [dataset_summary(dataset) for dataset in list_datasets(session)]


@router.get("/{dataset_id}", response_model=DatasetDetail)
def dataset_by_id(
    dataset_id: str,
    metadata: MetadataDatabase = Depends(get_metadata),
    settings: Settings = Depends(get_settings),
) -> dict:
    with metadata.session() as session:
        dataset = session.get(Dataset, dataset_id)
        if dataset is None:
            raise AppError(
                "dataset_not_found", "The selected dataset does not exist.", status_code=404
            )
        return dataset_detail(dataset, settings)


@router.post("/upload", response_model=DatasetDetail, status_code=201)
async def upload_dataset(
    file: UploadFile = File(...),
    metadata: MetadataDatabase = Depends(get_metadata),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        content = await file.read(settings.max_upload_bytes + 1)
        with metadata.session() as session:
            dataset = ingest_tabular_file(
                session=session,
                settings=settings,
                filename=file.filename or "upload",
                content=content,
            )
            return dataset_detail(dataset, settings)
    finally:
        await file.close()


@router.delete("/{dataset_id}")
def delete_dataset(
    dataset_id: str,
    metadata: MetadataDatabase = Depends(get_metadata),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    with metadata.session() as session:
        dataset = session.get(Dataset, dataset_id)
        if dataset is None:
            raise AppError(
                "dataset_not_found", "The selected dataset does not exist.", status_code=404
            )
        delete_uploaded_dataset(dataset, settings)
        session.execute(delete(QueryLog).where(QueryLog.dataset_id == dataset_id))
        session.execute(delete(Conversation).where(Conversation.dataset_id == dataset_id))
        session.delete(dataset)
    return {"status": "deleted", "dataset_id": dataset_id}
