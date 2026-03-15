"""Training service — Supervised learning pipeline with simulated training"""
import hashlib
import math
import random
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from config import logger
from modules.training.models import (
    DatasetInfo,
    SampleInfo,
    TrainingJobInfo,
    TrainingConfig,
    EvaluationResult,
    DeploymentInfo,
)


class TrainingService:
    """In-memory training pipeline service.

    In production this would dispatch to GPU workers (SageMaker, etc.).
    For now it simulates the full lifecycle with realistic status tracking.
    """

    def __init__(self):
        self._datasets: Dict[str, DatasetInfo] = {}
        self._samples: Dict[str, List[SampleInfo]] = {}  # dataset_id -> samples
        self._jobs: Dict[str, TrainingJobInfo] = {}
        self._evaluations: Dict[str, EvaluationResult] = {}
        self._deployments: Dict[str, DeploymentInfo] = {}
        self._active_models: Dict[str, str] = {}  # model_type -> job_id
        logger.info("[TrainingService] Initialized (simulated mode)")

    # ── Datasets ──

    def create_dataset(self, name: str, category: str, description: str = "") -> DatasetInfo:
        ds_id = f"ds-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        ds = DatasetInfo(
            id=ds_id,
            name=name,
            category=category,
            description=description,
            sample_count=0,
            created_at=now,
            status="empty",
        )
        self._datasets[ds_id] = ds
        self._samples[ds_id] = []
        logger.info(f"[TrainingService] Dataset created: {ds_id} ({name}/{category})")
        return ds

    def list_datasets(self) -> List[DatasetInfo]:
        return list(self._datasets.values())

    def get_dataset(self, dataset_id: str) -> Optional[DatasetInfo]:
        return self._datasets.get(dataset_id)

    def add_samples(self, dataset_id: str, samples: List[Dict]) -> int:
        ds = self._datasets.get(dataset_id)
        if not ds:
            raise ValueError(f"Dataset {dataset_id} not found")

        added = 0
        for s in samples:
            sample = SampleInfo(
                id=f"smp-{uuid.uuid4().hex[:8]}",
                dataset_id=dataset_id,
                filename=s.get("filename", f"sample_{added}.jpg"),
                label=s.get("label", "unknown"),
                content_type=s.get("content_type", "image/jpeg"),
                added_at=datetime.now(timezone.utc).isoformat(),
            )
            self._samples[dataset_id].append(sample)
            added += 1

        ds.sample_count = len(self._samples[dataset_id])
        ds.status = "ready" if ds.sample_count >= 5 else "empty"
        logger.info(f"[TrainingService] Added {added} samples to {dataset_id} (total: {ds.sample_count})")
        return added

    def get_samples(self, dataset_id: str) -> List[SampleInfo]:
        return self._samples.get(dataset_id, [])

    # ── Training ──

    def start_training(
        self, dataset_id: str, model_type: str, config: Optional[TrainingConfig] = None
    ) -> TrainingJobInfo:
        ds = self._datasets.get(dataset_id)
        if not ds:
            raise ValueError(f"Dataset {dataset_id} not found")
        if ds.sample_count < 5:
            raise ValueError(f"Dataset {dataset_id} needs at least 5 samples (has {ds.sample_count})")

        cfg = config or TrainingConfig()
        job_id = f"job-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()

        job = TrainingJobInfo(
            job_id=job_id,
            dataset_id=dataset_id,
            model_type=model_type,
            status="queued",
            progress=0.0,
            epochs_completed=0,
            total_epochs=cfg.epochs,
            metrics={"loss": 0.0, "accuracy": 0.0, "f1": 0.0},
            config=cfg,
            created_at=now,
        )
        self._jobs[job_id] = job
        ds.status = "training"

        # Simulate immediate training progression
        self._simulate_training(job, ds.sample_count)

        logger.info(f"[TrainingService] Training started: {job_id} (dataset={dataset_id}, type={model_type})")
        return job

    def _simulate_training(self, job: TrainingJobInfo, sample_count: int):
        """Simulate training completion with realistic metrics.

        In production this would be an async background task.
        For demo purposes we complete immediately with simulated metrics.
        """
        # More samples = better metrics (with randomness)
        base_quality = min(0.95, 0.5 + (sample_count / 200.0))
        noise = random.uniform(-0.05, 0.05)

        accuracy = min(0.99, max(0.4, base_quality + noise))
        loss = max(0.01, 1.0 - accuracy + random.uniform(0, 0.1))
        f1 = min(0.99, max(0.3, accuracy - random.uniform(0, 0.05)))

        job.status = "completed"
        job.progress = 100.0
        job.epochs_completed = job.total_epochs
        job.metrics = {
            "loss": round(loss, 4),
            "accuracy": round(accuracy, 4),
            "f1": round(f1, 4),
            "val_loss": round(loss + random.uniform(0, 0.05), 4),
            "val_accuracy": round(accuracy - random.uniform(0, 0.03), 4),
        }
        job.completed_at = datetime.now(timezone.utc).isoformat()

    def get_training_status(self, job_id: str) -> Optional[TrainingJobInfo]:
        return self._jobs.get(job_id)

    def list_jobs(self) -> List[TrainingJobInfo]:
        return list(self._jobs.values())

    # ── Evaluation ──

    def evaluate_model(self, job_id: str) -> EvaluationResult:
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        if job.status != "completed":
            raise ValueError(f"Job {job_id} is not completed (status: {job.status})")

        ds = self._datasets.get(job.dataset_id)
        sample_count = ds.sample_count if ds else 10

        # Generate realistic evaluation metrics
        base = min(0.95, 0.5 + (sample_count / 200.0))
        precision = round(min(0.99, max(0.3, base + random.uniform(-0.03, 0.03))), 4)
        recall = round(min(0.99, max(0.3, base + random.uniform(-0.05, 0.02))), 4)
        f1 = round(2 * (precision * recall) / (precision + recall + 1e-8), 4)
        accuracy = round(min(0.99, max(0.3, (precision + recall) / 2 + random.uniform(-0.02, 0.02))), 4)

        # Simulated confusion matrix for 3 classes
        labels = self._get_labels_for_type(job.model_type)
        confusion = {}
        per_class = {}
        for label in labels:
            row = {}
            total = random.randint(20, 50)
            correct = int(total * accuracy)
            remaining = total - correct
            row[label] = correct
            other_labels = [l for l in labels if l != label]
            for ol in other_labels:
                share = random.randint(0, remaining)
                row[ol] = share
                remaining -= share
            if other_labels:
                row[other_labels[-1]] = row.get(other_labels[-1], 0) + remaining
            confusion[label] = row
            per_class[label] = {
                "precision": round(precision + random.uniform(-0.05, 0.05), 4),
                "recall": round(recall + random.uniform(-0.05, 0.05), 4),
                "support": total,
            }

        evaluation = EvaluationResult(
            job_id=job_id,
            precision=precision,
            recall=recall,
            f1=f1,
            accuracy=accuracy,
            confusion_matrix=confusion,
            per_class=per_class,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._evaluations[job_id] = evaluation
        logger.info(f"[TrainingService] Evaluated {job_id}: acc={accuracy}, f1={f1}")
        return evaluation

    def _get_labels_for_type(self, model_type: str) -> List[str]:
        if model_type == "faces":
            return ["rostro_conocido", "rostro_desconocido", "sin_rostro"]
        elif model_type == "objects":
            return ["arma", "vehiculo", "droga", "otro"]
        elif model_type == "text":
            return ["placa", "documento", "graffiti", "otro"]
        return ["clase_a", "clase_b", "clase_c"]

    # ── Deployment ──

    def deploy_model(self, job_id: str) -> DeploymentInfo:
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        if job.status != "completed":
            raise ValueError(f"Job {job_id} is not completed")

        now = datetime.now(timezone.utc).isoformat()

        # Deactivate previous model of same type
        prev_job_id = self._active_models.get(job.model_type)
        if prev_job_id and prev_job_id in self._deployments:
            self._deployments[prev_job_id].active = False

        version_num = len([d for d in self._deployments.values() if d.model_type == job.model_type]) + 1
        deployment = DeploymentInfo(
            job_id=job_id,
            model_type=job.model_type,
            deployed=True,
            deployed_at=now,
            version=f"{version_num}.0.0",
            active=True,
        )
        self._deployments[job_id] = deployment
        self._active_models[job.model_type] = job_id

        logger.info(f"[TrainingService] Deployed {job_id} as {job.model_type} v{deployment.version}")
        return deployment

    def get_active_models(self) -> Dict[str, DeploymentInfo]:
        result = {}
        for model_type, job_id in self._active_models.items():
            dep = self._deployments.get(job_id)
            if dep and dep.active:
                result[model_type] = dep
        return result


# Singleton
training_service = TrainingService()
