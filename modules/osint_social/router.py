"""OSINT Social router"""
from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from config import logger
from modules.osint_social.models import SocialSearchResponse

router = APIRouter(prefix="/social", tags=["social"])


@router.get("/twitter/health")
async def twitter_health():
    from modules.osint_social.twitter_service import get_health
    return get_health()


@router.get("/twitter")
async def twitter_search(query: Optional[str] = None, user: Optional[str] = None, max_results: int = Query(10, ge=1, le=100)):
    from modules.osint_social.twitter_service import search, get_health
    health = get_health()
    results = await search(query=query, user=user, max_results=max_results) if health.available else []
    return SocialSearchResponse(query=query or user or "", plataforma="twitter", resultados=results, count=len(results), health=health)


@router.get("/instagram/health")
async def instagram_health():
    from modules.osint_social.instagram_service import get_health
    return get_health()


@router.get("/instagram")
async def instagram_search(username: Optional[str] = None, hashtag: Optional[str] = None):
    from modules.osint_social.instagram_service import search, get_health
    health = get_health()
    results = await search(username=username, hashtag=hashtag) if health.available else []
    return SocialSearchResponse(query=username or hashtag or "", plataforma="instagram", resultados=results, count=len(results), health=health)


@router.get("/tiktok/health")
async def tiktok_health():
    from modules.osint_social.tiktok_service import get_health
    return get_health()


@router.get("/tiktok")
async def tiktok_search(username: Optional[str] = None, query: Optional[str] = None, max_results: int = Query(10)):
    from modules.osint_social.tiktok_service import search, get_health
    health = get_health()
    results = await search(username=username, query=query, max_results=max_results) if health.available else []
    return SocialSearchResponse(query=username or query or "", plataforma="tiktok", resultados=results, count=len(results), health=health)


@router.get("/telegram/health")
async def telegram_health():
    from modules.osint_social.telegram_service import get_health
    return get_health()


@router.get("/telegram")
async def telegram_search(channel: Optional[str] = None, query: Optional[str] = None, max_results: int = Query(20)):
    from modules.osint_social.telegram_service import search, get_health
    health = get_health()
    results = await search(channel=channel, query=query, max_results=max_results) if health.available else []
    return SocialSearchResponse(query=channel or query or "", plataforma="telegram", resultados=results, count=len(results), health=health)


@router.get("/forums/health")
async def forums_health():
    from modules.osint_social.forums_service import get_health
    return get_health()


@router.get("/forums")
async def forums_search(query: Optional[str] = None, subreddit: Optional[str] = None, max_results: int = Query(10)):
    from modules.osint_social.forums_service import search, get_health
    health = get_health()
    results = await search(query=query, subreddit=subreddit, max_results=max_results) if health.available else []
    return SocialSearchResponse(query=query or "", plataforma="forums", resultados=results, count=len(results), health=health)
