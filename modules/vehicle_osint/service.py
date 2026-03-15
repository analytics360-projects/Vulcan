"""Vehicle OSINT service — VIN decode, REPUVE, social OSINT, image analysis"""
import asyncio
import io
import time
from collections import Counter
from datetime import datetime, timezone

import httpx

from config import logger
from modules.vehicle_osint.models import (
    VinDecodeResult,
    RepuveResult,
    VehicleOsintResult,
    VehicleFullSearchResponse,
    VehicleImageAnalysisResult,
    VehicleImageAttribute,
    VehicleTrainResponse,
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


# ══════════════════════════════════════════════════════════════
# M4: Vehicle Image Analysis
# ══════════════════════════════════════════════════════════════

# Color name mapping (RGB ranges to Spanish color names)
_COLOR_MAP = [
    ((0, 0, 0), (60, 60, 60), "negro"),
    ((200, 200, 200), (255, 255, 255), "blanco"),
    ((100, 100, 100), (200, 200, 200), "gris"),
    ((150, 0, 0), (255, 80, 80), "rojo"),
    ((0, 0, 150), (80, 80, 255), "azul"),
    ((0, 100, 0), (80, 255, 80), "verde"),
    ((200, 200, 0), (255, 255, 80), "amarillo"),
    ((180, 100, 0), (255, 180, 80), "naranja"),
    ((100, 50, 0), (180, 120, 60), "cafe"),
    ((150, 0, 150), (255, 80, 255), "morado"),
]


def _dominant_color_name(image_bytes: bytes) -> tuple[str, float]:
    """Extract dominant color from image using Pillow and map to a color name."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        # Resize for speed
        img = img.resize((50, 50))
        pixels = list(img.getdata())

        # Average color
        r_avg = sum(p[0] for p in pixels) / len(pixels)
        g_avg = sum(p[1] for p in pixels) / len(pixels)
        b_avg = sum(p[2] for p in pixels) / len(pixels)

        # Find closest color name
        best_name = "desconocido"
        best_dist = float("inf")
        for (r_lo, g_lo, b_lo), (r_hi, g_hi, b_hi), name in _COLOR_MAP:
            r_mid = (r_lo + r_hi) / 2
            g_mid = (g_lo + g_hi) / 2
            b_mid = (b_lo + b_hi) / 2
            dist = ((r_avg - r_mid) ** 2 + (g_avg - g_mid) ** 2 + (b_avg - b_mid) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_name = name

        # Confidence inversely proportional to distance (max ~442 for RGB)
        confidence = max(0.0, min(1.0, 1.0 - (best_dist / 250.0)))
        return best_name, round(confidence * 100, 1)
    except Exception as e:
        logger.warning(f"[VEHICLE] Color extraction failed: {e}")
        return "desconocido", 0.0


def _ocr_plate(image_bytes: bytes) -> tuple[str, float]:
    """Attempt OCR on image to extract plate text using pytesseract."""
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        # Try OCR with plate-optimized config
        text = pytesseract.image_to_string(
            img,
            config="--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-",
        ).strip()

        if text and len(text) >= 4:
            return text, 65.0
        return "no_detectada", 0.0
    except ImportError:
        logger.info("[VEHICLE] pytesseract not installed — OCR skipped")
        return "no_detectada", 0.0
    except Exception as e:
        logger.warning(f"[VEHICLE] OCR failed: {e}")
        return "no_detectada", 0.0


async def analyze_vehicle_image(image_bytes: bytes) -> VehicleImageAnalysisResult:
    """Analyze a vehicle image: extract color, attempt OCR, stub for type/make."""
    logger.info(f"[VEHICLE] analyze_vehicle_image: {len(image_bytes)} bytes")
    t0 = time.perf_counter()

    try:
        # Color analysis
        color_name, color_conf = _dominant_color_name(image_bytes)

        # OCR for plate
        plate_text, plate_conf = _ocr_plate(image_bytes)

        # Type and make are stubs (would need ML model)
        result = VehicleImageAnalysisResult(
            tipo_vehiculo=VehicleImageAttribute(
                value="sedan",  # stub
                confidence=15.0,  # low confidence = stub
            ),
            color=VehicleImageAttribute(
                value=color_name,
                confidence=color_conf,
            ),
            marca_probable=VehicleImageAttribute(
                value="desconocido",  # stub — needs trained model
                confidence=0.0,
            ),
            placa_ocr=VehicleImageAttribute(
                value=plate_text,
                confidence=plate_conf,
            ),
            anomalias_visibles=[],  # stub
            confidence=round((color_conf + plate_conf) / 2, 1),
        )

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            f"[VEHICLE] analyze_vehicle_image done: color={color_name}({color_conf}%), "
            f"plate={plate_text}({plate_conf}%) ({elapsed:.0f}ms)"
        )
        return result
    except Exception as e:
        logger.error(f"[VEHICLE] analyze_vehicle_image error: {e}")
        return VehicleImageAnalysisResult(error=str(e))


async def train_vehicle_model(label: str, image_count: int) -> VehicleTrainResponse:
    """Stub endpoint for vehicle model training."""
    logger.info(f"[VEHICLE] train_vehicle_model stub: label={label}, count={image_count}")
    return VehicleTrainResponse(
        status="stub",
        message=f"Entrenamiento para '{label}' con {image_count} imágenes pendiente de implementar",
        label=label,
    )
