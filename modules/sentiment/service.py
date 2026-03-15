"""Sentiment analysis service — keyword-based + LLM fallback (G2: Typed Interaction Analysis)"""
from typing import List, Dict, Any
import re
import requests
import json

from config import settings, logger
from modules.sentiment.models import SentimentItem, SentimentResponse

LLM_API_URL = settings.llm_api_url
LLM_MODEL = settings.llm_model
LLM_TIMEOUT = settings.llm_timeout

# ── Keyword-based sentiment dictionaries (Spanish) ──

_OFFENSIVE_WORDS = {
    # Insultos
    "pendejo", "pendeja", "idiota", "estupido", "estupida", "imbecil", "tarado", "tarada",
    "baboso", "babosa", "menso", "mensa", "tonto", "tonta", "burro", "burra", "animal",
    "cerdo", "cerda", "puerco", "puerca", "zorra", "perra", "puta", "puto", "cabron",
    "cabrona", "maldito", "maldita", "desgraciado", "desgraciada", "hijo de puta",
    "hdp", "ptm", "chinga", "chingada", "chingado", "verga", "culero", "culera",
    "mamada", "joto", "maricon", "pinche", "naco", "naca", "corriente", "mugroso",
    # Amenazas / odio
    "matar", "matarte", "muerte", "muere", "morir", "amenaza", "golpear", "golpearte",
    "romper la cara", "acabar contigo", "te voy a", "vas a pagar", "venganza",
    "odio", "desprecio", "asco", "basura", "escoria", "lacra", "rata", "alimaña",
}

_NEGATIVE_WORDS = {
    "malo", "mala", "terrible", "horrible", "pesimo", "pesima", "feo", "fea",
    "peligro", "peligroso", "peligrosa", "miedo", "temor", "triste", "tristeza",
    "dolor", "sufrir", "sufrimiento", "dañar", "daño", "destruir", "destruccion",
    "fracaso", "fracasar", "perder", "perdida", "lamentar", "arrepentir",
    "preocupar", "preocupante", "problema", "problemas", "crisis", "grave",
    "peor", "decepcion", "decepcionar", "frustrar", "frustrante", "enojo",
    "coraje", "rabia", "furioso", "furiosa", "molesto", "molesta", "indignante",
    "injusto", "injusta", "abuso", "abusar", "violencia", "violento", "violenta",
    "robo", "robar", "crimen", "criminal", "delito", "delincuente", "inseguro",
    "insegura", "inseguridad", "corrupto", "corrupcion", "fraude", "estafa",
}

_POSITIVE_WORDS = {
    "bueno", "buena", "excelente", "genial", "feliz", "felicidad", "alegria",
    "maravilloso", "maravillosa", "increible", "fantastico", "fantastica",
    "hermoso", "hermosa", "bonito", "bonita", "lindo", "linda", "bello", "bella",
    "amor", "amar", "cariño", "querer", "adorar", "gracias", "agradecido",
    "agradecida", "bendicion", "bendecido", "esperanza", "optimismo", "exito",
    "exitoso", "exitosa", "logro", "lograr", "ganar", "victoria", "triunfo",
    "mejor", "perfecto", "perfecta", "magnifico", "magnifica", "brillante",
    "talento", "talentoso", "talentosa", "orgullo", "orgulloso", "orgullosa",
    "valiente", "fuerte", "grandioso", "grandiosa", "impresionante", "super",
    "bien", "bravo", "brava", "admirable", "positivo", "positiva",
}

_CATEGORY_MAP = {
    "insulto": {"pendejo", "pendeja", "idiota", "estupido", "estupida", "imbecil", "tarado",
                "baboso", "menso", "tonto", "burro", "cerdo", "puerco", "zorra", "perra",
                "puta", "puto", "cabron", "culero", "pinche", "naco", "corriente"},
    "amenaza": {"matar", "matarte", "muerte", "morir", "golpear", "golpearte", "romper la cara",
                "acabar contigo", "te voy a", "vas a pagar", "venganza", "amenaza"},
    "odio": {"odio", "desprecio", "asco", "basura", "escoria", "lacra", "rata", "alimaña"},
    "aprobacion": {"bueno", "excelente", "genial", "maravilloso", "increible", "fantastico",
                   "perfecto", "brillante", "bravo", "super", "admirable"},
    "violencia": {"violencia", "violento", "violenta", "golpear", "matar", "destruir",
                  "robo", "robar", "crimen", "criminal", "delito", "delincuente"},
}


