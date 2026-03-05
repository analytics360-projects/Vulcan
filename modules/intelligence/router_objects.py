"""
Object detection and search API endpoints
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Optional, List
import os
import uuid
import json
import structlog

from modules.intelligence.models.analysis import (
    AnalysisJobResponse,
    AnalysisStatusResponse,
    AnalysisStatus,
)
from modules.intelligence.services.object_processor import ObjectProcessor
import app.services

logger = structlog.get_logger()

router = APIRouter(prefix="/intelligence", tags=["intelligence"])

# In-memory job storage (replace with Redis/database later)
jobs = {}


# ---------------------------------------------------------------------------
# POST /api/ingest/object — upload object photo for background analysis
# ---------------------------------------------------------------------------

@router.post("/ingest/object", response_model=AnalysisJobResponse)
async def ingest_object_photo(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    folio_id: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    confidence_threshold: Optional[float] = Form(0.25),
):
    """
    Upload an object photo for background analysis (object detection + embedding + graph storage).

    - **file**: Photo file (jpg, png, etc.)
    - **folio_id**: Optional folio ID if linked to a case
    - **description**: Optional description of the object
    - **tags**: Optional comma-separated Spanish tags (e.g., "evidencia,arma,pistola")
    - **metadata**: Optional JSON metadata string
    - **confidence_threshold**: Minimum confidence for object detection (default 0.5)
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
        object_name = f"objects/{photo_filename}"
        minio_url = storage_svc.upload_file(
            object_name=object_name,
            data=content,
            content_type=content_type,
            metadata={"original_filename": file.filename or ""}
        )

        logger.info("Object photo uploaded to MinIO", photo_id=photo_id, filename=file.filename, size=len(content), url=minio_url)

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

        # Parse tags
        tags_list = []
        if tags:
            tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()]

        logger.info(
            "Object ingest job created",
            photo_id=photo_id,
            folio_id=folio_id,
            description=description,
            tags=tags_list,
            confidence_threshold=confidence_threshold
        )

        job_id = str(uuid.uuid4())

        jobs[job_id] = {
            "status": AnalysisStatus.QUEUED,
            "photo_id": photo_id,
            "photo_path": minio_url,
            "object_name": object_name,
            "metadata": metadata_dict,
            "description": description,
            "tags": tags_list,
            "confidence_threshold": confidence_threshold,
        }

        background_tasks.add_task(_process_object_analysis_job, job_id)

        return AnalysisJobResponse(
            job_id=job_id,
            status=AnalysisStatus.QUEUED,
            message="Object photo uploaded and analysis started",
            photo_id=photo_id,
        )

    except Exception as e:
        logger.error("Object photo upload failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


# ---------------------------------------------------------------------------
# GET /api/ingest/object/{job_id} — check ingest status + results
# ---------------------------------------------------------------------------

@router.get("/ingest/object/{job_id}", response_model=AnalysisStatusResponse)
async def object_ingest_status(job_id: str):
    """
    Check object ingest job status and get results when complete.

    - **job_id**: Job ID returned from POST /api/ingest/object
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
# POST /api/search/object — search for similar objects
# ---------------------------------------------------------------------------

@router.post("/search/object")
async def search_objects(
    query: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    category: Optional[str] = Form(None),
    tag: Optional[str] = Form(None),
    threshold: Optional[float] = Form(0.25),
    limit: Optional[int] = Form(10),
):
    """
    Search for similar objects by image or text query.

    Provide **query** (text description in Spanish) or **image** (photo) for semantic search.
    At least one must be supplied.

    - **query**: Text query (e.g., "pistola negra", "celular iPhone")
    - **image**: Photo for visual similarity search
    - **category**: Optional category filter (e.g., "armas", "vehículos")
    - **tag**: Optional tag filter (Spanish)
    - **threshold**: Similarity threshold 0.0-1.0 (default 0.25)
    - **limit**: Max results (default 10)
    """
    if not query and not image:
        raise HTTPException(
            status_code=400,
            detail="Debe proporcionar al menos 'query' (texto) o 'image' (foto).",
        )

    # Access shared service instances
    graph_writer = app.services.graph_writer
    qdrant_service = app.services.qdrant_service
    object_embedding_service = app.services.object_embedding_service
    storage_service = app.services.storage_service

    if not object_embedding_service or not object_embedding_service.initialized:
        raise HTTPException(status_code=503, detail="Servicio de embeddings de objetos no disponible")
    if not qdrant_service:
        raise HTTPException(status_code=503, detail="Servicio de búsqueda vectorial no disponible")

    try:
        query_type = "image" if image else "text"
        query_display = query if query else (image.filename if image else "unknown")
        filters = []
        if category:
            filters.append(f"category={category}")
        if tag:
            filters.append(f"tag={tag}")
        filters_str = ", ".join(filters) if filters else "none"

        logger.info(
            "\n"
            "+==============================================================\n"
            "|  OBJECT SEARCH REQUEST\n"
            "+==============================================================\n"
            f"|  Type:       {query_type}\n"
            f"|  Query:      \"{query_display}\"\n"
            f"|  Filters:    {filters_str}\n"
            f"|  Threshold:  {threshold}\n"
            f"|  Limit:      {limit}\n"
            "+=============================================================="
        )

        # Generate query embedding
        query_embedding = None

        if image:
            # Image-based search
            file_extension = os.path.splitext(image.filename)[1] if image.filename else ".jpg"
            temp_filename = f"query_{uuid.uuid4()}{file_extension}"
            temp_path = os.path.join("/tmp", temp_filename)

            try:
                with open(temp_path, "wb") as f:
                    content = await image.read()
                    f.write(content)

                logger.info(
                    "  [1/3] IMAGE EMBEDDING",
                    filename=image.filename,
                    size_kb=f"{len(content) / 1024:.1f}"
                )

                query_embedding = object_embedding_service.generate_image_embedding(temp_path)

            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception as e:
                        logger.warning("Failed to remove temporary file", path=temp_path, error=str(e))

        elif query:
            # Text-based search — enhancement + encoding logged by embedding service
            query_embedding = object_embedding_service.generate_text_embedding(query)

        if query_embedding is None:
            logger.error("  FAILED — Could not generate query embedding")
            raise HTTPException(status_code=500, detail="Failed to generate query embedding")

        # Search in Qdrant
        matches = qdrant_service.search_similar_objects(
            query_embedding=query_embedding,
            threshold=threshold,
            limit=limit,
            category_filter=category,
            tag_filter=tag
        )

        # Enrich with photo URLs and additional metadata
        results = []
        for match in matches:
            object_id = match.get("object_id")

            # Get photo URL from Qdrant payload and convert to presigned URL
            photo_url = None

            # Get minio_url from either direct payload or metadata
            minio_url = match.get("metadata", {}).get("photo_url") if isinstance(match.get("metadata"), dict) else None

            # Try direct access if not in metadata
            if not minio_url:
                minio_url = match.get("photo_url")

            if minio_url and minio_url.startswith("minio://"):
                try:
                    object_name = minio_url.replace(f"minio://{storage_service.bucket_name}/", "")
                    photo_url = storage_service.get_presigned_url(object_name, expires_seconds=3600)
                except Exception as e:
                    logger.warning("Failed to generate presigned URL", object_id=object_id, error=str(e))
                    photo_url = None

            results.append({
                "object_id": object_id,
                "object_type": match.get("object_type_es"),
                "category": match.get("category"),
                "tags": match.get("tags", []),
                "similarity_score": match.get("score"),
                "photo_url": photo_url,
                "folio_id": match.get("folio_id"),
            })

        logger.info(
            "\n"
            "+==============================================================\n"
            f"|  SEARCH COMPLETE -- {len(results)} result(s) returned\n"
            "+=============================================================="
        )

        return JSONResponse(content={
            "query_type": query_type,
            "query": query if query else "image_search",
            "category_filter": category,
            "tag_filter": tag,
            "matches_found": len(results),
            "results": results
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Object search failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error al buscar objetos: {str(e)}")


# ---------------------------------------------------------------------------
# GET /api/list/objects — list objects with optional filters
# ---------------------------------------------------------------------------

@router.get("/list/objects")
async def list_objects(
    category: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """
    List objects with optional category/tag filters.

    - **category**: Optional category filter (e.g., "armas", "vehículos", "electrónicos")
    - **tag**: Optional tag filter (Spanish)
    - **limit**: Max results (default 50)
    - **offset**: Skip first N results (default 0)
    """
    graph_writer = app.services.graph_writer
    storage_service = app.services.storage_service

    if not graph_writer:
        raise HTTPException(status_code=503, detail="Servicio de base de datos no disponible")

    try:
        if category:
            objects = graph_writer.get_objects_by_category(category, limit=limit, offset=offset)
        elif tag:
            objects = graph_writer.get_objects_by_tag(tag, limit=limit, offset=offset)
        else:
            objects = graph_writer.list_all_objects(limit=limit, offset=offset)

        # Convert MinIO URLs to presigned URLs
        if storage_service:
            for obj in objects:
                minio_url = obj.get("photo_url")
                if minio_url and minio_url.startswith("minio://"):
                    try:
                        object_name = minio_url.replace(f"minio://{storage_service.bucket_name}/", "")
                        obj["photo_url"] = storage_service.get_presigned_url(object_name, expires_seconds=3600)
                    except Exception as e:
                        logger.warning("Failed to generate presigned URL", object_id=obj.get("object_id"), error=str(e))
                        obj["photo_url"] = None

        logger.info("Objects listed", category=category, tag=tag, count=len(objects))

        return JSONResponse(content={
            "category_filter": category,
            "tag_filter": tag,
            "count": len(objects),
            "objects": objects
        })

    except Exception as e:
        logger.error("Failed to list objects", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error al listar objetos: {str(e)}")


# ---------------------------------------------------------------------------
# GET /api/list/categories — list object categories with statistics
# ---------------------------------------------------------------------------

@router.get("/list/categories")
async def list_categories():
    """
    List all object categories with statistics.

    Returns categories from detected objects in the database with counts.
    """
    graph_writer = app.services.graph_writer
    object_detection_service = app.services.object_detection_service

    if not graph_writer:
        raise HTTPException(status_code=503, detail="Servicio de base de datos no disponible")

    try:
        # Get statistics from Neo4j
        stats = graph_writer.get_object_categories_stats()

        # Get all available categories from detection service
        all_categories = []
        if object_detection_service and object_detection_service.initialized:
            all_categories = object_detection_service.get_all_categories()

        logger.info("Categories listed", stats_count=len(stats), all_categories=len(all_categories))

        return JSONResponse(content={
            "categories_with_objects": stats,
            "all_available_categories": all_categories
        })

    except Exception as e:
        logger.error("Failed to list categories", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error al listar categorías: {str(e)}")


# ---------------------------------------------------------------------------
# Background processing
# ---------------------------------------------------------------------------

def _process_object_analysis_job(job_id: str):
    """Background task to process object analysis"""
    temp_file_path = None
    try:
        job = jobs[job_id]
        job["status"] = AnalysisStatus.PROCESSING
        job["progress"] = 0.0

        logger.info("Processing object analysis job", job_id=job_id)

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

        processor = ObjectProcessor(
            object_detection_service=app.services.object_detection_service,
            object_embedding_service=app.services.object_embedding_service,
            graph_writer=app.services.graph_writer,
            qdrant_service=app.services.qdrant_service,
        )

        result = processor.process_object_photo(
            photo_path=temp_file_path,
            photo_id=job["photo_id"],
            metadata=job["metadata"],
            description=job.get("description"),
            photo_url=job["photo_path"],  # MinIO URL
            tags=job.get("tags", []),
            confidence_threshold=job.get("confidence_threshold", 0.5)
        )

        job["status"] = result.status
        job["result"] = result
        job["progress"] = 100.0

        logger.info("Object analysis job completed", job_id=job_id, status=result.status)

    except Exception as e:
        logger.error("Object analysis job failed", job_id=job_id, error=str(e))
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
