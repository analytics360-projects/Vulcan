"""Correlation service — multi-case similarity using PostgreSQL."""
import hashlib
import json
import math
import time
from datetime import datetime, timezone
from typing import List, Optional

from config import settings, logger
from modules.correlation.models import (
    FindSimilarRequest, FindSimilarResponse, CasoSimilar,
    LinkCasesRequest, LinkCasesResponse,
    PersonCasesResponse,
)


def _custody_hash(user: str, modulo: str, accion: str, params: dict) -> str:
    payload = f"{user}|{modulo}|{accion}|{json.dumps(params, sort_keys=True)}|{datetime.now(timezone.utc).isoformat()}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _geo_distance_km(lat1, lng1, lat2, lng2) -> float:
    """Haversine distance in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _time_similarity(h1: int, h2: int) -> float:
    """Circular time similarity (0-1)."""
    diff = min(abs(h1 - h2), 24 - abs(h1 - h2))
    return max(0.0, 1.0 - diff / 12.0)


class CorrelationService:
    """Multi-case correlation using PostgreSQL queries."""

    def _get_conn(self):
        import psycopg2
        conn_str = settings.postgres_main_connection_string
        if not conn_str:
            raise RuntimeError("postgres_main_connection_string not configured")
        return psycopg2.connect(conn_str)

    def find_similar(self, req: FindSimilarRequest) -> FindSimilarResponse:
        """Find similar cases by type, location, time, and shared entities."""
        start = time.perf_counter()
        conn = self._get_conn()
        try:
            candidates: List[CasoSimilar] = []
            common_entities: List[dict] = []

            with conn.cursor() as cur:
                # Base query: same type of crime in time window
                cur.execute(
                    """SELECT "Id", "Folio", "Tipo", "Latitud", "Longitud",
                              EXTRACT(HOUR FROM "FechaCreacion") as hora,
                              EXTRACT(DOW FROM "FechaCreacion") as dow
                       FROM "CarpetasInvestigacion"
                       WHERE "Id" != %s
                         AND "FechaCreacion" > NOW() - INTERVAL '%s months'
                         AND "Estatus" != 'archivado'
                       ORDER BY "FechaCreacion" DESC
                       LIMIT 200""",
                    (req.carpeta_id, req.ventana_meses)
                )
                rows = cur.fetchall()

                for row in rows:
                    c_id, folio, tipo, lat, lng, hora, dow = row
                    razones = []
                    score = 0.0

                    # Type match (0.10)
                    if req.tipo_delito and tipo and req.tipo_delito.lower() in tipo.lower():
                        score += 0.10
                        razones.append({"campo": "tipo_delito", "similitud_pct": 100})

                    # Geo similarity (0.25)
                    if req.lat and req.lng and lat and lng:
                        dist = _geo_distance_km(req.lat, req.lng, float(lat), float(lng))
                        if dist <= req.radio_km:
                            geo_score = max(0, 1.0 - dist / req.radio_km)
                            score += geo_score * 0.25
                            razones.append({"campo": "ubicacion", "similitud_pct": round(geo_score * 100)})

                    # Time similarity (0.15)
                    if req.hora_evento is not None and hora is not None:
                        ts = _time_similarity(req.hora_evento, int(hora))
                        if ts > 0.5:
                            score += ts * 0.15
                            razones.append({"campo": "hora", "similitud_pct": round(ts * 100)})

                    if score > 0.15:
                        candidates.append(CasoSimilar(
                            carpeta_id=c_id, folio=folio or "",
                            score_similitud=round(score, 4),
                            razones=razones, entidades_comunes=[],
                        ))

                # Check shared personas
                if req.personas_ids:
                    carpeta_ids = [c.carpeta_id for c in candidates[:20]]
                    if carpeta_ids:
                        cur.execute(
                            """SELECT DISTINCT sc."CarpetaInvestigacionId", sc."Nombre", sc."ApellidoPaterno"
                               FROM "SujetosCarpeta" sc
                               WHERE sc."CarpetaInvestigacionId" = ANY(%s)
                                 AND sc."PersonaId" = ANY(%s::int[])""",
                            (carpeta_ids, [int(p) for p in req.personas_ids if p.isdigit()])
                        )
                        shared_personas = cur.fetchall()
                        for sp in shared_personas:
                            common_entities.append({
                                "tipo": "persona",
                                "nombre": f"{sp[1] or ''} {sp[2] or ''}".strip(),
                                "carpeta_id": sp[0],
                            })
                            # Boost score for shared entity
                            for c in candidates:
                                if c.carpeta_id == sp[0]:
                                    c.score_similitud = min(1.0, c.score_similitud + 0.30)
                                    c.entidades_comunes.append({"tipo": "persona", "nombre": f"{sp[1]} {sp[2]}"})

            candidates.sort(key=lambda c: c.score_similitud, reverse=True)
            candidates = candidates[:20]

            # Pattern alert
            pattern_alert = None
            high_score = [c for c in candidates if c.score_similitud > 0.75]
            if len(high_score) >= 3:
                pattern_alert = {
                    "tipo": "PATRON_SERIAL",
                    "carpetas": [c.carpeta_id for c in high_score],
                    "descripcion": f"Se detectaron {len(high_score)} casos similares en los últimos {req.ventana_meses} meses",
                }

            elapsed = (time.perf_counter() - start) * 1000
            h = _custody_hash(req.user, "CORRELATION", "FindSimilar", {
                "carpeta_id": req.carpeta_id, "results": len(candidates),
            })

            return FindSimilarResponse(
                similar_cases=candidates,
                pattern_alert=pattern_alert,
                common_entities=common_entities,
                hash_custodia=h,
            )
        finally:
            conn.close()

    async def find_similar_from_folio(self, carpeta_id: str, folio_data: dict):
        """Event handler wrapper."""
        req = FindSimilarRequest(
            carpeta_id=carpeta_id,
            tipo_delito=folio_data.get("tipo_delito", ""),
            lat=folio_data.get("lat"),
            lng=folio_data.get("lng"),
            hora_evento=folio_data.get("hora_evento"),
            personas_ids=folio_data.get("personas_ids", []),
            vehiculos_placas=folio_data.get("placas", []),
        )
        return self.find_similar(req)

    def link_cases(self, req: LinkCasesRequest) -> LinkCasesResponse:
        """Link related cases together."""
        import uuid
        grupo_id = str(uuid.uuid4())[:8]
        h = _custody_hash(req.user, "CORRELATION", "LinkCases", {
            "carpetas": req.carpeta_ids, "grupo": grupo_id,
        })
        # Store link in RavenDB
        try:
            from modules.sans.ravendb_client import get_store
            store = get_store()
            with store.open_session() as session:
                doc = {
                    "grupo_id": grupo_id, "carpetas": req.carpeta_ids,
                    "razon": req.razon,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                session.store(doc, f"case_links/{grupo_id}")
                session.save_changes()
        except Exception as e:
            logger.warning(f"Failed to store case link: {e}")
        return LinkCasesResponse(linked=True, grupo_id=grupo_id, hash_custodia=h)

    def person_cases(self, persona_id: str) -> PersonCasesResponse:
        """Get all cases involving a person."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT sc."CarpetaInvestigacionId", ci."Folio", ci."Tipo", ci."Estatus",
                              sc."Nombre", sc."ApellidoPaterno"
                       FROM "SujetosCarpeta" sc
                       JOIN "CarpetasInvestigacion" ci ON ci."Id" = sc."CarpetaInvestigacionId"
                       WHERE sc."PersonaId" = %s
                       ORDER BY ci."FechaCreacion" DESC""",
                    (int(persona_id),)
                )
                rows = cur.fetchall()
                nombre = f"{rows[0][4] or ''} {rows[0][5] or ''}".strip() if rows else ""
                carpetas = [
                    {"carpeta_id": r[0], "folio": r[1], "tipo": r[2], "estatus": r[3]}
                    for r in rows
                ]
            return PersonCasesResponse(
                persona_id=persona_id, nombre=nombre,
                carpetas=carpetas, total=len(carpetas),
            )
        finally:
            conn.close()


correlation_service = CorrelationService()