def _normalize(text: str) -> str:
    """Lowercase + strip accents for matching."""
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'ñ': 'n', 'ü': 'u',
    }
    t = text.lower()
    for src, dst in replacements.items():
        t = t.replace(src, dst)
    return t


def classify_keyword(text: str) -> SentimentItem:
    """
    Classify a single text using keyword-based heuristics.
    No external LLM needed — fast and deterministic.
    """
    norm = _normalize(text)
    words = set(re.findall(r'\b\w+\b', norm))
    total_words = max(len(words), 1)

    off_hits = words & _OFFENSIVE_WORDS
    neg_hits = words & _NEGATIVE_WORDS
    pos_hits = words & _POSITIVE_WORDS

    # Also check multi-word phrases
    for phrase in ["hijo de puta", "romper la cara", "acabar contigo", "te voy a", "vas a pagar"]:
        if phrase in norm:
            off_hits.add(phrase)

    # Determine categories
    categorias = []
    for cat, cat_words in _CATEGORY_MAP.items():
        if words & cat_words:
            categorias.append(cat)

    # Classify
    off_count = len(off_hits)
    neg_count = len(neg_hits)
    pos_count = len(pos_hits)

    if off_count > 0:
        sentimiento = "ofensivo"
        score = min(1.0, off_count / total_words * 3)
    elif neg_count > pos_count:
        sentimiento = "negativo"
        score = min(1.0, neg_count / total_words * 2)
    elif pos_count > neg_count:
        sentimiento = "positivo"
        score = min(1.0, pos_count / total_words * 2)
    else:
        sentimiento = "neutral"
        score = 0.0

    return SentimentItem(
        text=text,
        sentimiento=sentimiento,
        score=round(score, 3),
        categorias=categorias,
    )


def analyze_texts_keyword(texts: List[str]) -> SentimentResponse:
    """
    Keyword-based batch analysis — no external dependencies.
    Returns structured SentimentResponse with counts.
    """
    resultados = []
    for text in texts:
        if not text or len(text.strip()) < 3:
            resultados.append(SentimentItem(text=text, sentimiento="neutral", score=0.0, categorias=[]))
        else:
            resultados.append(classify_keyword(text))

    off = sum(1 for r in resultados if r.sentimiento == "ofensivo")
    pos = sum(1 for r in resultados if r.sentimiento == "positivo")
    neg = sum(1 for r in resultados if r.sentimiento == "negativo")
    neu = sum(1 for r in resultados if r.sentimiento == "neutral")

    return SentimentResponse(
        resultados=resultados,
        total=len(resultados),
        ofensivos=off,
        positivos=pos,
        negativos=neg,
        neutrales=neu,
    )


