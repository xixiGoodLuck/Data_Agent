from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy import delete, select

from app.api.dependencies import get_metadata, get_settings
from app.core.config import Settings
from app.core.db import MetadataDatabase
from app.core.errors import AppError
from app.data.csv_loader import delete_uploaded_dataset, ingest_tabular_file
from app.data.registry import dataset_detail, dataset_summary, list_datasets
from app.data.seed import seed_builtin_datasets
from app.models import AgentRun, Conversation, Dataset, DisabledBuiltinDataset, QueryLog
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
    request: Request,
    metadata: MetadataDatabase = Depends(get_metadata),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    with metadata.session() as session:
        dataset = session.get(Dataset, dataset_id)
        if dataset is None:
            raise AppError(
                "dataset_not_found", "The selected dataset does not exist.", status_code=404
            )
        thread_ids = set(
            session.scalars(
                select(AgentRun.thread_id)
                .join(QueryLog, QueryLog.id == AgentRun.query_log_id)
                .where(QueryLog.dataset_id == dataset_id)
            )
        )
        thread_ids.update(
            session.scalars(select(Conversation.id).where(Conversation.dataset_id == dataset_id))
        )
        if dataset.is_builtin:
            session.merge(DisabledBuiltinDataset(dataset_id=dataset_id))
            status = "disabled"
        else:
            delete_uploaded_dataset(dataset, settings)
            status = "deleted"
        session.execute(delete(QueryLog).where(QueryLog.dataset_id == dataset_id))
        session.execute(delete(Conversation).where(Conversation.dataset_id == dataset_id))
        session.delete(dataset)
        session.flush()
        saver = request.app.state.checkpoint.saver
        if hasattr(saver, "delete_thread"):
            for thread_id in thread_ids:
                saver.delete_thread(thread_id)
    return {"status": status, "dataset_id": dataset_id}


@router.post("/builtins/restore")
def restore_builtin_datasets(
    metadata: MetadataDatabase = Depends(get_metadata),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    with metadata.session() as session:
        disabled_ids = list(session.scalars(select(DisabledBuiltinDataset.dataset_id)))
        session.execute(delete(DisabledBuiltinDataset))
        seed_builtin_datasets(session, settings)
    return {"status": "restored", "dataset_ids": disabled_ids}
