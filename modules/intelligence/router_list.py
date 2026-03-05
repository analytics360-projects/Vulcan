"""
List API - Deterministic endpoints to list entities by type
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional
import structlog
import app.services

logger = structlog.get_logger()

router = APIRouter(prefix="/intelligence/list", tags=["intelligence"])


@router.get("/persons")
async def list_persons(
    limit: Optional[int] = Query(100, ge=1, le=1000),
    offset: Optional[int] = Query(0, ge=0)
):
    """
    List all persons in the database

    - **limit**: Maximum number of results (default: 100, max: 1000)
    - **offset**: Skip first N results (default: 0)
    """
    graph_writer = app.services.graph_writer
    if not graph_writer:
        raise HTTPException(status_code=503, detail="Database service unavailable")

    try:
        persons = graph_writer.list_all_persons(limit=limit, offset=offset)
        return JSONResponse(content={
            "entity_type": "Person",
            "results": persons,
            "count": len(persons),
            "limit": limit,
            "offset": offset
        })
    except Exception as e:
        logger.error("Failed to list persons", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/crimes")
async def list_crimes(
    limit: Optional[int] = Query(100, ge=1, le=1000),
    offset: Optional[int] = Query(0, ge=0)
):
    """
    List all crimes/delitos in the database

    - **limit**: Maximum number of results (default: 100, max: 1000)
    - **offset**: Skip first N results (default: 0)
    """
    graph_writer = app.services.graph_writer
    if not graph_writer:
        raise HTTPException(status_code=503, detail="Database service unavailable")

    try:
        crimes = graph_writer.list_all_crimes(limit=limit, offset=offset)
        return JSONResponse(content={
            "entity_type": "Crime",
            "results": crimes,
            "count": len(crimes),
            "limit": limit,
            "offset": offset
        })
    except Exception as e:
        logger.error("Failed to list crimes", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/folios")
async def list_folios(
    limit: Optional[int] = Query(100, ge=1, le=1000),
    offset: Optional[int] = Query(0, ge=0)
):
    """
    List all folios in the database

    - **limit**: Maximum number of results (default: 100, max: 1000)
    - **offset**: Skip first N results (default: 0)
    """
    graph_writer = app.services.graph_writer
    if not graph_writer:
        raise HTTPException(status_code=503, detail="Database service unavailable")

    try:
        folios = graph_writer.list_all_folios(limit=limit, offset=offset)
        return JSONResponse(content={
            "entity_type": "Folio",
            "results": folios,
            "count": len(folios),
            "limit": limit,
            "offset": offset
        })
    except Exception as e:
        logger.error("Failed to list folios", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/locations")
async def list_locations(
    limit: Optional[int] = Query(100, ge=1, le=1000),
    offset: Optional[int] = Query(0, ge=0)
):
    """
    List all locations in the database

    - **limit**: Maximum number of results (default: 100, max: 1000)
    - **offset**: Skip first N results (default: 0)
    """
    graph_writer = app.services.graph_writer
    if not graph_writer:
        raise HTTPException(status_code=503, detail="Database service unavailable")

    try:
        locations = graph_writer.list_all_locations(limit=limit, offset=offset)
        return JSONResponse(content={
            "entity_type": "Location",
            "results": locations,
            "count": len(locations),
            "limit": limit,
            "offset": offset
        })
    except Exception as e:
        logger.error("Failed to list locations", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/stats")
async def get_stats():
    """
    Get database statistics (counts of each entity type)
    """
    graph_writer = app.services.graph_writer
    if not graph_writer:
        raise HTTPException(status_code=503, detail="Database service unavailable")

    try:
        stats = graph_writer.get_database_stats()
        return JSONResponse(content=stats)
    except Exception as e:
        logger.error("Failed to get stats", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
