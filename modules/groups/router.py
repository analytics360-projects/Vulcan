"""Groups router — moved from routers/group.py"""
from fastapi import APIRouter, Query, Path, HTTPException
from typing import List

from config import settings, logger
from modules.groups.models import GroupAnalysis, Post, GroupCategorySearchResponse
from modules.groups.service import scrape_facebook_group, get_group_posts_by_keyword, get_group_member_activity, search_groups_by_category

router = APIRouter(prefix="/groups", tags=["groups"])


# ── G4: Group Taxonomy Search by Category ──
# IMPORTANT: This route MUST be defined before /{group_id} to avoid path conflicts.

@router.get("/search-by-category", response_model=GroupCategorySearchResponse)
async def search_by_category(
    query: str = Query(..., description="Search query"),
    categories: str = Query(..., description="Comma-separated category codes: negocios,empresas,marcas,artistas,entretenimiento,causas"),
    max_results: int = Query(5, ge=1, le=20),
):
    try:
        category_list = [c.strip() for c in categories.split(",") if c.strip()]
        return search_groups_by_category(query=query, categories=category_list, max_results=max_results)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in group category search: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{group_id}", response_model=GroupAnalysis)
async def analyze_facebook_group(
    group_id: str = Path(...),
    max_posts: int = Query(30, ge=5, le=100),
    max_scroll_attempts: int = Query(10, ge=5, le=30),
):
    try:
        return scrape_facebook_group(group_id=group_id, max_posts=max_posts, max_scroll_attempts=max_scroll_attempts)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error analyzing group: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{group_id}/top-comments")
async def get_top_comments(
    group_id: str = Path(...),
    max_posts: int = Query(30, ge=5, le=100),
    limit: int = Query(10, ge=1, le=50),
):
    try:
        analysis = scrape_facebook_group(group_id=group_id, max_posts=max_posts)
        return {"group_name": analysis.group_name, "group_id": analysis.group_id, "top_comments": analysis.top_comments[:limit], "count": min(limit, len(analysis.top_comments))}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting top comments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{group_id}/reaction-stats")
async def get_reaction_stats(group_id: str = Path(...), max_posts: int = Query(30, ge=5, le=100)):
    try:
        analysis = scrape_facebook_group(group_id=group_id, max_posts=max_posts)
        return {"group_name": analysis.group_name, "group_id": analysis.group_id, "reaction_stats": analysis.reaction_stats}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting reaction stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{group_id}/active-members")
async def get_active_members(group_id: str = Path(...), max_posts: int = Query(30, ge=5, le=100)):
    try:
        analysis = scrape_facebook_group(group_id=group_id, max_posts=max_posts)
        return {"group_name": analysis.group_name, "group_id": analysis.group_id, "active_members": analysis.most_active_members, "count": len(analysis.most_active_members)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting active members: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{group_id}/search", response_model=List[Post])
async def search_group_posts(
    group_id: str = Path(...),
    keyword: str = Query(...),
    max_posts: int = Query(30, ge=5, le=100),
    case_sensitive: bool = Query(False),
):
    try:
        return get_group_posts_by_keyword(group_id=group_id, keyword=keyword, max_posts=max_posts, case_sensitive=case_sensitive)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error searching group: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{group_id}/members/{member_name}")
async def get_member_activity(group_id: str = Path(...), member_name: str = Path(...), max_posts: int = Query(30, ge=5, le=100)):
    try:
        return get_group_member_activity(group_id=group_id, member_name=member_name, max_posts=max_posts)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting member activity: {e}")
        raise HTTPException(status_code=500, detail=str(e))
