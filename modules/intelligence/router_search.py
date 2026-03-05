"""
Unified Search API — 3 endpoints replacing analysis, query, and identity routers
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Optional
import os
import uuid
import json
import structlog

from modules.intelligence.models.analysis import (
    AnalysisJobResponse,
    AnalysisStatusResponse,
    AnalysisStatus,
)
from modules.intelligence.services.analysis_processor import AnalysisProcessor
from modules.intelligence.services.query_service import QueryService
from config import settings
import app.services

logger = structlog.get_logger()

router = APIRouter(prefix="/intelligence", tags=["intelligence"])

# In-memory job storage (replace with Redis/database later)
jobs = {}


# ---------------------------------------------------------------------------
# POST /api/search — unified text + image search
# ---------------------------------------------------------------------------

@router.post("/search")
async def search(
    query: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    threshold: Optional[float] = Form(0.7),
    limit: Optional[int] = Form(10),
):
    """
    Unified search endpoint.

    Provide **query** (natural language in Spanish) for text search,
    or **image** (photo) for face recognition search.
    At least one must be supplied.

    - **query**: Natural language query (e.g. "Buscar persona Noel Olivas")
    - **image**: Photo for face similarity search
    - **threshold**: Face similarity threshold 0.0-1.0 (default 0.7)
    - **limit**: Max results per face (default 10)
    """
    if not query and not image:
        raise HTTPException(
            status_code=400,
            detail="Debe proporcionar al menos 'query' (texto) o 'image' (foto).",
        )

    # Access shared service instances
    graph_writer = app.services.graph_writer
    qdrant_service = app.services.qdrant_service
    face_service = app.services.face_service
    entity_service = app.services.entity_service
    storage_service = app.services.storage_service

    # ---- Image search (face recognition) ----
    if image:
        if threshold < 0.0 or threshold > 1.0:
            raise HTTPException(status_code=400, detail="El threshold debe estar entre 0.0 y 1.0")
        if limit < 1 or limit > 100:
            raise HTTPException(status_code=400, detail="El limite debe estar entre 1 y 100")

        if not face_service or not face_service.initialized:
            raise HTTPException(status_code=503, detail="Servicio de deteccion de rostros no disponible")
        if not qdrant_service:
            raise HTTPException(status_code=503, detail="Servicio de busqueda vectorial no disponible")

        file_extension = os.path.splitext(image.filename)[1] if image.filename else ".jpg"
        temp_filename = f"query_{uuid.uuid4()}{file_extension}"
        temp_path = os.path.join("/tmp", temp_filename)

        try:
            with open(temp_path, "wb") as f:
                content = await image.read()
                f.write(content)

            logger.info("Image uploaded for search", filename=image.filename, size=len(content))

            query_service = QueryService(
                graph_writer=graph_writer,
                qdrant_service=qdrant_service,
                face_service=face_service,
                entity_service=entity_service,
                storage_service=storage_service,
            )

            result = query_service.search_image_matches(
                image_path=temp_path,
                threshold=threshold,
                limit=limit,
            )
            return JSONResponse(content=result)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Image search failed", error=str(e))
            raise HTTPException(status_code=500, detail=f"Error al buscar coincidencias: {str(e)}")
        finally:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception as e:
                logger.warning("Failed to remove temporary file", path=temp_path, error=str(e))

    # ---- Text search (natural language) ----
    if not graph_writer:
        raise HTTPException(status_code=503, detail="Servicio de base de datos no disponible")

    if not hasattr(graph_writer, "get_folios_by_person_name"):
        logger.error(
            "GraphWriterService missing required method",
            available_methods=[m for m in dir(graph_writer) if not m.startswith("_")],
            service_type=type(graph_writer).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="El servicio de base de datos no tiene el metodo requerido. Por favor, reinicia la aplicacion.",
        )

    try:
        query_service = QueryService(
            graph_writer=graph_writer,
            qdrant_service=qdrant_service,
            face_service=face_service,
            entity_service=entity_service,
            storage_service=storage_service,
        )

        parsed = query_service.parse_query(query)
        logger.info("Query parsed", intent=parsed.get("intent"), query=query)

        result = query_service.execute_query(parsed)
        return JSONResponse(content=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Query execution failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error al ejecutar la consulta: {str(e)}")


# ---------------------------------------------------------------------------
# POST /api/ingest — upload photo for background analysis
# ---------------------------------------------------------------------------

@router.post("/ingest", response_model=AnalysisJobResponse)
async def ingest_photo(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    folio_id: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
):
    """
    Upload a photo for background analysis (face detection + entity extraction + graph storage).

    - **file**: Photo file (jpg, png, etc.)
    - **folio_id**: Optional folio ID if linked to a case
    - **description**: Optional description/context
    - **metadata**: Optional JSON metadata string
    """
    try:
        storage_svc = app.services.storage_service
        if not storage_svc:
            raise HTTPException(status_code=503, detail="Servicio de almacenamiento no disponible")

        photo_id = str(uuid.uuid4())
        file_extension = os.path.splitext(file.filename)[1] if file.filename else ".jpg"
        photo_filename = f"{photo_id}{file_extension}"

        # Read file content
        content = await file.read()

        # Determine content type
        content_type = file.content_type or "image/jpeg"

        # Upload to MinIO
        object_name = f"evidence/{photo_filename}"
        minio_url = storage_svc.upload_file(
            object_name=object_name,
            data=content,
            content_type=content_type,
            metadata={"original_filename": file.filename or ""}
        )

        logger.info("Photo uploaded to MinIO", photo_id=photo_id, filename=file.filename, size=len(content), url=minio_url)

        # Parse metadata
        metadata_dict = {}
        if metadata:
            try:
                metadata_clean = metadata.strip().strip("'\"")
                metadata_dict = json.loads(metadata_clean)
            except json.JSONDecodeError as e:
                logger.warning("Invalid metadata JSON, ignoring", metadata=metadata, error=str(e))
                metadata_dict = {"raw_metadata": metadata}

        if folio_id:
            metadata_dict["folio_id"] = folio_id

        logger.info(
            "Ingest job created",
            photo_id=photo_id,
            folio_id=folio_id,
            description=description,
            metadata_dict=metadata_dict
        )

        job_id = str(uuid.uuid4())

        jobs[job_id] = {
            "status": AnalysisStatus.QUEUED,
            "photo_id": photo_id,
            "photo_path": minio_url,  # Store MinIO URL instead of local path
            "object_name": object_name,  # Store object name for retrieval
            "metadata": metadata_dict,
            "description": description,
            "entity_type": None,
        }

        background_tasks.add_task(_process_analysis_job, job_id)

        return AnalysisJobResponse(
            job_id=job_id,
            status=AnalysisStatus.QUEUED,
            message="Photo uploaded and analysis started",
            photo_id=photo_id,
        )

    except Exception as e:
        logger.error("Photo upload failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


# ---------------------------------------------------------------------------
# GET /api/ingest/{job_id} — check ingest status + results
# ---------------------------------------------------------------------------

@router.get("/ingest/{job_id}", response_model=AnalysisStatusResponse)
async def ingest_status(job_id: str):
    """
    Check ingest job status and get results when complete.

    - **job_id**: Job ID returned from POST /api/ingest
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]

    return AnalysisStatusResponse(
        job_id=job_id,
        status=job["status"],
        result=job.get("result"),
        progress=job.get("progress"),
        error=job.get("error"),
    )


