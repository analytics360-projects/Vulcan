"""Deduplication router — person matching endpoints."""
from fastapi import APIRouter, HTTPException
from config import logger
from modules.deduplication.models import (
    DeduplicationRequest, DeduplicationResponse,
    CheckPersonRequest, CheckPersonResponse,
    MergePersonRequest, MergePersonResponse,
    MarkAliasRequest, MarkAliasResponse,
)
from modules.deduplication.service import deduplication_service, db_deduplication_service

router = APIRouter(prefix="/deduplication", tags=["Deduplication"])


@router.post("/find-duplicates", response_model=DeduplicationResponse)
async def find_duplicates(request: DeduplicationRequest):
    """Find duplicate persons using in-memory fuzzy matching."""
    try:
        return deduplication_service.find_duplicates(request)
    except Exception as e:
        logger.exception(f"Deduplication error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/CheckPerson", response_model=CheckPersonResponse)
async def check_person(request: CheckPersonRequest):
    """Check if person exists in DB using pg_trgm fuzzy + exact CURP/RFC."""
    try:
        return db_deduplication_service.check_person(request)
    except Exception as e:
        logger.exception(f"CheckPerson error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/MergePerson", response_model=MergePersonResponse)
async def merge_person(request: MergePersonRequest):
    """Merge two duplicate persons."""
    try:
        return db_deduplication_service.merge_persons(request)
    except Exception as e:
        logger.exception(f"MergePerson error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/MarkAlias", response_model=MarkAliasResponse)
async def mark_alias(request: MarkAliasRequest):
    """Register an alias for a person."""
    try:
        return db_deduplication_service.mark_alias(request)
    except Exception as e:
        logger.exception(f"MarkAlias error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
