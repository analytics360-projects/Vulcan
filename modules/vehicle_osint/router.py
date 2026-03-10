"""Vehicle OSINT router — VIN decode, REPUVE lookup, social OSINT, full search"""
import json
from fastapi import APIRouter, Query, Request
from typing import Optional

from config import logger
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


def _log_response_json(tag: str, result):
    """Log full JSON response for debugging what gets sent to Balder."""
    try:
        data = result.model_dump() if hasattr(result, "model_dump") else result
        json_str = json.dumps(data, default=str, ensure_ascii=False, indent=2)
        logger.info(f"[{tag}] RESPONSE JSON:\n{json_str}")
    except Exception as e:
        logger.warning(f"[{tag}] Could not serialize response: {e}")


@router.get("/vin-decode", response_model=VinDecodeResult)
async def vin_decode_endpoint(vin: str = Query(..., min_length=11, max_length=17)):
    """Decode a VIN using the free NHTSA API."""
    result = await decode_vin(vin)
    _log_response_json("VIN-DECODE", result)
    return result


@router.get("/repuve", response_model=RepuveResult)
async def repuve_endpoint(
    placa: Optional[str] = Query(None),
    niv: Optional[str] = Query(None),
):
    """Search REPUVE for vehicle registration / stolen status."""
    result = await search_repuve(placa=placa, niv=niv)
    _log_response_json("REPUVE", result)
    return result


@router.get("/osint", response_model=VehicleOsintResult)
async def osint_endpoint(placa: str = Query(...)):
    """Search vehicle plate across marketplace, twitter, google, forums."""
    result = await search_vehicle_osint(placa)
    _log_response_json("VEHICLE-OSINT", result)
    return result


@router.get("/full-search", response_model=VehicleFullSearchResponse)
async def full_search_endpoint(
    request: Request,
    placa: Optional[str] = Query(None),
    niv: Optional[str] = Query(None),
):
    """Full vehicle search: VIN decode + REPUVE + OSINT in parallel."""
    client = request.client.host if request.client else "?"
    logger.info(f"[VEHICLE-ROUTER] Full search request from {client}: placa={placa}, niv={niv}")
    result = await full_vehicle_search(placa=placa, niv=niv)
    _log_response_json("VEHICLE-FULL-SEARCH", result)
    logger.info(f"[VEHICLE-ROUTER] Full search response sent to {client}")
    return result