# ---------------------------------------------------------------------------
# Background processing (unchanged from original analysis router)
# ---------------------------------------------------------------------------

def _process_analysis_job(job_id: str):
    """Background task to process analysis"""
    temp_file_path = None
    try:
        job = jobs[job_id]
        job["status"] = AnalysisStatus.PROCESSING
        job["progress"] = 0.0

        logger.info("Processing analysis job", job_id=job_id)

        from modules.intelligence.services import qdrant_service as qs

        # Download from MinIO to temporary file
        storage_svc = app.services.storage_service
        object_name = job["object_name"]

        # Create temp file path
        file_extension = os.path.splitext(object_name)[1]
        temp_filename = f"processing_{job['photo_id']}{file_extension}"
        temp_file_path = os.path.join("/tmp", temp_filename)

        # Download from MinIO
        logger.info("Downloading from MinIO for processing", object_name=object_name)
        storage_svc.download_file_to_path(object_name, temp_file_path)

        processor = AnalysisProcessor(
            face_service=app.services.face_service,
            entity_service=app.services.entity_service,
            graph_writer=app.services.graph_writer,
            qdrant_service=qs,
        )

        result = processor.process_photo(
            photo_path=temp_file_path,  # Use temp file path
            photo_id=job["photo_id"],
            metadata=job["metadata"],
            description=job.get("description"),
            entity_type=job.get("entity_type"),
            photo_url=job["photo_path"],  # MinIO URL stored in photo_path
        )

        job["status"] = result.status
        job["result"] = result
        job["progress"] = 100.0

        logger.info("Analysis job completed", job_id=job_id, status=result.status)

    except Exception as e:
        logger.error("Analysis job failed", job_id=job_id, error=str(e))
        jobs[job_id]["status"] = AnalysisStatus.FAILED
        jobs[job_id]["error"] = str(e)
    finally:
        # Clean up temp file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.info("Temporary file removed", path=temp_file_path)
            except Exception as e:
                logger.warning("Failed to remove temporary file", path=temp_file_path, error=str(e))
