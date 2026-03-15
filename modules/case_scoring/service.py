"""Case scoring service — Weighted multi-factor case prioritization."""
from typing import List, Dict
from config import logger
from modules.case_scoring.models import (
    CaseData, CaseScoreResult, ScoreFactor,
    BatchScoreRequest, BatchScoreResponse,
)

# ── Crime severity weights ──

CRIME_SEVERITY = {
    "homicidio": 1.0, "secuestro": 0.95, "desaparicion_forzada": 0.90,
    "violacion": 0.90, "armas": 0.80, "narcomenudeo": 0.70,
    "robo_violento": 0.75, "robo": 0.50, "violencia_domestica": 0.65,
    "accidente_transito": 0.40, "riña": 0.30, "otros": 0.20,
}

# ── Scoring weights ──

FACTOR_WEIGHTS = {
    "gravedad_delito": 0.25,
    "urgencia_sla": 0.20,
    "evidencia_disponible": 0.15,
    "vulnerabilidad_victima": 0.15,
    "complejidad": 0.10,
    "reincidencia": 0.10,
    "zona_riesgo": 0.05,
}

RECOMMENDATIONS = {
    "critica": "Asignar equipo completo inmediatamente. Prioridad máxima en MP.",
    "alta": "Asignar investigador senior. Seguimiento diario requerido.",
    "media": "Asignación estándar. Seguimiento semanal.",
    "baja": "Puede procesarse en orden regular. Verificar SLA periódicamente.",
}


class CaseScoringService:
    """Multi-factor case priority scoring engine."""

    def score_case(self, caso: CaseData) -> CaseScoreResult:
        factores: List[ScoreFactor] = []

        # 1. Crime severity
        severity = CRIME_SEVERITY.get(caso.tipo_delito, 0.3)
        factores.append(self._factor("gravedad_delito", severity))

        # 2. SLA urgency
        sla_val = 0.0
        if caso.sla_restante_horas is not None:
            if caso.sla_restante_horas <= 24:
                sla_val = 1.0
            elif caso.sla_restante_horas <= 72:
                sla_val = 0.7
            elif caso.sla_restante_horas <= 168:
                sla_val = 0.4
            else:
                sla_val = 0.2
        factores.append(self._factor("urgencia_sla", sla_val))

        # 3. Evidence availability
        ev_score = min(1.0, (
            (0.3 if caso.tiene_video else 0) +
            (0.3 if caso.tiene_testigos else 0) +
            min(caso.num_evidencias * 0.1, 0.4)
        ))
        factores.append(self._factor("evidencia_disponible", ev_score))

        # 4. Victim vulnerability
        vuln = 0.0
        if caso.victimas_menores:
            vuln = 1.0
        elif caso.tiene_arma:
            vuln = 0.7
        factores.append(self._factor("vulnerabilidad_victima", vuln))

        # 5. Complexity
        comp = min(1.0, caso.num_sujetos * 0.2 + (0.3 if caso.dias_abierto > 30 else 0))
        factores.append(self._factor("complejidad", comp))

        # 6. Recidivism
        factores.append(self._factor("reincidencia", 1.0 if caso.reincidente else 0.0))

        # 7. Risk zone
        factores.append(self._factor("zona_riesgo", 1.0 if caso.zona_riesgo else 0.0))

        total = round(sum(f.contribucion for f in factores), 3)
        prioridad = self._classify_priority(total)

        return CaseScoreResult(
            carpeta_id=caso.carpeta_id,
            score_total=total,
            prioridad=prioridad,
            factores=factores,
            recomendacion=RECOMMENDATIONS[prioridad],
        )

    def score_batch(self, req: BatchScoreRequest) -> BatchScoreResponse:
        results = [self.score_case(c) for c in req.casos]
        dist = {"critica": 0, "alta": 0, "media": 0, "baja": 0}
        for r in results:
            dist[r.prioridad] += 1
        avg = sum(r.score_total for r in results) / len(results) if results else 0

        return BatchScoreResponse(
            resultados=results,
            promedio_score=round(avg, 3),
            distribucion=dist,
        )

    def _factor(self, name: str, value: float) -> ScoreFactor:
        weight = FACTOR_WEIGHTS[name]
        return ScoreFactor(
            factor=name, peso=weight,
            valor=round(value, 3),
            contribucion=round(value * weight, 4),
        )

    @staticmethod
    def _classify_priority(score: float) -> str:
        if score >= 0.7:
            return "critica"
        elif score >= 0.5:
            return "alta"
        elif score >= 0.3:
            return "media"
        return "baja"


case_scoring_service = CaseScoringService()
