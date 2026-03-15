"""
IC7 — Risk Score Integral
Calcula un puntaje de riesgo (0-100) para una persona basado en
antecedentes, asociaciones criminales, zona, armas, reincidencia y tipo de incidente.
"""
from typing import Optional
from config import settings, logger


# ── Tipo incidente → puntaje (peso max 10) ──
INCIDENT_SCORES: dict[str, float] = {
    "homicidio": 10,
    "secuestro": 9,
    "robo_armado": 8,
    "asalto": 6,
    "robo": 4,
    "otro": 2,
}


def _nivel(score: int) -> str:
    if score <= 25:
        return "bajo"
    if score <= 50:
        return "medio"
    if score <= 75:
        return "alto"
    return "critico"


class RiskScoringService:
    """Servicio de scoring de riesgo integral para personas."""

    def __init__(self):
        self._neo4j_driver = None
        try:
            if settings.neo4j_password:
                from neo4j import GraphDatabase
                self._neo4j_driver = GraphDatabase.driver(
                    settings.neo4j_uri,
                    auth=(settings.neo4j_user, settings.neo4j_password),
                )
                logger.info("RiskScoringService: Neo4j driver initialized")
        except Exception as e:
            logger.warning(f"RiskScoringService: Neo4j not available ({e}), graph queries disabled")

    # ──────────────────────────────────────────────
    # Core scoring
    # ──────────────────────────────────────────────

    def calculate_risk_score(self, persona_data: dict) -> dict:
        """
        Calcula el risk score integral de una persona.

        Parameters
        ----------
        persona_data : dict
            - persona_id (int)
            - antecedentes (int)          — incidentes previos
            - asociaciones_criminales (int) — asociaciones en grafo
            - zona_riesgo (float 0-1)     — riesgo geoespacial del area
            - armas_reportadas (int)      — armas vinculadas
            - reincidencia (int)          — reincidencias
            - tipo_incidente (str)        — categoria de severidad

        Returns
        -------
        dict with score, nivel, factores
        """
        antecedentes = int(persona_data.get("antecedentes", 0))
        asociaciones = int(persona_data.get("asociaciones_criminales", 0))
        zona_riesgo = float(persona_data.get("zona_riesgo", 0.0))
        armas = int(persona_data.get("armas_reportadas", 0))
        reincidencia = int(persona_data.get("reincidencia", 0))
        tipo_incidente = str(persona_data.get("tipo_incidente", "otro")).lower()

        # Clamp zona_riesgo to [0, 1]
        zona_riesgo = max(0.0, min(1.0, zona_riesgo))

        # ── Factor calculations ──
        s_antecedentes = min(antecedentes * 5, 25)
        s_asociaciones = min(asociaciones * 4, 20)
        s_zona = round(zona_riesgo * 15, 2)
        s_armas = min(armas * 7.5, 15)
        s_reincidencia = min(reincidencia * 5, 15)
        s_tipo = INCIDENT_SCORES.get(tipo_incidente, 2)

        total = int(round(s_antecedentes + s_asociaciones + s_zona + s_armas + s_reincidencia + s_tipo))
        total = max(0, min(100, total))

        factores = [
            {
                "nombre": "antecedentes",
                "peso": 25,
                "score": s_antecedentes,
                "maximo": 25,
                "descripcion": f"{antecedentes} incidente(s) previo(s)",
            },
            {
                "nombre": "asociaciones_criminales",
                "peso": 20,
                "score": s_asociaciones,
                "maximo": 20,
                "descripcion": f"{asociaciones} asociacion(es) criminal(es)",
            },
            {
                "nombre": "zona_riesgo",
                "peso": 15,
                "score": s_zona,
                "maximo": 15,
                "descripcion": f"Indice de zona: {zona_riesgo:.2f}",
            },
            {
                "nombre": "armas_reportadas",
                "peso": 15,
                "score": s_armas,
                "maximo": 15,
                "descripcion": f"{armas} arma(s) vinculada(s)",
            },
            {
                "nombre": "reincidencia",
                "peso": 15,
                "score": s_reincidencia,
                "maximo": 15,
                "descripcion": f"{reincidencia} reincidencia(s)",
            },
            {
                "nombre": "tipo_incidente",
                "peso": 10,
                "score": s_tipo,
                "maximo": 10,
                "descripcion": f"Tipo: {tipo_incidente}",
            },
        ]

        return {
            "persona_id": persona_data.get("persona_id"),
            "score": total,
            "nivel": _nivel(total),
            "factores": factores,
        }
