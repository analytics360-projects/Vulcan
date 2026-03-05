"""OSINT Specialized search router"""
from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from config import logger

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/phone")
async def search_phone(number: str = Query(...)):
    from modules.osint_specialized.phone_service import search
    return await search(number)


@router.get("/email")
async def search_email(email: str = Query(...)):
    from modules.osint_specialized.email_service import search
    return await search(email)


@router.get("/plate")
async def search_plate(plate: str = Query(...), country: str = Query("MX")):
    from modules.osint_specialized.plate_service import search
    return await search(plate, country)


@router.get("/identity")
async def search_identity(
    curp: Optional[str] = None,
    rfc: Optional[str] = None,
    nombre: Optional[str] = None,
):
    if not any([curp, rfc, nombre]):
        raise HTTPException(status_code=400, detail="Provide at least one: curp, rfc, or nombre")
    from modules.osint_specialized.identity_service import search
    return await search(curp=curp, rfc=rfc, nombre=nombre)
