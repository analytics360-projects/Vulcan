from typing import Dict, Any, List
import requests
import json
import time
from fastapi import HTTPException

from config import logger, LLM_API_URL, LLM_MODEL, LLM_TIMEOUT
from models.news import NewsArticle


def analyze_article_with_llm(article: NewsArticle) -> Dict[str, Any]:
    """
    Analyze a news article using an LLM.

    Args:
        article (NewsArticle): The news article to analyze

    Returns:
        Dict[str, Any]: The analysis results
    """
    try:
        # Check if article has content
        if not article.article_content:
            return {"error": "No article content to analyze"}

        # Prepare the content for analysis
        article_content = f"Título: {article.title}\n\nFuente: {article.source}\n\nContenido: {article.article_content}"

        # Prepare the prompt
        prompt = f"""Analiza el contenido de la siguiente noticia:
{article_content}

Por favor, proporciona un análisis estructurado en formato JSON que incluya:

1. "categorias": Clasifica la noticia en una o más de las siguientes categorías:
   - Negocios o lugares locales
   - Empresas, organizaciones o instituciones
   - Marcas o productos
   - Artistas, bandas o figuras públicas
   - Entretenimiento
   - Causas o comunidades

2. "ubicaciones": Identifica y lista todas las ubicaciones geográficas mencionadas en la noticia.

3. "analisisSemantico": Proporciona:
   - "temasPrincipales": Lista de los temas principales tratados
   - "tonalidad": Si la noticia es positiva, negativa o neutral
   - "objetividad": Si el contenido es objetivo, subjetivo o mixto
   - "enfasis": El enfoque principal del texto (informativo, análisis, opinión, denuncia)
   - "longitudTexto": Número de caracteres en el texto

4. "resumen": Incluye una lista de "puntosClave" con 5 aspectos fundamentales de la noticia.

Asegúrate de que la respuesta esté en formato JSON válido."""

        # Prepare the LLM request
        payload = {
            "model": LLM_MODEL,
            "prompt": prompt,
            "stream": False
        }

        # Make the LLM request
        response = requests.post(
            LLM_API_URL,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=LLM_TIMEOUT
        )

        if response.status_code != 200:
            logger.error(f"LLM API error: {response.status_code} - {response.text}")
            return {"error": f"LLM API error: {response.status_code}"}

        # Parse the LLM response
        llm_response = response.json()

        # Try to extract the JSON from the response
        try:
            # The response might be in the "response" field for Ollama
            analysis_text = llm_response.get("response", llm_response.get("output", ""))

            # Try to find JSON in the response
            json_start = analysis_text.find('{')
            json_end = analysis_text.rfind('}') + 1

            if json_start >= 0 and json_end > json_start:
                json_str = analysis_text[json_start:json_end]
                analysis = json.loads(json_str)
            else:
                # If no JSON is found, return the raw text with a warning
                logger.warning(f"Could not find JSON in LLM response: {analysis_text[:100]}...")
                analysis = {"text": analysis_text, "warning": "Response was not in valid JSON format"}

            return analysis

        except json.JSONDecodeError as e:
            # If we can't parse as JSON, return the raw text with error
            logger.error(f"JSON parse error: {str(e)}")
            return {
                "text": llm_response.get("response", llm_response.get("output", "")),
                "error": f"Failed to parse response as JSON: {str(e)}"
            }

    except Exception as e:
        logger.error(f"Error analyzing article: {str(e)}")
        return {"error": f"Error analyzing article: {str(e)}"}


def analyze_news_batch(articles: List[NewsArticle]) -> List[Dict[str, Any]]:
    """
    Analyze a batch of news articles.

    Args:
        articles (List[NewsArticle]): The news articles to analyze

    Returns:
        List[Dict[str, Any]]: The analysis results for each article
    """
    analyzed_articles = []

    for article in articles:
        try:
            # Skip articles without content
            if not article.article_content or len(article.article_content.strip()) < 50:
                logger.warning(f"Skipping article with insufficient content: {article.title}")
                article_dict = article.dict()
                article_dict["analysis"] = {"error": "Insufficient content for analysis"}
                analyzed_articles.append(article_dict)
                continue

            # Create a copy of the article as a dictionary
            article_dict = article.dict()

            # Analyze the article
            analysis = analyze_article_with_llm(article)

            # Add the analysis to the article
            article_dict["analysis"] = analysis

            analyzed_articles.append(article_dict)

            # Sleep briefly to avoid overloading the LLM API
            time.sleep(1)

        except Exception as e:
            logger.error(f"Error processing article {article.title}: {str(e)}")
            # Add the article with an error message
            article_dict = article.dict()
            article_dict["analysis"] = {"error": f"Analysis failed: {str(e)}"}
            analyzed_articles.append(article_dict)

    return analyzed_articles
