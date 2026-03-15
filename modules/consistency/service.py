"""Consistency service — declaration comparison using Ollama (gemma3:12b)."""
import hashlib
import json
import time
from datetime import datetime, timezone
from typing import List

from config import settings, logger
from modules.consistency.models import (
    ConsistencyAnalyzeRequest, ConsistencyReport, InconsistenciaDetectada,
    Declaracion, AddDeclarationRequest, AddDeclarationResponse,
)

CONSISTENCY_SCHEMA = {
    "type": "object",
    "required": ["score_coherencia", "inconsistencias", "resumen"],
    "properties": {
        "score_coherencia": {"type": "number", "minimum": 0, "maximum": 100},
        "inconsistencias": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["tema", "texto_a", "texto_b", "tipo", "severidad"],
                "properties": {
                    "tema": {"type": "string"},
                    "texto_a": {"type": "string"},
                    "texto_b": {"type": "string"},
                    "tipo": {"type": "string", "enum": [
                        "CONTRADICCION_DIRECTA", "OMISION_SIGNIFICATIVA",
                        "CAMBIO_ENFASIS", "INCONSISTENCIA_MENOR",
                    ]},
                    "severidad": {"type": "string", "enum": ["ALTA", "MEDIA", "BAJA"]},
                },
            },
        },
        "resumen": {"type": "string"},
    },
}


def _custody_hash(user: str, modulo: str, accion: str, params: dict) -> str:
    payload = f"{user}|{modulo}|{accion}|{json.dumps(params, sort_keys=True)}|{datetime.now(timezone.utc).isoformat()}"
    return hashlib.sha256(payload.encode()).hexdigest()


