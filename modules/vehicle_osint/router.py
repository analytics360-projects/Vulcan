"""Vehicle OSINT router — VIN decode, REPUVE lookup, social OSINT, full search"""
from fastapi import APIRouter, Query
from typing import Optional

from modules.vehicle_osint.models import (
    VinDecodeResult,
    RepuveResult,
    VehicleOsintResult,
    VehicleFullSearchResponse,
)
from modules.vehicle_osint.service import (
    decode_vin,
    search_repuve,
    search_vehicle_osint,
    full_vehicle_search,
)

router = APIRouter(prefix="/vehicle", tags=["Vehicle OSINT"])


@router.get("/vin-decode", response_model=VinDecodeResult)
async def vin_decode_endpoint(vin: str = Query(..., min_length=11, max_length=17)):
    """Decode a VIN using the free NHTSA API."""
    return await decode_vin(vin)


@router.get("/repuve", response_model=RepuveResult)
async def repuve_endpoint(
    placa: Optional[str] = Query(None),
    niv: Optional[str] = Query(None),
):
    """Search REPUVE for vehicle registration / stolen status."""
    return await search_repuve(placa=placa, niv=niv)


@router.get("/osint", response_model=VehicleOsintResult)
async def osint_endpoint(placa: str = Query(...)):
    """Search vehicle plate across marketplace, twitter, google, forums."""
    return await search_vehicle_osint(placa)


@router.get("/full-search", response_model=VehicleFullSearchResponse)
async def full_search_endpoint(
    placa: Optional[str] = Query(None),
    niv: Optional[str] = Query(None),
):
    """Full vehicle search: VIN decode + REPUVE + OSINT in parallel."""
    return await full_vehicle_search(placa=placa, niv=niv)
