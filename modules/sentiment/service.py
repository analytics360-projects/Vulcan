"""Sentiment analysis service using LLM (Ollama/DeepSeek)"""
from typing import List, Dict, Any
import requests
import json

from config import settings, logger

LLM_API_URL = settings.llm_api_url
LLM_MODEL = settings.llm_model
LLM_TIMEOUT = settings.llm_timeout


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
