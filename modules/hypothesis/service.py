"""Hypothesis service — investigative hypothesis generation using Ollama."""
import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from config import settings, logger
from modules.hypothesis.models import (
    HypothesisRequest, HypothesisResponse, Hipotesis, AccionSugerida,
    AcceptRequest, AcceptResponse,
)

HYPOTHESIS_SCHEMA = {
    "type": "object",
    "required": ["hipotesis"],
    "properties": {
        "hipotesis": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["titulo", "descripcion", "evidencia_sustento",
                             "acciones_sugeridas", "datos_faltantes", "prioridad",
                             "modulos_sugeridos", "confianza"],
                "properties": {
                    "titulo": {"type": "string"},
                    "descripcion": {"type": "string"},
                    "evidencia_sustento": {"type": "array", "items": {"type": "string"}},
                    "acciones_sugeridas": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "descripcion": {"type": "string"},
                                "modulo_sugerido": {"type": "string"},
                                "prioridad": {"type": "integer", "minimum": 1, "maximum": 5},
                            },
                        },
                    },
                    "datos_faltantes": {"type": "array", "items": {"type": "string"}},
                    "prioridad": {"type": "string", "enum": ["ALTA", "MEDIA", "BAJA"]},
                    "modulos_sugeridos": {"type": "array", "items": {"type": "string"}},
                    "confianza": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
    },
}


def _custody_hash(user: str, modulo: str, accion: str, params: dict) -> str:
    payload = f"{user}|{modulo}|{accion}|{json.dumps(params, sort_keys=True)}|{datetime.now(timezone.utc).isoformat()}"
    return hashlib.sha256(payload.encode()).hexdigest()


