"""Investigator AI service — Case summarization, judicial drafts (CNPP), next steps."""
from datetime import datetime
from typing import List, Dict
from config import logger
from modules.investigator_ai.models import (
    CaseSummaryRequest, CaseSummaryResponse,
    JudicialDraftRequest, JudicialDraftResponse,
    NextStepsRequest, NextStepsResponse, InvestigationStep,
    MPPackageRequest, MPPackageResponse, MPPackageDocument,
)

# ── CNPP Article references by action type ──

CNPP_ARTICLES = {
    "detencion": ["Art. 146 CNPP - Detención en flagrancia", "Art. 147 CNPP - Supuestos de flagrancia"],
    "registro": ["Art. 282 CNPP - Registro de personas", "Art. 283 CNPP - Inspección de vehículos"],
    "cadena_custodia": ["Art. 227 CNPP - Cadena de custodia", "Art. 228 CNPP - Responsables"],
    "peritaje": ["Art. 368 CNPP - Dictamen pericial", "Art. 369 CNPP - Requisitos del dictamen"],
    "declaracion": ["Art. 308 CNPP - Declaración del imputado", "Art. 360 CNPP - Testimonio"],
    "cateo": ["Art. 282 CNPP - Orden de cateo", "Art. 285 CNPP - Reglas del cateo"],
    "arraigo": ["Art. 168 CNPP - Arraigo", "Art. 16 Constitucional"],
    "medidas_cautelares": ["Art. 153 CNPP - Tipos de medidas", "Art. 155 CNPP - Medidas cautelares"],
    "accion_penal": ["Art. 211 CNPP - Etapa de investigación", "Art. 335 CNPP - Acusación"],
}

PROTOCOL_BY_CRIME = {
    "homicidio": "Protocolo de Actuación para Homicidio Doloso (Protocolo de Minnesota)",
    "secuestro": "Protocolo Nacional de Actuación para Secuestro",
    "violencia_domestica": "Protocolo para Atención a Víctimas de Violencia de Género",
    "desaparicion": "Protocolo Homologado de Búsqueda de Personas Desaparecidas",
    "robo": "Protocolo de Primer Respondiente",
    "armas": "Protocolo de Actuación de Cadena de Custodia en Armas de Fuego",
    "narcomenudeo": "Protocolo de Actuación en Materia de Narcomenudeo",
    "default": "Protocolo Nacional de Primer Respondiente",
}

INVESTIGATION_TEMPLATES: Dict[str, List[Dict]] = {
    "homicidio": [
        {"accion": "Preservar escena del crimen y establecer perímetro", "responsable": "policia", "prioridad": "inmediata", "plazo": 2},
        {"accion": "Documentación fotográfica y videográfica completa de la escena", "responsable": "perito", "prioridad": "inmediata", "plazo": 4},
        {"accion": "Levantamiento de indicios y evidencia física", "responsable": "perito", "prioridad": "inmediata", "plazo": 6},
        {"accion": "Entrevista a testigos presenciales", "responsable": "policia", "prioridad": "alta", "plazo": 12},
        {"accion": "Solicitar cámaras de videovigilancia en la zona", "responsable": "analista", "prioridad": "alta", "plazo": 24},
        {"accion": "Análisis balístico de proyectiles y casquillos", "responsable": "perito", "prioridad": "alta", "plazo": 48},
        {"accion": "Solicitar registros de CDR de teléfonos encontrados", "responsable": "mp", "prioridad": "alta", "plazo": 48},
        {"accion": "Cruce con bases de datos biométricas (MIA)", "responsable": "analista", "prioridad": "media", "plazo": 72},
    ],
    "secuestro": [
        {"accion": "Activar Protocolo Alba/Amber según aplique", "responsable": "mp", "prioridad": "inmediata", "plazo": 1},
        {"accion": "Rastreo de última ubicación conocida de la víctima", "responsable": "analista", "prioridad": "inmediata", "plazo": 2},
        {"accion": "Análisis de CDR del teléfono de la víctima", "responsable": "analista", "prioridad": "inmediata", "plazo": 4},
        {"accion": "Entrevista a familia y círculo cercano", "responsable": "policia", "prioridad": "inmediata", "plazo": 6},
        {"accion": "Solicitar videovigilancia en puntos clave", "responsable": "analista", "prioridad": "alta", "plazo": 12},
        {"accion": "Monitoreo de redes sociales de la víctima", "responsable": "analista", "prioridad": "alta", "plazo": 24},
    ],
    "default": [
        {"accion": "Recabar declaración inicial de la víctima/denunciante", "responsable": "mp", "prioridad": "inmediata", "plazo": 4},
        {"accion": "Preservar y documentar evidencia disponible", "responsable": "perito", "prioridad": "alta", "plazo": 12},
        {"accion": "Identificar y entrevistar testigos", "responsable": "policia", "prioridad": "alta", "plazo": 24},
        {"accion": "Solicitar registros de videovigilancia", "responsable": "analista", "prioridad": "media", "plazo": 48},
        {"accion": "Cruce de datos en bases disponibles", "responsable": "analista", "prioridad": "media", "plazo": 72},
    ],
}


