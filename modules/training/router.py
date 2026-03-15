"""Training pipeline router — Supervised learning endpoints"""
from fastapi import APIRouter, HTTPException
from typing import List

from config import logger
from modules.training.models import (
    DatasetInfo,
    TrainingJobInfo,
    EvaluationResult,
    DeploymentInfo,
    CreateDatasetRequest,
    AddSamplesRequest,
    StartTrainingRequest,
)
from modules.training.service import training_service

router = APIRouter(prefix="/training", tags=["Training Pipeline"])


@router.post("/datasets", response_model=DatasetInfo)
async def create_dataset(req: CreateDatasetRequest):
    """Create a new labeled dataset for supervised training."""
    try:
        return training_service.create_dataset(req.name, req.category, req.description)
    except Exception as e:
        logger.error(f"[Training] create_dataset error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/datasets", response_model=List[DatasetInfo])
async def list_datasets():
    """List all datasets."""
    return training_service.list_datasets()


@router.get("/datasets/{dataset_id}", response_model=DatasetInfo)
async def get_dataset(dataset_id: str):
    """Get dataset details."""
    ds = training_service.get_dataset(dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
    return ds


@router.post("/datasets/{dataset_id}/samples")
async def add_samples(dataset_id: str, req: AddSamplesRequest):
    """Add labeled samples to a dataset."""
    try:
        count = training_service.add_samples(dataset_id, req.samples)
        ds = training_service.get_dataset(dataset_id)
        return {"added": count, "total": ds.sample_count if ds else count, "dataset_id": dataset_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[Training] add_samples error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/start", response_model=TrainingJobInfo)
async def start_training(req: StartTrainingRequest):
    """Start a training job on a dataset."""
    try:
        return training_service.start_training(req.dataset_id, req.model_type, req.config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[Training] start_training error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{job_id}", response_model=TrainingJobInfo)
async def get_training_status(job_id: str):
    """Get training job status and metrics."""
    job = training_service.get_training_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


@router.get("/jobs", response_model=List[TrainingJobInfo])
async def list_jobs():
    """List all training jobs."""
    return training_service.list_jobs()


@router.post("/evaluate/{job_id}", response_model=EvaluationResult)
async def evaluate_model(job_id: str):
    """Evaluate a completed model — precision, recall, F1, confusion matrix."""
    try:
        return training_service.evaluate_model(job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[Training] evaluate error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deploy/{job_id}", response_model=DeploymentInfo)
async def deploy_model(job_id: str):
    """Deploy a trained model as the active model for its type."""
    try:
        return training_service.deploy_model(job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[Training] deploy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/active-models")
async def get_active_models():
    """Get currently deployed/active models by type."""
    return training_service.get_active_models()