class ConsistencyService:
    """Compare declarations for inconsistencies using Ollama LLM."""

    async def analyze(self, req: ConsistencyAnalyzeRequest) -> ConsistencyReport:
        """Compare declarations and find inconsistencies."""
        from clients.ollama_client import ollama_chat, MODEL_MEDIUM

        if len(req.declaraciones) < 2:
            h = _custody_hash(req.user, "CONSISTENCY", "Analyze", {"status": "single"})
            return ConsistencyReport(
                score=100.0, inconsistencias=[], red_flags=[],
                resumen_ejecutivo="Primera declaración almacenada. Se requieren al menos 2 para comparar.",
                total_declaraciones_analizadas=len(req.declaraciones),
                hash_custodia=h,
            )

        # Sort by date — oldest first as Declaración A
        sorted_decls = sorted(req.declaraciones, key=lambda d: d.fecha)

        # Compare all against the first (A vs B, A vs C, ...)
        all_inconsistencies: List[InconsistenciaDetectada] = []
        scores = []

        decl_a = sorted_decls[0]
        for decl_b in sorted_decls[1:]:
            result = await self._compare_pair(decl_a, decl_b, req.ejes_tematicos)
            scores.append(result.get("score_coherencia", 50))

            for inc in result.get("inconsistencias", []):
                all_inconsistencies.append(InconsistenciaDetectada(
                    tema=inc.get("tema", ""),
                    texto_declaracion_a=inc.get("texto_a", ""),
                    texto_declaracion_b=inc.get("texto_b", ""),
                    tipo=inc.get("tipo", "INCONSISTENCIA_MENOR"),
                    severidad=inc.get("severidad", "BAJA"),
                ))

        avg_score = sum(scores) / len(scores) if scores else 50.0
        red_flags = [i for i in all_inconsistencies if i.severidad == "ALTA"]

        # Store in RavenDB
        self._store_report(req.persona_id, req.carpeta_id, avg_score, all_inconsistencies)

        h = _custody_hash(req.user, "CONSISTENCY", "Analyze", {
            "score": avg_score, "red_flags_count": len(red_flags),
            "declaraciones_count": len(req.declaraciones),
        })

        resumen = result.get("resumen", "Análisis completado.") if scores else "Sin datos suficientes."

        return ConsistencyReport(
            score=round(avg_score, 1),
            inconsistencias=all_inconsistencies,
            red_flags=red_flags,
            resumen_ejecutivo=resumen,
            total_declaraciones_analizadas=len(req.declaraciones),
            hash_custodia=h,
        )

    async def _compare_pair(self, decl_a: Declaracion, decl_b: Declaracion,
                             ejes: list | None = None) -> dict:
        """Compare two declarations using Ollama."""
        from clients.ollama_client import ollama_chat, MODEL_MEDIUM

        ejes_text = ""
        if ejes:
            ejes_text = f"\nAnaliza especialmente estos temas: {', '.join(ejes)}"

        messages = [
            {
                "role": "system",
                "content": (
                    "Eres un analista forense especializado en verificación de testimonios para "
                    "investigaciones criminales en México. Tu tarea es comparar declaraciones "
                    "de la misma persona en momentos distintos e identificar inconsistencias. "
                    "Sé preciso y objetivo. No asumas mala fe — registra los hechos. "
                    "Responde SOLO con el JSON del schema proporcionado."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"DECLARACIÓN A ({decl_a.fuente} — {decl_a.fecha}):\n{decl_a.texto}\n\n"
                    f"DECLARACIÓN B ({decl_b.fuente} — {decl_b.fecha}):\n{decl_b.texto}\n"
                    f"{ejes_text}\n\n"
                    "Compara ambas declaraciones e identifica:\n"
                    "1. Contradicciones directas\n2. Omisiones significativas\n"
                    "3. Cambios de énfasis\n4. Inconsistencias menores\n\n"
                    "Para el score_coherencia: 100 = completamente consistentes, 0 = completamente contradictorias"
                ),
            },
        ]

        try:
            return await ollama_chat(
                model=MODEL_MEDIUM, messages=messages,
                schema=CONSISTENCY_SCHEMA, temperature=0.0,
            )
        except Exception as e:
            logger.error(f"Consistency Ollama call failed: {e}")
            return {"score_coherencia": 50, "inconsistencias": [], "resumen": f"Error en análisis: {e}"}

    async def analyze_async(self, payload: dict) -> dict:
        """Queue-compatible wrapper."""
        req = ConsistencyAnalyzeRequest(
            persona_id=payload.get("persona_id", ""),
            carpeta_id=payload.get("carpeta_id", ""),
            declaraciones=payload.get("declaraciones", []),
        )
        result = await self.analyze(req)
        return result.model_dump()

    def add_declaration(self, req: AddDeclarationRequest) -> AddDeclarationResponse:
        """Store a declaration in RavenDB for future comparison."""
        try:
            from modules.sans.ravendb_client import get_store
            store = get_store()
            with store.open_session() as session:
                doc = {
                    "persona_id": req.persona_id,
                    "carpeta_id": req.carpeta_id,
                    "texto": req.declaracion.texto,
                    "fuente": req.declaracion.fuente,
                    "fecha": req.declaracion.fecha,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                doc_id = f"declarations/{req.persona_id}/{req.carpeta_id}/{int(time.time())}"
                session.store(doc, doc_id)
                session.save_changes()

                # Count total
                results = list(session.query_collection("declarations"))
                total = len([r for r in results if getattr(r, 'persona_id', '') == req.persona_id])
        except Exception as e:
            logger.warning(f"RavenDB declaration storage failed: {e}")
            total = 0

        h = _custody_hash(req.user, "CONSISTENCY", "AddDeclaration", {
            "persona_id": req.persona_id, "carpeta_id": req.carpeta_id,
        })
        return AddDeclarationResponse(stored=True, total_declaraciones=total, hash_custodia=h)

    def get_report(self, persona_id: str, carpeta_id: str) -> dict:
        """Get latest consistency report from RavenDB."""
        try:
            from modules.sans.ravendb_client import get_store
            store = get_store()
            with store.open_session() as session:
                doc = session.load(f"consistency/{persona_id}/{carpeta_id}")
                if doc:
                    return doc.__dict__ if hasattr(doc, '__dict__') else {}
        except Exception as e:
            logger.warning(f"RavenDB report fetch failed: {e}")
        return {}

    def _store_report(self, persona_id: str, carpeta_id: str, score: float, inconsistencies: list):
        """Store consistency report in RavenDB."""
        try:
            from modules.sans.ravendb_client import get_store
            store = get_store()
            with store.open_session() as session:
                doc = {
                    "persona_id": persona_id,
                    "carpeta_id": carpeta_id,
                    "score": score,
                    "total_inconsistencias": len(inconsistencies),
                    "red_flags": len([i for i in inconsistencies if i.severidad == "ALTA"]),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                session.store(doc, f"consistency/{persona_id}/{carpeta_id}")
                session.save_changes()
        except Exception as e:
            logger.warning(f"RavenDB consistency storage failed: {e}")


consistency_service = ConsistencyService()
