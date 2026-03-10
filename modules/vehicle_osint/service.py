"""Vehicle OSINT service — VIN decode, REPUVE, social OSINT"""
import asyncio
import time
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


def _extract_field(text: str, label: str) -> str | None:
    """Extract a field value from scraped REPUVE text.

    Handles two formats:
    1. Plain text: 'Marca: INFINITI\\nModelo: JX'
    2. Selenium body.text from table: 'Marca:\\nINFINITI\\nModelo:\\nJX'
    """
    text_lower = text.lower()
    label_lower = label.lower()
    idx = text_lower.find(label_lower)
    if idx < 0:
        return None
    after = text[idx + len(label):].strip()
    # Take text until next newline
    lines = after.split("\n")
    # First non-empty line is the value
    for line in lines:
        val = line.strip()
        if val:
            # Stop if this looks like the next label (ends with ":")
            if val.endswith(":") or val.endswith("："):
                break
            return val if len(val) <= 200 else val[:200]
    return None


async def decode_vin(vin: str) -> VinDecodeResult:
    """Decode VIN via NHTSA free API."""
    logger.info(f"[VEHICLE] VIN decode start: {vin}")
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(NHTSA_URL.format(vin=vin))
            resp.raise_for_status()
            data = resp.json()

        results = data.get("Results", [{}])[0]
        year_raw = results.get("ModelYear", "")
        year = int(year_raw) if year_raw and year_raw.isdigit() else None

        result = VinDecodeResult(
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
        logger.info(f"[VEHICLE] VIN decode OK: {vin} → {result.make} {result.model} {result.year} ({(time.perf_counter()-t0)*1000:.0f}ms)")
        return result
    except Exception as e:
        logger.warning(f"[VEHICLE] VIN decode FAILED: {vin} → {e} ({(time.perf_counter()-t0)*1000:.0f}ms)")
        return VinDecodeResult(vin=vin, error=str(e))


async def search_repuve(placa: str = None, niv: str = None) -> RepuveResult:
    """Proxy to existing REPUVE scraper in public_records module."""
    logger.info(f"[VEHICLE] REPUVE search start: placa={placa}, niv={niv}")
    t0 = time.perf_counter()
    try:
        from modules.public_records.service import search_repuve as _search_repuve

        result = await _search_repuve(placa=placa, niv=niv)
        datos = result.datos or {}

        # Parse estatus from scraped text
        estatus = "no_encontrado"
        resultado_text = str(datos.get("resultado_placa", "") or datos.get("resultado_niv", "")).lower()
        if "robado" in resultado_text or "robo" in resultado_text:
            estatus = "robado"
        elif "no se encontr" in resultado_text or "sin resultado" in resultado_text or "no existe" in resultado_text:
            estatus = "no_encontrado"
        elif "marca:" in resultado_text or "modelo:" in resultado_text or "niv:" in resultado_text or "placa:" in resultado_text:
            # REPUVE returned vehicle data — vehicle is registered
            estatus = "registrado"
        elif "registrado" in resultado_text or "vigente" in resultado_text:
            estatus = "registrado"
        elif len(resultado_text.strip()) > 200:
            # Substantial response text likely means vehicle was found
            estatus = "registrado"

        # Parse vehicle data fields from scraped text
        marca = _extract_field(resultado_text, "marca:")
        modelo_v = _extract_field(resultado_text, "modelo:")
        anio = _extract_field(resultado_text, "año modelo:") or _extract_field(resultado_text, "ano modelo:")
        clase = _extract_field(resultado_text, "clase:")
        tipo = _extract_field(resultado_text, "tipo:")
        entidad = _extract_field(resultado_text, "entidad que emplacó:") or _extract_field(resultado_text, "entidad que emplaco:")
        version = _extract_field(resultado_text, "versión:") or _extract_field(resultado_text, "version:")
        niv_found = (
            _extract_field(resultado_text, "número de identificación vehicular (niv):")
            or _extract_field(resultado_text, "numero de identificacion vehicular (niv):")
            or _extract_field(resultado_text, "niv:")
        )
        nci = (
            _extract_field(resultado_text, "número de constancia de inscripción (nci):")
            or _extract_field(resultado_text, "numero de constancia de inscripcion (nci):")
            or _extract_field(resultado_text, "nci:")
        )
        puertas = _extract_field(resultado_text, "número de puertas:") or _extract_field(resultado_text, "numero de puertas:")
        pais_origen = _extract_field(resultado_text, "país de origen:") or _extract_field(resultado_text, "pais de origen:")
        desplazamiento = _extract_field(resultado_text, "desplazamiento (cc/l):")  or _extract_field(resultado_text, "desplazamiento:")
        cilindros = _extract_field(resultado_text, "número de cilindros:") or _extract_field(resultado_text, "numero de cilindros:")
        planta = _extract_field(resultado_text, "planta de ensamble:")
        institucion = _extract_field(resultado_text, "institución que lo inscribió:") or _extract_field(resultado_text, "institucion que lo inscribio:")
        fecha_inscripcion = _extract_field(resultado_text, "fecha de inscripción:") or _extract_field(resultado_text, "fecha de inscripcion:")
        fecha_emplacado = _extract_field(resultado_text, "fecha de emplacado:")
        fecha_actualizacion = _extract_field(resultado_text, "fecha de última actualización:") or _extract_field(resultado_text, "fecha de ultima actualizacion:")
        datos_complementarios = _extract_field(resultado_text, "datos complementarios:")

        logger.info(
            f"[VEHICLE] REPUVE result: placa={placa} → estatus={estatus} "
            f"marca={marca} modelo={modelo_v} anio={anio} niv={niv_found} "
            f"({(time.perf_counter()-t0)*1000:.0f}ms)"
        )
        return RepuveResult(
            placa=placa,
            niv=niv_found or niv,
            nci=nci,
            estatus=estatus,
            marca=marca,
            modelo=modelo_v,
            anio=anio,
            clase=clase,
            tipo=tipo,
            entidad=entidad,
            version=version,
            puertas=puertas,
            pais_origen=pais_origen,
            desplazamiento=desplazamiento,
            cilindros=cilindros,
            planta_ensamble=planta,
            institucion_inscripcion=institucion,
            fecha_inscripcion=fecha_inscripcion,
            fecha_emplacado=fecha_emplacado,
            fecha_actualizacion=fecha_actualizacion,
            datos_complementarios=datos_complementarios,
            detalles=resultado_text[:500] if resultado_text else None,
            error=result.error,
        )
    except Exception as e:
        logger.warning(f"[VEHICLE] REPUVE FAILED: placa={placa} → {e} ({(time.perf_counter()-t0)*1000:.0f}ms)")
        return RepuveResult(placa=placa, niv=niv, estatus="error", error=str(e))


async def search_vehicle_osint(placa: str) -> VehicleOsintResult:
    """Search vehicle plate across OSINT sources in parallel."""
    logger.info(f"[VEHICLE] OSINT social search start: placa={placa}")
    t0 = time.perf_counter()
    result = VehicleOsintResult()

    async def _marketplace():
        t1 = time.perf_counter()
        try:
            from modules.marketplace.service import scrape_marketplace
            items = scrape_marketplace(
                city="mexico", product=placa, min_price=0, max_price=999999,
                days_listed=30, max_results=5,
            )
            items = items or []
            logger.info(f"[VEHICLE]   ├─ Marketplace: {len(items)} results ({(time.perf_counter()-t1)*1000:.0f}ms)")
            return items
        except Exception as e:
            logger.warning(f"[VEHICLE]   ├─ Marketplace FAILED: {e} ({(time.perf_counter()-t1)*1000:.0f}ms)")
            return []

    async def _twitter():
        t1 = time.perf_counter()
        try:
            from modules.osint_social.twitter_service import search
            items = await search(query=placa, max_results=10)
            items = items if isinstance(items, list) else []
            logger.info(f"[VEHICLE]   ├─ Twitter: {len(items)} results ({(time.perf_counter()-t1)*1000:.0f}ms)")
            return items
        except Exception as e:
            logger.warning(f"[VEHICLE]   ├─ Twitter FAILED: {e} ({(time.perf_counter()-t1)*1000:.0f}ms)")
            return []

    async def _google():
        t1 = time.perf_counter()
        try:
            from modules.google_search.service import search_google
            queries = [
                f'"{placa}" vehiculo',
                f'"{placa}" accidente OR robo OR reporte',
            ]
            all_results = []
            for q in queries:
                items = search_google(q, max_results=5)
                if isinstance(items, list):
                    all_results.extend(items)
            logger.info(f"[VEHICLE]   ├─ Google: {len(all_results)} results ({(time.perf_counter()-t1)*1000:.0f}ms)")
            return all_results
        except Exception as e:
            logger.warning(f"[VEHICLE]   ├─ Google FAILED: {e} ({(time.perf_counter()-t1)*1000:.0f}ms)")
            return []

    async def _forums():
        t1 = time.perf_counter()
        try:
            from modules.osint_social.forums_service import search
            items = await search(query=placa, max_results=5)
            items = items if isinstance(items, list) else []
            logger.info(f"[VEHICLE]   ├─ Forums: {len(items)} results ({(time.perf_counter()-t1)*1000:.0f}ms)")
            return items
        except Exception as e:
            logger.warning(f"[VEHICLE]   ├─ Forums FAILED: {e} ({(time.perf_counter()-t1)*1000:.0f}ms)")
            return []

    marketplace, twitter, google, forums = await asyncio.gather(
        _marketplace(), _twitter(), _google(), _forums(),
    )

    result.marketplace = marketplace
    result.twitter = twitter
    result.google = google
    result.forums = forums
    result.total = len(marketplace) + len(twitter) + len(google) + len(forums)

    logger.info(f"[VEHICLE]   └─ OSINT total: {result.total} results ({(time.perf_counter()-t0)*1000:.0f}ms)")
    return result


async def full_vehicle_search(
    placa: str = None,
    niv: str = None,
) -> VehicleFullSearchResponse:
    """Run all vehicle searches in parallel."""
    logger.info(f"[VEHICLE] ══════ FULL SEARCH START ══════  placa={placa}, niv={niv}")
    t0 = time.perf_counter()

    tasks = []
    task_names = []

    if niv:
        tasks.append(decode_vin(niv))
        task_names.append("VIN")
    if placa or niv:
        tasks.append(search_repuve(placa=placa, niv=niv))
        task_names.append("REPUVE")
    if placa:
        tasks.append(search_vehicle_osint(placa))
        task_names.append("OSINT")

    logger.info(f"[VEHICLE] Running {len(tasks)} tasks in parallel: {', '.join(task_names)}")
    results = await asyncio.gather(*tasks, return_exceptions=True) if tasks else []

    # Log any exceptions from gather
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            logger.error(f"[VEHICLE] Task {task_names[i]} raised exception: {r}")

    idx = 0
    vin_result = None
    repuve_result = None
    osint_result = None

    if niv:
        vin_result = results[idx] if idx < len(results) and isinstance(results[idx], VinDecodeResult) else None
        idx += 1
    if placa or niv:
        repuve_result = results[idx] if idx < len(results) and isinstance(results[idx], RepuveResult) else None
        idx += 1
    if placa:
        osint_result = results[idx] if idx < len(results) and isinstance(results[idx], VehicleOsintResult) else None

    elapsed = (time.perf_counter() - t0) * 1000
    logger.info(
        f"[VEHICLE] ══════ FULL SEARCH DONE ══════  placa={placa} "
        f"VIN={'✓' if vin_result and not vin_result.error else '✗'} "
        f"REPUVE={'✓' if repuve_result and not repuve_result.error else '✗'} "
        f"OSINT={'✓' if osint_result else '✗'}({osint_result.total if osint_result else 0} hits) "
        f"({elapsed:.0f}ms)"
    )

    return VehicleFullSearchResponse(
        vin_decode=vin_result,
        repuve=repuve_result,
        osint=osint_result,
        placa=placa,
        niv=niv,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
