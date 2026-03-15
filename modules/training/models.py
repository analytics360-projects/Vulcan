"""Training pipeline models"""
from typing import Optional, Dict, List
from pydantic import BaseModel, Field


class DatasetInfo(BaseModel):
    id: str
    name: str
    category: str
    description: str = ""
    sample_count: int = 0
    created_at: str = ""
    status: str = "empty"  # empty | ready | training | archived


class SampleInfo(BaseModel):
    id: str
    dataset_id: str
    filename: str
    label: str
    content_type: str = "image/jpeg"
    added_at: str = ""


class TrainingConfig(BaseModel):
    epochs: int = Field(default=10, ge=1, le=100)
    batch_size: int = Field(default=32, ge=1, le=256)
    learning_rate: float = Field(default=0.001, gt=0, lt=1)
    augmentation: bool = True


class TrainingJobInfo(BaseModel):
    job_id: str
    dataset_id: str
    model_type: str  # faces | objects | text
    status: str = "queued"  # queued | training | completed | failed
    progress: float = 0.0  # 0-100
    epochs_completed: int = 0
    total_epochs: int = 10
    metrics: Dict = Field(default_factory=lambda: {"loss": 0.0, "accuracy": 0.0, "f1": 0.0})
    config: Optional[TrainingConfig] = None
    created_at: str = ""
    completed_at: Optional[str] = None
    error: Optional[str] = None


class EvaluationResult(BaseModel):
    job_id: str
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    accuracy: float = 0.0
    confusion_matrix: Dict = Field(default_factory=dict)
    per_class: Dict = Field(default_factory=dict)
    evaluated_at: str = ""


class DeploymentInfo(BaseModel):
    job_id: str
    model_type: str
    deployed: bool = False
    deployed_at: Optional[str] = None
    version: str = "1.0.0"
    active: bool = False


# ── Request models ──

class CreateDatasetRequest(BaseModel):
    name: str
    category: str
    description: str = ""


class AddSamplesRequest(BaseModel):
    samples: List[Dict]  # [{filename, label, data_base64?}]


class StartTrainingRequest(BaseModel):
    dataset_id: str
    model_type: str = "faces"  # faces | objects | text
    config: Optional[TrainingConfig] = None
