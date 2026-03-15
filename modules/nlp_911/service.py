"""NLP 911 service — Keyword-based incident classification for emergency calls."""
import re
from config import logger
from modules.nlp_911.models import ClassifyIncidentResponse

# ── Keyword dictionaries (Spanish emergency terms) ──

INCIDENT_KEYWORDS = {
    "homicidio": {
        "keywords": ["muerto", "muerta", "cadaver", "cadáver", "mataron", "asesinaron", "sin vida", "baleado", "apuñalado", "degollado"],
        "prioridad_base": 1, "subtipo": "muerte_violenta",
        "recursos": ["patrulla", "ambulancia", "criminalistica", "ministerio_publico"]
    },
    "secuestro": {
        "keywords": ["secuestro", "secuestraron", "me tienen", "no me dejan salir", "piden rescate", "levantaron", "privado de libertad"],
        "prioridad_base": 1, "subtipo": "privacion_libertad",
        "recursos": ["patrulla", "grupo_especial", "negociador"]
    },
    "violencia_domestica": {
        "keywords": ["me golpea", "me pega", "violencia", "mi esposo", "mi pareja", "me amenaza", "golpeando", "maltrato", "agresion"],
        "prioridad_base": 2, "subtipo": "violencia_familiar",
        "recursos": ["patrulla", "ambulancia", "trabajo_social"]
    },
    "robo": {
        "keywords": ["robo", "robaron", "asalto", "asaltaron", "atraco", "me quitaron", "ladron", "ladrón", "despojaron"],
        "prioridad_base": 2, "subtipo": "robo_generico",
        "recursos": ["patrulla"]
    },
    "armas": {
        "keywords": ["arma", "pistola", "disparo", "disparos", "balazo", "balazos", "tiros", "rifle", "cuerno", "fusca", "fierro", "metralleta"],
        "prioridad_base": 1, "subtipo": "portacion_uso_arma",
        "recursos": ["patrulla", "grupo_especial", "ambulancia"]
    },
    "accidente_transito": {
        "keywords": ["choque", "accidente", "volcadura", "atropellado", "atropellaron", "colision", "carambola", "volcó"],
        "prioridad_base": 2, "subtipo": "accidente_vehicular",
        "recursos": ["patrulla", "ambulancia", "transito", "bomberos"]
    },
    "incendio": {
        "keywords": ["incendio", "fuego", "llamas", "quemando", "humo", "arde", "combustion", "explosión", "explosion"],
        "prioridad_base": 1, "subtipo": "incendio_explosion",
        "recursos": ["bomberos", "ambulancia", "proteccion_civil"]
    },
    "crisis_salud_mental": {
        "keywords": ["suicidio", "suicidarse", "quitarse la vida", "tirarse", "cortarse", "pastillas", "crisis nerviosa", "delirio"],
        "prioridad_base": 1, "subtipo": "intento_suicidio",
        "recursos": ["ambulancia", "psicologo", "patrulla"]
    },
    "desaparicion": {
        "keywords": ["desaparecido", "desaparecida", "no llega", "no contesta", "no aparece", "se perdió", "extraviado", "extraviada"],
        "prioridad_base": 2, "subtipo": "persona_desaparecida",
        "recursos": ["patrulla", "busqueda"]
    },
    "riña": {
        "keywords": ["pelea", "riña", "golpes", "peleando", "pleito", "bronca", "altercado", "agresión"],
        "prioridad_base": 3, "subtipo": "altercado_publico",
        "recursos": ["patrulla"]
    },
    "drogas": {
        "keywords": ["drogas", "narcomenudeo", "narco", "marihuana", "coca", "cristal", "metanfetamina", "laboratorio clandestino"],
        "prioridad_base": 2, "subtipo": "narcotrafico",
        "recursos": ["patrulla", "grupo_especial"]
    },
}

STRESS_KEYWORDS = {
    "alto": ["ayuda", "por favor", "rápido", "rapido", "urgente", "emergencia", "auxilio", "socorro", "ya viene", "me va a matar"],
    "medio": ["necesito", "vengan", "manden", "pueden venir", "algo pasó"],
    "bajo": ["quiero reportar", "para informar", "quisiera", "buenas"],
}

EMOTION_KEYWORDS = {
    "panico": ["ayuda", "auxilio", "socorro", "no puedo", "me va a matar", "viene armado"],
    "susurro": ["no puedo hablar", "escondida", "escondido", "bajito", "susurro"],
    "agresividad": ["maldito", "pendejo", "hijo de", "chinguen", "pinche", "matenlo"],
    "confusion": ["no sé qué pasó", "no entiendo", "creo que", "parece que", "no estoy seguro"],
    "calma": ["quisiera reportar", "buenas", "para informar", "quiero hacer una denuncia"],
}


class NLP911Service:
    """Classify 911 emergency call text into incident type, priority, and emotional state."""

    def classify_incident(self, texto: str) -> ClassifyIncidentResponse:
        text_lower = texto.lower().strip()
        if not text_lower:
            return self._empty_response()

        # Find matching incident types and their keyword hits
        matches = []
        all_keywords_found = []
        for tipo, config in INCIDENT_KEYWORDS.items():
            found = [kw for kw in config["keywords"] if kw in text_lower]
            if found:
                matches.append((tipo, config, len(found), found))
                all_keywords_found.extend(found)

        if not matches:
            return ClassifyIncidentResponse(
                tipo_incidente="otros",
                subtipo="sin_clasificar",
                prioridad=4,
                confidence=0.3,
                palabras_clave=[],
                estado_emocional=self._detect_emotion(text_lower),
                nivel_estres=self._detect_stress(text_lower),
                recursos_sugeridos=["patrulla"],
            )

        # Best match by keyword count
        matches.sort(key=lambda m: m[2], reverse=True)
        best_tipo, best_config, hit_count, keywords = matches[0]

        # Confidence based on keyword density
        confidence = min(0.5 + (hit_count * 0.15), 0.98)

        # Adjust priority based on stress level
        estres = self._detect_stress(text_lower)
        prioridad = best_config["prioridad_base"]
        if estres == "alto" and prioridad > 1:
            prioridad -= 1

        return ClassifyIncidentResponse(
            tipo_incidente=best_tipo,
            subtipo=best_config["subtipo"],
            prioridad=prioridad,
            confidence=round(confidence, 2),
            palabras_clave=list(set(all_keywords_found)),
            estado_emocional=self._detect_emotion(text_lower),
            nivel_estres=estres,
            recursos_sugeridos=best_config["recursos"],
        )

    def _detect_stress(self, text: str) -> str:
        for level in ["alto", "medio", "bajo"]:
            if any(kw in text for kw in STRESS_KEYWORDS[level]):
                return level
        return "medio"

    def _detect_emotion(self, text: str) -> str:
        for emotion, keywords in EMOTION_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return emotion
        return "calma"

    def _empty_response(self) -> ClassifyIncidentResponse:
        return ClassifyIncidentResponse(
            tipo_incidente="otros", subtipo="sin_texto", prioridad=5,
            confidence=0.0, palabras_clave=[], estado_emocional="desconocido",
            nivel_estres="desconocido", recursos_sugeridos=[],
        )


nlp_911_service = NLP911Service()
