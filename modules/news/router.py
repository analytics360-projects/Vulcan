"""News router — moved from routers/news.py"""
from fastapi import APIRouter, Query, Path, HTTPException
from typing import List

from config import logger
from modules.news.models import NewsSearchResults, NewsArticle
from modules.news.service import fetch_google_news, extract_article_content, fetch_news_with_content
from modules.news.analyzer import analyze_news_batch, analyze_news_batch_with_keywords

router = APIRouter(prefix="/news", tags=["news"])


def _build_result(query, language, country, articles, include_content, analyze, keywords=None, parameters=None):
    news_articles = [NewsArticle(**a) for a in articles]
    percentage = 0

    if analyze:
        try:
            if keywords is not None:
                analyzed, percentage = analyze_news_batch_with_keywords(news_articles, keywords, parameters or [])
            else:
                analyzed, percentage = analyze_news_batch(news_articles)
            return {"query": query, "language": language, "country": country, "results": analyzed, "count": len(analyzed), "include_content": include_content, "percentage": percentage, "authorized": False}
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            dicts = [{"analysis": {}, **a.model_dump()} for a in news_articles]
            return {"query": query, "language": language, "country": country, "results": dicts, "count": len(dicts), "include_content": include_content, "percentage": 0, "authorized": False}

    if include_content:
        with_content = sum(1 for a in news_articles if a.article_content and len(a.article_content.strip()) >= 10)
        percentage = (with_content / len(news_articles) * 100) if news_articles else 0

    return NewsSearchResults(query=query, language=language, country=country, results=news_articles, count=len(news_articles), include_content=include_content, percentage=percentage, authorized=False)


def _fetch(query, language, country, max_results, include_content):
    if include_content:
        return fetch_news_with_content(query=query, language=language, country=country, max_results=max_results, include_content=True)
    return fetch_google_news(query=query, language=language, country=country, max_results=max_results)


@router.get("/search", response_model=NewsSearchResults)
async def search_news(
    query: str = Query(...), language: str = Query("es"), country: str = Query("MX"),
    max_results: int = Query(5, ge=1, le=20), include_content: bool = Query(False), analyze: bool = Query(False),
):
    try:
        if analyze:
            include_content = True
        articles = _fetch(query, language, country, max_results, include_content)
        return _build_result(query, language, country, articles, include_content, analyze)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"News search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/searchWithKeywords", response_model=NewsSearchResults)
async def search_news_keywords(
    query: str = Query(...), language: str = Query("es"), country: str = Query("MX"),
    keywords: List[str] = Query([]), parameters: List[str] = Query([]),
    max_results: int = Query(5, ge=1, le=20), include_content: bool = Query(False), analyze: bool = Query(False),
):
    try:
        if analyze:
            include_content = True
        articles = _fetch(query, language, country, max_results, include_content)
        return _build_result(query, language, country, articles, include_content, analyze, keywords, parameters)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"News search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/article")
async def get_article(url: str = Query(...)):
    try:
        data = extract_article_content(url)
        return {"url": url, "article_content": data["article_content"], "image_url": data["image_url"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Article extraction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/topic/{topic}", response_model=NewsSearchResults)
async def get_news_by_topic(
    topic: str = Path(...), language: str = Query("en"), country: str = Query("US"),
    max_results: int = Query(5, ge=1, le=10), include_content: bool = Query(False),
):
    topic_queries = {
        "technology": "technology OR tech OR AI", "business": "business OR economy OR finance",
        "sports": "sports OR athletics", "entertainment": "entertainment OR movies OR music",
        "health": "health OR medicine", "science": "science OR research",
        "politics": "politics OR government", "world": "world news OR international",
    }
    try:
        q = topic_queries.get(topic.lower(), topic)
        articles = _fetch(q, language, country, max_results, include_content)
        return _build_result(topic, language, country, articles, include_content, False)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Topic news error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trending", response_model=NewsSearchResults)
async def get_trending(
    language: str = Query("en"), country: str = Query("US"),
    max_results: int = Query(5, ge=1, le=10), include_content: bool = Query(False),
):
    try:
        articles = _fetch("", language, country, max_results, include_content)
        return _build_result("trending", language, country, articles, include_content, False)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Trending news error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
