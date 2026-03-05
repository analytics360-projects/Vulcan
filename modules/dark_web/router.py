"""Dark web router — ported from nyx-crawler/main.py"""
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from config import logger

router = APIRouter(prefix="/dark-web", tags=["dark-web"])


class SearchResult(BaseModel):
    title: str
    link: str
    date: Optional[str] = None
    thumbnail: Optional[str] = None
    engine: str = ""
    score: int = 0
    authorized: Optional[bool] = False


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    count: int


@router.get("/health")
async def dark_web_health():
    try:
        from modules.dark_web.service import get_searcher
        searcher = get_searcher()
        return {"status": "healthy", "tor_connected": searcher.session is not None}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


@router.get("/search", response_model=SearchResponse)
async def dark_web_search(
    q: str = Query(..., description="Search query"),
    engines: Optional[List[str]] = Query(None, description="Engines: torch, onion_land"),
    limit: int = Query(10, ge=1, le=100),
):
    try:
        from modules.dark_web.service import get_searcher
        searcher = get_searcher()
        results = searcher.search(q, engines=engines)
        limited = results[:limit]
        return SearchResponse(query=q, results=[SearchResult(**r) for r in limited], count=len(limited))
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Tor not available: {e}")
    except Exception as e:
        logger.exception(f"Dark web search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scrape")
async def dark_web_scrape(url: str = Query(...)):
    try:
        from modules.dark_web.scraper import DarkScrape
        scraper = DarkScrape()
        scraper.scrape(url)
        return scraper.result
    except Exception as e:
        logger.exception(f"Dark web scrape error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