class InvestigatorAIService:
    """AI-assisted investigation: case summaries, judicial drafts, and next steps."""

    def summarize_case(self, req: CaseSummaryRequest) -> CaseSummaryResponse:
        n_narrativas = len(req.narrativas)
        n_evidencias = len(req.evidencias)
        n_sujetos = len(req.sujetos)
        delitos_str = ", ".join(req.delitos) if req.delitos else "sin clasificar"

        resumen = (
            f"Carpeta de investigación #{req.carpeta_id}. "
            f"Delito(s): {delitos_str}. "
            f"Se cuenta con {n_narrativas} narrativa(s), {n_evidencias} evidencia(s) "
            f"y {n_sujetos} sujeto(s) identificado(s)."
        )

        hechos = []
        for i, n in enumerate(req.narrativas[:5]):
            hechos.append(f"Narrativa {i+1}: {n[:200]}")

        lineas = self._suggest_lines(req.delitos, n_evidencias, n_sujetos)
        pendiente = self._identify_pending(req)
        fortalezas, debilidades = self._evaluate_case(req)

        conclusion = "Caso con elementos suficientes para continuar investigación." \
            if len(fortalezas) >= len(debilidades) \
            else "Caso requiere fortalecimiento probatorio antes de ejercer acción penal."

        return CaseSummaryResponse(
            resumen_ejecutivo=resumen,
            hechos_clave=hechos,
            lineas_investigacion=lineas,
            evidencia_pendiente=pendiente,
            fortalezas=fortalezas,
            debilidades=debilidades,
            conclusion=conclusion,
        )

    def generate_judicial_draft(self, req: JudicialDraftRequest) -> JudicialDraftResponse:
        fecha = req.fecha or datetime.now().strftime("%d de %B de %Y")
        datos = req.datos_caso

        templates = {
            "dictamen": self._draft_dictamen,
            "oficio_canalizacion": self._draft_oficio,
            "solicitud_peritaje": self._draft_solicitud_peritaje,
            "informe_policial": self._draft_informe_policial,
            "acta_circunstanciada": self._draft_acta,
        }

        gen = templates.get(req.tipo_documento, self._draft_generic)
        titulo, contenido, arts = gen(req, fecha, datos)

        fundamentos = []
        for key in ["cadena_custodia", "declaracion"]:
            fundamentos.extend(CNPP_ARTICLES.get(key, []))

        return JudicialDraftResponse(
            tipo_documento=req.tipo_documento,
            titulo=titulo,
            contenido=contenido,
            fundamento_legal=fundamentos,
            articulos_cnpp=arts,
        )

    def suggest_next_steps(self, req: NextStepsRequest) -> NextStepsResponse:
        template = INVESTIGATION_TEMPLATES.get(req.tipo_delito, INVESTIGATION_TEMPLATES["default"])
        realizadas_lower = [a.lower() for a in req.acciones_realizadas]

        pasos: List[InvestigationStep] = []
        for i, step in enumerate(template):
            if not any(step["accion"].lower()[:30] in a for a in realizadas_lower):
                pasos.append(InvestigationStep(
                    paso=i + 1,
                    accion=step["accion"],
                    justificacion=f"Paso requerido por protocolo para {req.tipo_delito}",
                    prioridad=step["prioridad"],
                    responsable=step["responsable"],
                    plazo_horas=step["plazo"],
                ))

        protocolo = PROTOCOL_BY_CRIME.get(req.tipo_delito, PROTOCOL_BY_CRIME["default"])
        arts = CNPP_ARTICLES.get("accion_penal", [])

        return NextStepsResponse(
            pasos_sugeridos=pasos,
            protocolo_aplicable=protocolo,
            articulos_referencia=arts,
        )

    def generate_mp_package(self, req: MPPackageRequest) -> MPPackageResponse:
        docs: List[MPPackageDocument] = []
        fecha = datetime.now().strftime("%d de %B de %Y")

        # 1. Acta circunstanciada
        docs.append(MPPackageDocument(
            tipo="acta_circunstanciada",
            titulo=f"Acta Circunstanciada - Carpeta {req.carpeta_id}",
            contenido=self._gen_acta_content(req, fecha),
        ))

        # 2. Informe policial
        docs.append(MPPackageDocument(
            tipo="informe_policial",
            titulo=f"Informe Policial Homologado - Carpeta {req.carpeta_id}",
            contenido=self._gen_informe_content(req, fecha),
        ))

        # 3. Cadena de custodia
        docs.append(MPPackageDocument(
            tipo="cadena_custodia",
            titulo=f"Registro de Cadena de Custodia - Carpeta {req.carpeta_id}",
            contenido=self._gen_custodia_content(req, fecha),
        ))

        # 4. Dictamen pericial (if evidence present)
        if req.evidencias:
            docs.append(MPPackageDocument(
                tipo="dictamen_pericial",
                titulo=f"Solicitud de Dictamen Pericial - Carpeta {req.carpeta_id}",
                contenido=self._gen_peritaje_content(req, fecha),
            ))

        # Checklist
        checklist = {
            "acta_circunstanciada": True,
            "informe_policial": True,
            "cadena_custodia": True,
            "dictamen_pericial": len(req.evidencias) > 0,
            "declaraciones_testigos": len(req.sujetos) > 0,
            "medidas_cautelares": False,
            "orden_aprehension": False,
        }

        obs = []
        if not req.sujetos:
            obs.append("No se han identificado sujetos. Se requiere fortalecer líneas de investigación.")
        if not req.evidencias:
            obs.append("No hay evidencias registradas. El caso carece de sustento probatorio.")

        return MPPackageResponse(documentos=docs, checklist_completitud=checklist, observaciones=obs)

    # ── Private helpers ──

    def _suggest_lines(self, delitos: List[str], n_ev: int, n_suj: int) -> List[str]:
        lines = []
        if n_suj == 0:
            lines.append("Identificación de probables responsables mediante análisis de evidencia")
        if n_ev < 3:
            lines.append("Ampliación del acervo probatorio (videovigilancia, testimonios, peritajes)")
        lines.append("Análisis de vínculos y relaciones entre sujetos involucrados")
        if any(d in ["homicidio", "secuestro", "armas"] for d in delitos):
            lines.append("Coordinación con unidades especializadas (SEIDO/FGR)")
        return lines

    def _identify_pending(self, req: CaseSummaryRequest) -> List[str]:
        pending = []
        if not req.evidencias:
            pending.append("Recolección de evidencia física o digital")
        if not req.sujetos:
            pending.append("Identificación de personas involucradas")
        pending.append("Dictamen pericial de evidencias recolectadas")
        pending.append("Análisis de videovigilancia en zona de los hechos")
        return pending

    def _evaluate_case(self, req: CaseSummaryRequest):
        strengths, weaknesses = [], []
        if len(req.evidencias) >= 3:
            strengths.append(f"Acervo probatorio con {len(req.evidencias)} evidencias")
        else:
            weaknesses.append("Evidencia insuficiente")
        if len(req.sujetos) > 0:
            strengths.append(f"{len(req.sujetos)} sujeto(s) identificado(s)")
        else:
            weaknesses.append("Sin sujetos identificados")
        if len(req.narrativas) > 0:
            strengths.append("Narrativa de hechos documentada")
        else:
            weaknesses.append("Sin narrativa de hechos")
        return strengths, weaknesses

    def _draft_dictamen(self, req, fecha, datos):
        titulo = f"Dictamen - Carpeta {req.carpeta_id}"
        contenido = (
            f"{req.fiscalia}\n\n"
            f"DICTAMEN\n\nFecha: {fecha}\n"
            f"Carpeta de Investigación: {req.carpeta_id}\n"
            f"Agente del MP: {req.agente_mp or 'Por asignar'}\n\n"
            f"ANTECEDENTES:\n{datos.get('antecedentes', 'Por describir')}\n\n"
            f"ANÁLISIS:\n{datos.get('analisis', 'Por realizar')}\n\n"
            f"CONCLUSIONES:\n{datos.get('conclusiones', 'Pendiente de determinación')}"
        )
        return titulo, contenido, CNPP_ARTICLES.get("peritaje", [])

    def _draft_oficio(self, req, fecha, datos):
        titulo = f"Oficio de Canalización - Carpeta {req.carpeta_id}"
        contenido = (
            f"{req.fiscalia}\nOficio de Canalización\n\nFecha: {fecha}\n"
            f"Carpeta: {req.carpeta_id}\n\n"
            f"Se canaliza a: {datos.get('destino', '[Unidad]')}\n"
            f"Motivo: {datos.get('motivo', '[Motivo de canalización]')}\n"
        )
        return titulo, contenido, CNPP_ARTICLES.get("accion_penal", [])

    def _draft_solicitud_peritaje(self, req, fecha, datos):
        titulo = f"Solicitud de Peritaje - Carpeta {req.carpeta_id}"
        contenido = (
            f"{req.fiscalia}\nSolicitud de Dictamen Pericial\n\nFecha: {fecha}\n"
            f"Carpeta: {req.carpeta_id}\n\n"
            f"Tipo de peritaje: {datos.get('tipo_peritaje', '[Tipo]')}\n"
            f"Evidencia a analizar: {datos.get('evidencia', '[Descripción]')}\n"
            f"Objetivo: {datos.get('objetivo', '[Objetivo del peritaje]')}\n"
        )
        return titulo, contenido, CNPP_ARTICLES.get("peritaje", [])

    def _draft_informe_policial(self, req, fecha, datos):
        titulo = f"Informe Policial Homologado - Carpeta {req.carpeta_id}"
        contenido = (
            f"INFORME POLICIAL HOMOLOGADO\n\nFecha: {fecha}\n"
            f"Carpeta: {req.carpeta_id}\n\n"
            f"I. DATOS DE IDENTIFICACIÓN\n{datos.get('datos', '')}\n\n"
            f"II. NARRACIÓN DE LOS HECHOS\n{datos.get('narracion', '')}\n\n"
            f"III. INSPECCIÓN DEL LUGAR\n{datos.get('inspeccion', '')}\n\n"
            f"IV. DESCRIPCIÓN DE EVIDENCIA\n{datos.get('evidencia', '')}\n\n"
            f"V. ENTREVISTAS\n{datos.get('entrevistas', '')}"
        )
        return titulo, contenido, CNPP_ARTICLES.get("registro", [])

    def _draft_acta(self, req, fecha, datos):
        titulo = f"Acta Circunstanciada - Carpeta {req.carpeta_id}"
        contenido = (
            f"ACTA CIRCUNSTANCIADA\n\nEn la ciudad de {datos.get('ciudad', '[Ciudad]')}, "
            f"siendo las {datos.get('hora', '[Hora]')} horas del día {fecha}, "
            f"el/la suscrito/a {req.agente_mp or '[Agente MP]'}, adscrito a {req.fiscalia}, "
            f"hace constar lo siguiente:\n\n"
            f"HECHOS:\n{datos.get('hechos', '[Descripción de hechos]')}\n\n"
            f"DILIGENCIAS:\n{datos.get('diligencias', '[Diligencias realizadas]')}\n\n"
            f"DETERMINACIÓN:\n{datos.get('determinacion', '[Determinación]')}"
        )
        return titulo, contenido, CNPP_ARTICLES.get("accion_penal", [])

    def _draft_generic(self, req, fecha, datos):
        titulo = f"Documento - Carpeta {req.carpeta_id}"
        contenido = f"{req.fiscalia}\n\nFecha: {fecha}\nCarpeta: {req.carpeta_id}\n\n{datos}"
        return titulo, contenido, []

    def _gen_acta_content(self, req, fecha):
        delitos = ", ".join(req.delitos) if req.delitos else "por determinar"
        return (
            f"ACTA CIRCUNSTANCIADA\n\n{req.fiscalia}\nFecha: {fecha}\n"
            f"Carpeta: {req.carpeta_id}\nDelito(s): {delitos}\n\n"
            f"HECHOS:\n{req.narrativa[:500] if req.narrativa else 'Sin narrativa'}\n\n"
            f"Sujetos involucrados: {len(req.sujetos)}\n"
            f"Evidencias: {len(req.evidencias)}"
        )

    def _gen_informe_content(self, req, fecha):
        return (
            f"INFORME POLICIAL HOMOLOGADO\n\nFecha: {fecha}\n"
            f"Carpeta: {req.carpeta_id}\n\n"
            f"NARRACIÓN DE LOS HECHOS:\n{req.narrativa[:500] if req.narrativa else 'Pendiente'}\n\n"
            f"SUJETOS IDENTIFICADOS: {len(req.sujetos)}\n"
            f"EVIDENCIAS RECOLECTADAS: {len(req.evidencias)}"
        )

    def _gen_custodia_content(self, req, fecha):
        lines = [f"REGISTRO DE CADENA DE CUSTODIA\nFecha: {fecha}\nCarpeta: {req.carpeta_id}\n"]
        for i, ev in enumerate(req.evidencias[:20]):
            lines.append(f"  {i+1}. {ev.get('tipo', 'N/A')} — {ev.get('descripcion', 'Sin descripción')}")
        return "\n".join(lines)

    def _gen_peritaje_content(self, req, fecha):
        tipos = set(ev.get("tipo", "general") for ev in req.evidencias)
        return (
            f"SOLICITUD DE DICTAMEN PERICIAL\nFecha: {fecha}\n"
            f"Carpeta: {req.carpeta_id}\n\n"
            f"Se solicita dictamen en las siguientes materias: {', '.join(tipos)}\n"
            f"Total de evidencias a analizar: {len(req.evidencias)}"
        )


investigator_ai_service = InvestigatorAIService()
