"""
Analysis Service — Semantic Report Generation
Template-based with optional LLM enhancement via Ollama
"""
import httpx
from datetime import datetime, timezone
from typing import Dict, Any, List

from config import settings, logger
from .models import SemanticReportRequest, SemanticReportResponse


class AnalysisService:

    def _build_template_report(self, req: SemanticReportRequest) -> str:
        """Generate structured report without LLM."""
        lines: List[str] = []
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        lines.append("# Informe Semántico de Investigación OSINT")
        lines.append(f"\n**Fecha de generación:** {ts}\n")

        # Section 1: Search Parameters
        lines.append("## 1. Parámetros de Búsqueda\n")
        if req.search_params:
            for k, v in req.search_params.items():
                if v:
                    lines.append(f"- **{k}:** {v}")
        else:
            lines.append("- No se proporcionaron parámetros específicos.")

        # Section 2: Keywords
        lines.append("\n## 2. Palabras Clave\n")
        if req.keywords:
            lines.append(", ".join(f"`{kw}`" for kw in req.keywords))
        else:
            lines.append("- Sin palabras clave específicas.")

        # Section 3: Results Summary
        lines.append("\n## 3. Resultados Obtenidos\n")
        lines.append("| Plataforma | Resultados |")
        lines.append("|------------|-----------|")
        total = 0
        for plat, count in req.platform_stats.items():
            lines.append(f"| {plat} | {count} |")
            total += count
        lines.append(f"| **Total** | **{total}** |")

        # Section 4: Effectiveness
        lines.append("\n## 4. Efectividad por Fuente\n")
        if total > 0 and req.platform_stats:
            sorted_plats = sorted(req.platform_stats.items(), key=lambda x: x[1], reverse=True)
            for plat, count in sorted_plats:
                pct = (count / total) * 100 if total > 0 else 0
                bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
                lines.append(f"- **{plat}:** {bar} {pct:.1f}% ({count} resultados)")
        else:
            lines.append("- Sin datos suficientes para calcular efectividad.")

        # Section 5: Keyword Correlation
        lines.append("\n## 5. Correlación Parámetros-Resultados\n")
        if req.results_summary:
            top_results = req.results_summary.get("top_results", [])
            if top_results:
                lines.append("### Resultados más relevantes:\n")
                for i, result in enumerate(top_results[:10], 1):
                    title = result.get("title", result.get("titulo", "Sin título"))
                    source = result.get("source", result.get("fuente", "Desconocida"))
                    lines.append(f"{i}. **{title}** — _{source}_")

            kw_matches = req.results_summary.get("keyword_matches", {})
            if kw_matches:
                lines.append("\n### Aparición de palabras clave:\n")
                for kw, count in kw_matches.items():
                    lines.append(f"- `{kw}`: {count} menciones")
        else:
            lines.append("- Sin resumen de resultados proporcionado.")

        # Section 6: Patterns
        lines.append("\n## 6. Patrones Detectados\n")
        if req.platform_stats:
            active = [p for p, c in req.platform_stats.items() if c > 0]
            empty = [p for p, c in req.platform_stats.items() if c == 0]
            if active:
                lines.append(f"- **Fuentes activas:** {', '.join(active)}")
            if empty:
                lines.append(f"- **Fuentes sin resultados:** {', '.join(empty)}")
            if len(active) > 3:
                lines.append("- Presencia digital amplia detectada (más de 3 plataformas con resultados)")
            elif len(active) == 0:
                lines.append("- Sin presencia digital detectada en las fuentes consultadas")
        else:
            lines.append("- Sin datos de plataformas para análisis de patrones.")

        # Section 7: Recommendations
        lines.append("\n## 7. Recomendaciones\n")
        recommendations = []
        if req.platform_stats:
            empty = [p for p, c in req.platform_stats.items() if c == 0]
            if empty:
                recommendations.append(f"- Ampliar búsqueda en: {', '.join(empty[:3])}")
        if req.keywords and len(req.keywords) < 3:
            recommendations.append("- Agregar más palabras clave para mejorar precisión")
        recommendations.append("- Verificar resultados manualmente antes de incluir en informe final")
        recommendations.append("- Correlacionar con bases de datos internas (Dossier, Carpetas)")
        for r in recommendations:
            lines.append(r)

        lines.append("\n---\n*Informe generado automáticamente por Centinela PCE — Módulo SANS*")
        return "\n".join(lines)

    async def generate_report(self, req: SemanticReportRequest) -> SemanticReportResponse:
        """Generate semantic report. Try LLM first, fallback to template."""
        ts = datetime.now(timezone.utc).isoformat()

        # Try LLM enhancement
        try:
            prompt = self._build_llm_prompt(req)
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    settings.llm_api_url,
                    json={
                        "model": settings.llm_model,
                        "prompt": prompt,
                        "stream": False,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    report = data.get("response", "")
                    if report and len(report) > 100:
                        return SemanticReportResponse(
                            report_markdown=report,
                            generated_at=ts,
                            method="llm",
                        )
        except Exception as e:
            logger.info(f"LLM not available for semantic report, using template: {e}")

        # Fallback: template-based
        report = self._build_template_report(req)
        return SemanticReportResponse(
            report_markdown=report,
            generated_at=ts,
            method="template",
        )

    def _build_llm_prompt(self, req: SemanticReportRequest) -> str:
        params_str = "\n".join(f"- {k}: {v}" for k, v in req.search_params.items() if v)
        kw_str = ", ".join(req.keywords) if req.keywords else "ninguna"
        stats_str = "\n".join(f"- {p}: {c} resultados" for p, c in req.platform_stats.items())

        return f"""Genera un informe semántico profesional de investigación OSINT en español.
El informe debe correlacionar los parámetros de búsqueda con los resultados obtenidos.

PARÁMETROS DE BÚSQUEDA:
{params_str}

PALABRAS CLAVE: {kw_str}

RESULTADOS POR PLATAFORMA:
{stats_str}

El informe debe tener estas secciones en formato Markdown:
1. Resumen Ejecutivo (2-3 oraciones)
2. Análisis de Resultados por Plataforma
3. Correlación entre Parámetros y Hallazgos
4. Patrones Detectados
5. Evaluación de Riesgo/Relevancia
6. Recomendaciones de Seguimiento

Usa un tono profesional forense. No inventes datos que no se proporcionaron."""


analysis_service = AnalysisService()