class HypothesisService:
    """Generate investigative hypotheses from carpeta data using Ollama."""

    def _gather_snapshot(self, carpeta_id: str) -> Dict:
        """Gather all available data for a carpeta."""
        snapshot = {
            "carpeta": {},
            "personas": [],
            "vehiculos": [],
            "evidencias": [],
            "sans_results": [],
            "consistency": [],
            "profiles": [],
        }

        # Query PostgreSQL for carpeta data
        try:
            import psycopg2
            conn = psycopg2.connect(settings.postgres_main_connection_string)
            with conn.cursor() as cur:
                # Carpeta info
                cur.execute(
                    """SELECT "Id", "Folio", "Tipo", "Estatus", "Prioridad", "FechaCreacion"
                       FROM "CarpetasInvestigacion" WHERE "Id" = %s""",
                    (int(carpeta_id),)
                )
                row = cur.fetchone()
                if row:
                    snapshot["carpeta"] = {
                        "id": row[0], "folio": row[1], "tipo_delito": row[2],
                        "estatus": row[3], "prioridad": row[4],
                        "fecha": str(row[5]) if row[5] else "",
                    }

                # Personas
                cur.execute(
                    """SELECT "Nombre", "ApellidoPaterno", "ApellidoMaterno", "Curp", "Estatus"
                       FROM "SujetosCarpeta" WHERE "CarpetaInvestigacionId" = %s""",
                    (int(carpeta_id),)
                )
                snapshot["personas"] = [
                    {"nombre": f"{r[0] or ''} {r[1] or ''} {r[2] or ''}".strip(),
                     "curp": r[3], "estatus": r[4]}
                    for r in cur.fetchall()
                ]

                # Nodos (entities)
                cur.execute(
                    """SELECT "Tipo", "Nombre", "Datos"
                       FROM "CarpetasNodos" WHERE "CarpetaInvestigacionId" = %s LIMIT 50""",
                    (int(carpeta_id),)
                )
                nodos = cur.fetchall()
                for n in nodos:
                    tipo = n[0] or ""
                    if "vehiculo" in tipo.lower():
                        snapshot["vehiculos"].append({"nombre": n[1], "datos": n[2]})

            conn.close()
        except Exception as e:
            logger.warning(f"Failed to gather carpeta data: {e}")

        # Query RavenDB for SANS/consistency/profiles
        try:
            from modules.sans.ravendb_client import get_store
            store = get_store()
            with store.open_session() as session:
                # SANS results
                results = list(session.query_collection("sans_results"))
                snapshot["sans_results"] = [
                    r.__dict__ if hasattr(r, '__dict__') else {}
                    for r in results
                    if str(getattr(r, 'carpeta_id', '')) == carpeta_id
                ][:5]  # Limit

                # Consistency reports
                results = list(session.query_collection("consistency"))
                snapshot["consistency"] = [
                    r.__dict__ if hasattr(r, '__dict__') else {}
                    for r in results
                    if str(getattr(r, 'carpeta_id', '')) == carpeta_id
                ]
        except Exception:
            pass

        return snapshot

    def _calculate_completeness(self, snapshot: Dict) -> float:
        """Calculate carpeta completeness percentage."""
        fields = [
            bool(snapshot["carpeta"]),
            len(snapshot["personas"]) > 0,
            len(snapshot["vehiculos"]) > 0,
            len(snapshot["evidencias"]) > 0,
            len(snapshot["sans_results"]) > 0,
            len(snapshot["consistency"]) > 0,
            len(snapshot["profiles"]) > 0,
            bool(snapshot["carpeta"].get("tipo_delito")),
            bool(snapshot["carpeta"].get("prioridad")),
        ]
        return round(sum(fields) / len(fields) * 100, 1)

    async def generate(self, req: HypothesisRequest) -> HypothesisResponse:
        """Generate investigative hypotheses from carpeta data."""
        from clients.ollama_client import ollama_chat, MODEL_LARGE

        snapshot = self._gather_snapshot(req.carpeta_id)
        completitud = self._calculate_completeness(snapshot)

        # Threshold check
        if completitud < 60 and not req.force_generate:
            h = _custody_hash(req.user, "HYPOTHESIS", "Generate", {
                "carpeta_id": req.carpeta_id, "completitud": completitud, "skipped": True,
            })
            return HypothesisResponse(
                hypotheses=[], completitud_carpeta_pct=completitud, hash_custodia=h,
            )

        # Build context
        context = self._format_context(snapshot)

        messages = [
            {
                "role": "system",
                "content": (
                    "Eres un analista de inteligencia criminal senior trabajando en México. "
                    "Con base en la información de la carpeta de investigación, genera hipótesis "
                    "investigativas concretas y accionables.\n\n"
                    "Reglas:\n"
                    "- Basa CADA hipótesis en evidencia específica de los datos proporcionados\n"
                    "- No especules más allá de lo que los datos sugieren\n"
                    "- Prioriza hipótesis que tienen más evidencia de soporte\n"
                    "- Sugiere acciones concretas y realizables\n"
                    "- Usa terminología legal mexicana (Ministerio Público, NUC, carpeta de investigación)\n"
                    "- Responde SOLO con el JSON del schema"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Analiza esta carpeta de investigación y genera de 3 a 5 hipótesis investigativas:\n\n"
                    f"{context}\n\n"
                    "Para cada hipótesis indica título, descripción, evidencia, acciones, "
                    "datos faltantes, prioridad, módulos sugeridos y confianza."
                ),
            },
        ]

        try:
            result = await ollama_chat(
                model=MODEL_LARGE, messages=messages,
                schema=HYPOTHESIS_SCHEMA, temperature=0.2,
            )
        except Exception as e:
            logger.error(f"Hypothesis generation failed: {e}")
            result = {"hipotesis": []}

        hypotheses = []
        for i, hip in enumerate(result.get("hipotesis", [])[:5]):
            acciones = []
            for acc in hip.get("acciones_sugeridas", []):
                acciones.append(AccionSugerida(
                    descripcion=acc.get("descripcion", ""),
                    modulo_sugerido=acc.get("modulo_sugerido"),
                    prioridad=acc.get("prioridad", 3),
                ))

            hypotheses.append(Hipotesis(
                hypothesis_id=f"H{i + 1}",
                titulo=hip.get("titulo", ""),
                descripcion=hip.get("descripcion", ""),
                evidencia_sustento=hip.get("evidencia_sustento", []),
                acciones_sugeridas=acciones,
                datos_faltantes=hip.get("datos_faltantes", []),
                prioridad=hip.get("prioridad", "MEDIA"),
                modulos_sugeridos=hip.get("modulos_sugeridos", []),
                confianza=min(1.0, max(0.0, float(hip.get("confianza", 0.5)))),
            ))

        h = _custody_hash(req.user, "HYPOTHESIS", "Generate", {
            "carpeta_id": req.carpeta_id, "completitud": completitud,
            "num_hipotesis": len(hypotheses),
        })

        # Store in RavenDB
        self._store_hypotheses(req.carpeta_id, hypotheses)

        return HypothesisResponse(
            hypotheses=hypotheses,
            completitud_carpeta_pct=completitud,
            hash_custodia=h,
        )

    async def generate_async(self, payload: dict) -> dict:
        """Queue-compatible wrapper."""
        req = HypothesisRequest(
            carpeta_id=payload.get("carpeta_id", ""),
            force_generate=payload.get("force_generate", False),
        )
        result = await self.generate(req)
        return result.model_dump()

    def accept(self, req: AcceptRequest) -> AcceptResponse:
        """Accept a hypothesis and enqueue suggested actions."""
        actions_enqueued = 0
        try:
            from services.llm_queue_service import enqueue_llm_task

            # Load stored hypothesis
            from modules.sans.ravendb_client import get_store
            store = get_store()
            with store.open_session() as session:
                doc = session.load(f"hypotheses/{req.carpeta_id}")
                if doc:
                    hipotesis_list = getattr(doc, 'hypotheses', [])
                    for hip in hipotesis_list:
                        h_data = hip if isinstance(hip, dict) else (hip.__dict__ if hasattr(hip, '__dict__') else {})
                        if h_data.get("hypothesis_id") == req.hypothesis_id:
                            for mod in h_data.get("modulos_sugeridos", []):
                                mod_lower = mod.lower()
                                if mod_lower in ("sans", "ner", "consistency", "profiler", "dossier"):
                                    enqueue_llm_task(mod_lower, {
                                        "carpeta_id": req.carpeta_id,
                                    }, carpeta_id=req.carpeta_id, priority=7)
                                    actions_enqueued += 1
        except Exception as e:
            logger.warning(f"Failed to enqueue hypothesis actions: {e}")

        h = _custody_hash(req.user, "HYPOTHESIS", "Accept", {
            "carpeta_id": req.carpeta_id, "hypothesis_id": req.hypothesis_id,
        })
        return AcceptResponse(
            accepted=True, actions_enqueued=actions_enqueued, hash_custodia=h,
        )

    def _format_context(self, snapshot: Dict) -> str:
        """Format snapshot data as context string for LLM."""
        parts = ["=== CARPETA DE INVESTIGACIÓN ==="]
        c = snapshot["carpeta"]
        if c:
            parts.append(f"Folio: {c.get('folio', 'N/A')}")
            parts.append(f"Tipo de delito: {c.get('tipo_delito', 'N/A')}")
            parts.append(f"Estatus: {c.get('estatus', 'N/A')}")
            parts.append(f"Prioridad: {c.get('prioridad', 'N/A')}")
            parts.append(f"Fecha: {c.get('fecha', 'N/A')}")

        if snapshot["personas"]:
            parts.append("\n=== PERSONAS INVOLUCRADAS ===")
            for p in snapshot["personas"][:10]:
                parts.append(f"- {p.get('nombre', 'N/A')} (CURP: {p.get('curp', 'N/A')})")

        if snapshot["vehiculos"]:
            parts.append("\n=== VEHÍCULOS ===")
            for v in snapshot["vehiculos"][:5]:
                parts.append(f"- {v.get('nombre', 'N/A')}")

        if snapshot["sans_results"]:
            parts.append("\n=== RESULTADOS OSINT ===")
            for s in snapshot["sans_results"][:3]:
                parts.append(f"- {str(s)[:200]}")

        if snapshot["consistency"]:
            parts.append("\n=== ANÁLISIS DE CONSISTENCIA ===")
            for c in snapshot["consistency"]:
                parts.append(f"- Score: {c.get('score', 'N/A')}, Red flags: {c.get('red_flags', 0)}")

        return "\n".join(parts)

    def _store_hypotheses(self, carpeta_id: str, hypotheses: list):
        """Store generated hypotheses in RavenDB."""
        try:
            from modules.sans.ravendb_client import get_store
            store = get_store()
            with store.open_session() as session:
                doc = {
                    "carpeta_id": carpeta_id,
                    "hypotheses": [h.model_dump() for h in hypotheses],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                session.store(doc, f"hypotheses/{carpeta_id}")
                session.save_changes()
        except Exception as e:
            logger.warning(f"Failed to store hypotheses: {e}")


hypothesis_service = HypothesisService()