def analyze_sentiment_batch(texts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Analyze sentiment for a batch of texts (comments, posts, etc.).
    Each text dict should have at least: { "text": str, "id": str|int }
    Returns the same dicts enriched with sentiment fields.
    """
    results = []
    for item in texts:
        text = item.get("text", "")
        if not text or len(text.strip()) < 3:
            results.append({**item, "sentimiento": "neutral", "confianza": 0, "ofensivo": False})
            continue

        analysis = _classify_single(text)
        results.append({**item, **analysis})

    return results


def _classify_single(text: str) -> Dict[str, Any]:
    """Classify a single text using LLM."""
    try:
        prompt = f"""Clasifica el sentimiento del siguiente texto de redes sociales.

Texto: "{text[:500]}"

IMPORTANTE:
1. Responde SOLAMENTE con un objeto JSON valido, sin texto adicional.
2. Usa comillas dobles para todas las cadenas.

El JSON debe tener exactamente estas propiedades:
- "sentimiento": string, uno de: "positivo", "negativo", "neutral", "ofensivo"
- "confianza": number entre 0 y 100
- "ofensivo": boolean, true si el texto contiene lenguaje ofensivo, amenazas, odio o insultos
- "emocion": string, la emocion dominante: "alegria", "enojo", "tristeza", "miedo", "sorpresa", "asco", "neutral"
- "resumen": string corto (max 20 palabras) describiendo el tono del mensaje

Responde SOLO el JSON."""

        payload = {
            "model": LLM_MODEL,
            "prompt": prompt,
            "stream": False
        }

        response = requests.post(
            LLM_API_URL,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=min(LLM_TIMEOUT, 30)
        )

        if response.status_code != 200:
            logger.error(f"Sentiment LLM error: {response.status_code}")
            return _default_sentiment()

        llm_response = response.json()
        analysis_text = llm_response.get("response", llm_response.get("output", ""))

        json_start = analysis_text.find('{')
        json_end = analysis_text.rfind('}') + 1

        if json_start >= 0 and json_end > json_start:
            result = json.loads(analysis_text[json_start:json_end])
            # Validate expected fields
            return {
                "sentimiento": result.get("sentimiento", "neutral"),
                "confianza": min(100, max(0, result.get("confianza", 50))),
                "ofensivo": bool(result.get("ofensivo", False)),
                "emocion": result.get("emocion", "neutral"),
                "resumen": result.get("resumen", ""),
            }

        return _default_sentiment()

    except Exception as e:
        logger.error(f"Sentiment analysis error: {e}")
        return _default_sentiment()


def _default_sentiment() -> Dict[str, Any]:
    return {
        "sentimiento": "neutral",
        "confianza": 0,
        "ofensivo": False,
        "emocion": "neutral",
        "resumen": "No se pudo analizar",
    }


def generate_semantic_report(
    search_params: Dict[str, Any],
    keywords: List[str],
    results_summary: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Generate a semantic report correlating search parameters + keywords
    with the obtained results. Uses LLM for narrative generation.
    """
    try:
        params_text = "\n".join(f"- {k}: {v}" for k, v in search_params.items() if v)
        keywords_text = ", ".join(keywords) if keywords else "Ninguna"

        platforms_text = ""
        for platform, data in results_summary.get("platforms", {}).items():
            count = data.get("count", 0)
            sample = data.get("sample", "")
            platforms_text += f"\n- {platform}: {count} resultados"
            if sample:
                platforms_text += f" (ejemplo: {sample[:100]})"

        prompt = f"""Genera un informe semantico forense en espanol para una investigacion OSINT.

PARAMETROS DE BUSQUEDA:
{params_text}

PALABRAS CLAVE: {keywords_text}

RESULTADOS OBTENIDOS POR PLATAFORMA:
{platforms_text}

TOTAL RESULTADOS: {results_summary.get('total', 0)}

IMPORTANTE:
1. Responde con un JSON valido.
2. El informe debe correlacionar los parametros de busqueda con los hallazgos.
3. Identificar patrones, coincidencias y ausencias relevantes.

JSON con estas propiedades:
- "resumenEjecutivo": string (3-5 oraciones resumiendo hallazgos clave)
- "correlaciones": array de strings (cada correlacion entre parametros y resultados)
- "patronesDetectados": array de strings (patrones observados en los datos)
- "hallazgosRelevantes": array de strings (hallazgos mas importantes)
- "lagunas": array de strings (informacion que no se encontro o fue insuficiente)
- "recomendaciones": array de strings (sugerencias para profundizar la investigacion)
- "nivelConfianza": number 0-100 (confianza general en los resultados)

Responde SOLO el JSON."""

        payload = {
            "model": LLM_MODEL,
            "prompt": prompt,
            "stream": False
        }

        response = requests.post(
            LLM_API_URL,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=LLM_TIMEOUT
        )

        if response.status_code != 200:
            return {"error": f"LLM API error: {response.status_code}"}

        llm_response = response.json()
        analysis_text = llm_response.get("response", llm_response.get("output", ""))

        json_start = analysis_text.find('{')
        json_end = analysis_text.rfind('}') + 1

        if json_start >= 0 and json_end > json_start:
            return json.loads(analysis_text[json_start:json_end])

        return {"resumenEjecutivo": analysis_text, "error": "Respuesta no JSON"}

    except Exception as e:
        logger.error(f"Semantic report error: {e}")
        return {"error": str(e)}
