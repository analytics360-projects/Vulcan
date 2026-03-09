"""Vehicle OSINT service — VIN decode, REPUVE, social OSINT"""
import asyncio
from datetime import datetime, timezone

import httpx

from config import logger
from modules.vehicle_osint.models import (
    VinDecodeResult,
    RepuveResult,
    VehicleOsintResult,
    VehicleFullSearchResponse,
)

NHTSA_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"


async def decode_vin(vin: str) -> VinDecodeResult:
    """Decode VIN via NHTSA free API."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(NHTSA_URL.format(vin=vin))
            resp.raise_for_status()
            data = resp.json()

        results = data.get("Results", [{}])[0]
        year_raw = results.get("ModelYear", "")
        year = int(year_raw) if year_raw and year_raw.isdigit() else None

        return VinDecodeResult(
            vin=vin,
            make=results.get("Make") or None,
            model=results.get("Model") or None,
            year=year,
            vehicle_type=results.get("VehicleType") or None,
            engine=results.get("EngineModel") or None,
            country=results.get("PlantCountry") or None,
            body_class=results.get("BodyClass") or None,
            raw=results,
        )
    except Exception as e:
        logger.warning(f"VIN decode error: {e}")
        return VinDecodeResult(vin=vin, error=str(e))


async def search_repuve(placa: str = None, niv: str = None) -> RepuveResult:
    """Proxy to existing REPUVE scraper in public_records module."""
    try:
        from modules.public_records.service import search_repuve as _search_repuve

        result = await _search_repuve(placa=placa, niv=niv)
        datos = result.datos or {}

        # Parse estatus from scraped text
        estatus = "no_encontrado"
        resultado_text = str(datos.get("resultado_placa", "") or datos.get("resultado_niv", "")).lower()
        if "robado" in resultado_text or "robo" in resultado_text:
            estatus = "robado"
        elif "registrado" in resultado_text or "vigente" in resultado_text:
            estatus = "registrado"

        return RepuveResult(
            placa=placa,
            niv=niv,
            estatus=estatus,
            detalles=resultado_text[:500] if resultado_text else None,
            error=result.error,
        )
    except Exception as e:
        logger.warning(f"REPUVE search error: {e}")
        return RepuveResult(placa=placa, niv=niv, estatus="error", error=str(e))


async def search_vehicle_osint(placa: str) -> VehicleOsintResult:
    """Search vehicle plate across OSINT sources in parallel."""
    result = VehicleOsintResult()

    async def _marketplace():
        try:
            from modules.marketplace.service import scrape_marketplace
            items = scrape_marketplace(
                city="mexico", product=placa, min_price=0, max_price=999999,
                days_listed=30, max_results=5,
            )
            return items or []
        except Exception as e:
            logger.warning(f"Vehicle OSINT marketplace error: {e}")
            return []

    async def _twitter():
        try:
            from modules.osint_social.service import search_twitter
            items = await search_twitter(placa, max_results=10)
            return items if isinstance(items, list) else []
        except Exception as e:
            logger.warning(f"Vehicle OSINT twitter error: {e}")
            return []

    async def _google():
        try:
            from modules.google_search.service import search_google
            queries = [
                f'"{placa}" vehiculo',
                f'"{placa}" accidente OR robo OR reporte',
            ]
            all_results = []
            for q in queries:
                items = await search_google(q, max_results=5)
                if isinstance(items, list):
                    all_results.extend(items)
            return all_results
        except Exception as e:
            logger.warning(f"Vehicle OSINT google error: {e}")
            return []

    async def _forums():
        try:
            from modules.osint_social.service import search_forums
            items = await search_forums(placa, max_results=5)
            return items if isinstance(items, list) else []
        except Exception as e:
            logger.warning(f"Vehicle OSINT forums error: {e}")
            return []

    marketplace, twitter, google, forums = await asyncio.gather(
        _marketplace(), _twitter(), _google(), _forums(),
    )

    result.marketplace = marketplace
    result.twitter = twitter
    result.google = google
    result.forums = forums
    result.total = len(marketplace) + len(twitter) + len(google) + len(forums)

    return result


async def full_vehicle_search(
    placa: str = None,
    niv: str = None,
) -> VehicleFullSearchResponse:
    """Run all vehicle searches in parallel."""
    vin_coro = decode_vin(niv) if niv else None
    repuve_coro = search_repuve(placa=placa, niv=niv) if (placa or niv) else None
    osint_coro = search_vehicle_osint(placa) if placa else None

    coros = [c for c in [vin_coro, repuve_coro, osint_coro] if c is not None]
    results = await asyncio.gather(*coros, return_exceptions=True) if coros else []

    idx = 0
    vin_result = None
    repuve_result = None
    osint_result = None

    if vin_coro is not None:
        vin_result = results[idx] if isinstance(results[idx], VinDecodeResult) else None
        idx += 1
    if repuve_coro is not None:
        repuve_result = results[idx] if isinstance(results[idx], RepuveResult) else None
        idx += 1
    if osint_coro is not None:
        osint_result = results[idx] if isinstance(results[idx], VehicleOsintResult) else None

    return VehicleFullSearchResponse(
        vin_decode=vin_result,
        repuve=repuve_result,
        osint=osint_result,
        placa=placa,
        niv=niv,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
