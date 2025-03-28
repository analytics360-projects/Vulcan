from fastapi import APIRouter, Query, Path, HTTPException
from typing import List, Dict, Any, Optional

from config import logger
from models.news import NewsSearchResults, NewsArticle
from services.web_scraper import (
    fetch_google_news, extract_article_content, fetch_news_with_content
)
from services.news_analyzer import analyze_article_with_llm, analyze_news_batch

router = APIRouter(
    prefix="/news",
    tags=["news"],
    responses={
        404: {"description": "Not found"},
        500: {"description": "Internal server error"},
        504: {"description": "Gateway timeout"}
    }
)


@router.get("/search", response_model=NewsSearchResults)
async def search_news(
        query: str = Query(..., description="Search query for news articles"),
        language: str = Query("es", description="Language code"),
        country: str = Query("MX", description="Country code"),
        max_results: int = Query(5, description="Maximum number of results to return", ge=1, le=20),
        include_content: bool = Query(False, description="Whether to include full article content"),
        analyze: bool = Query(False, description="Whether to analyze articles with LLM")
):
    """
    Search for news articles using Google News.

    This endpoint searches Google News and returns articles matching the query.
    If include_content is True, it will also extract the full article text and images.
    If analyze is True, it will use an LLM to analyze the article content.
    """
    try:
        # Always require include_content if analyze is True
        if analyze and not include_content:
            include_content = True

        # First, get the articles
        if include_content:
            articles = fetch_news_with_content(
                query=query,
                language=language,
                country=country,
                max_results=max_results,
                include_content=True
            )
        else:
            articles = fetch_google_news(
                query=query,
                language=language,
                country=country,
                max_results=max_results
            )

        # Convert to model objects first
        news_articles = [NewsArticle(**article) for article in articles]

        # Default percentage value
        percentage = 0

        # If analyze is requested, try to analyze the articles
        if analyze:
            try:
                from services.news_analyzer import analyze_news_batch

                # Get analyzed articles and percentage with content
                analyzed_articles, percentage = analyze_news_batch(news_articles)

                # Create result with articles including analysis field
                result = {
                    "query": query,
                    "language": language,
                    "country": country,
                    "results": analyzed_articles,
                    "count": len(analyzed_articles),
                    "include_content": include_content,
                    "percentage": percentage,
                    "authorized": False
                }

                return result

            except Exception as e:
                # If analysis fails, log the error but continue with the regular response
                logger.error(f"Article analysis failed: {str(e)}")
                # Add empty analysis field to each article
                article_dicts = []
                for article in news_articles:
                    article_dict = article.dict()
                    article_dict["analysis"] = {}
                    article_dicts.append(article_dict)

                # Create result with articles including empty analysis field
                result = {
                    "query": query,
                    "language": language,
                    "country": country,
                    "results": article_dicts,
                    "count": len(article_dicts),
                    "include_content": include_content,
                    "percentage": 0,  # Default to 0 if analysis fails
                    "authorized": False
                }

                return result

        # If no analysis requested, return standard response
        # Calculate percentage for articles with content even if not analyzing
        if include_content:
            articles_with_content = sum(1 for article in news_articles
                                        if article.article_content and len(article.article_content.strip()) >= 10)
            percentage = (articles_with_content / len(news_articles) * 100) if news_articles else 0

        result = NewsSearchResults(
            query=query,
            language=language,
            country=country,
            results=news_articles,
            count=len(news_articles),
            include_content=include_content,
            percentage=percentage,
            authorized=False
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in news search endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error searching news: {str(e)}")


@router.get("/article")
async def get_article_content(
        url: str = Query(..., description="URL of the article to extract content from")
):
    """
    Extract content and main image from a news article.

    This endpoint scrapes the provided URL and extracts the main article content and image.
    """
    try:
        extracted_data = extract_article_content(url)

        return {
            "url": url,
            "article_content": extracted_data["article_content"],
            "image_url": extracted_data["image_url"]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error extracting article content: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error extracting article content: {str(e)}")


@router.get("/topic/{topic}", response_model=NewsSearchResults)
async def get_news_by_topic(
        topic: str = Path(..., description="News topic"),
        language: str = Query("en", description="Language code"),
        country: str = Query("US", description="Country code"),
        max_results: int = Query(5, description="Maximum number of results to return", ge=1, le=10),
        include_content: bool = Query(False, description="Whether to include full article content")
):
    """
    Get news articles for a specific topic.

    This endpoint returns the latest news for predefined topics like 'technology',
    'business', 'sports', etc.
    """
    try:
        # Transform topic to appropriate search query
        topic_queries = {
            "technology": "technology OR tech OR AI OR artificial intelligence",
            "business": "business OR economy OR finance",
            "sports": "sports OR athletics",
            "entertainment": "entertainment OR movies OR music",
            "health": "health OR medicine OR wellness",
            "science": "science OR research",
            "politics": "politics OR government",
            "world": "world news OR international",
        }

        # Use the mapped query or default to the topic itself
        query = topic_queries.get(topic.lower(), topic)

        # Fetch news
        if include_content:
            articles = fetch_news_with_content(
                query=query,
                language=language,
                country=country,
                max_results=max_results,
                include_content=True
            )
        else:
            articles = fetch_google_news(
                query=query,
                language=language,
                country=country,
                max_results=max_results
            )

        # Convert to model objects
        news_articles = [NewsArticle(**article) for article in articles]

        result = NewsSearchResults(
            query=topic,
            language=language,
            country=country,
            results=news_articles,
            count=len(news_articles),
            include_content=include_content
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting news by topic: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting news by topic: {str(e)}")


@router.get("/trending", response_model=NewsSearchResults)
async def get_trending_news(
        language: str = Query("en", description="Language code"),
        country: str = Query("US", description="Country code"),
        max_results: int = Query(5, description="Maximum number of results to return", ge=1, le=10),
        include_content: bool = Query(False, description="Whether to include full article content")
):
    """
    Get trending news articles.

    This endpoint returns the latest trending news stories.
    """
    try:
        # For trending news, we don't specify a query in the RSS feed
        if include_content:
            articles = fetch_news_with_content(
                query="",  # Empty query for trending news
                language=language,
                country=country,
                max_results=max_results,
                include_content=True
            )
        else:
            articles = fetch_google_news(
                query="",  # Empty query for trending news
                language=language,
                country=country,
                max_results=max_results
            )

        # Convert to model objects
        news_articles = [NewsArticle(**article) for article in articles]

        result = NewsSearchResults(
            query="trending",
            language=language,
            country=country,
            results=news_articles,
            count=len(news_articles),
            include_content=include_content
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting trending news: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting trending news: {str(e)}")
