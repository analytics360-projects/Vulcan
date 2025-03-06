from fastapi import APIRouter, Query, Path, HTTPException
from typing import Dict, Any, List

from config import (
    DEFAULT_MAX_POSTS, DEFAULT_MAX_SCROLL_ATTEMPTS, logger
)
from models.group import GroupAnalysis, Post
from services.group_scraper import (
    scrape_facebook_group, get_group_posts_by_keyword, get_group_member_activity
)


router = APIRouter(
    prefix="/group",
    tags=["group"],
    responses={
        404: {"description": "Not found"},
        500: {"description": "Internal server error"},
        504: {"description": "Gateway timeout"}
    }
)


@router.get("/{group_id}", response_model=GroupAnalysis)
async def analyze_facebook_group(
        group_id: str = Path(..., description="Facebook Group ID"),
        max_posts: int = Query(DEFAULT_MAX_POSTS, description="Maximum number of posts to analyze", ge=5, le=100),
        max_scroll_attempts: int = Query(DEFAULT_MAX_SCROLL_ATTEMPTS, description="Maximum number of scroll attempts", ge=5, le=30)
):
    """
    Analyze a Facebook Group's content including posts, comments, and reactions.
    """
    try:
        group_analysis = scrape_facebook_group(
            group_id=group_id,
            max_posts=max_posts,
            max_scroll_attempts=max_scroll_attempts
        )

        return group_analysis

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error analyzing Facebook group: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error analyzing Facebook group: {str(e)}")


@router.get("/{group_id}/top-comments")
async def get_top_comments(
        group_id: str = Path(..., description="Facebook Group ID"),
        max_posts: int = Query(DEFAULT_MAX_POSTS, description="Maximum number of posts to analyze", ge=5, le=100),
        limit: int = Query(10, description="Number of top comments to return", ge=1, le=50)
):
    """
    Retrieve top comments (most liked) from a Facebook Group.
    """
    try:
        group_analysis = scrape_facebook_group(
            group_id=group_id,
            max_posts=max_posts
        )

        # Limit to requested number
        top_comments = group_analysis.top_comments[:limit]

        return {
            "group_name": group_analysis.group_name,
            "group_id": group_analysis.group_id,
            "top_comments": top_comments,
            "count": len(top_comments)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving top comments: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving top comments: {str(e)}")


@router.get("/{group_id}/reaction-stats")
async def get_reaction_stats(
        group_id: str = Path(..., description="Facebook Group ID"),
        max_posts: int = Query(DEFAULT_MAX_POSTS, description="Maximum number of posts to analyze", ge=5, le=100)
):
    """
    Retrieve reaction statistics from a Facebook Group.
    Provides counts for different reaction types (like, love, haha, etc.)
    """
    try:
        group_analysis = scrape_facebook_group(
            group_id=group_id,
            max_posts=max_posts
        )

        return {
            "group_name": group_analysis.group_name,
            "group_id": group_analysis.group_id,
            "reaction_stats": group_analysis.reaction_stats
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving reaction stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving reaction stats: {str(e)}")


@router.get("/{group_id}/active-members")
async def get_active_members(
        group_id: str = Path(..., description="Facebook Group ID"),
        max_posts: int = Query(DEFAULT_MAX_POSTS, description="Maximum number of posts to analyze", ge=5, le=100)
):
    """
    Retrieve most active members from a Facebook Group.
    """
    try:
        group_analysis = scrape_facebook_group(
            group_id=group_id,
            max_posts=max_posts
        )

        return {
            "group_name": group_analysis.group_name,
            "group_id": group_analysis.group_id,
            "active_members": group_analysis.most_active_members,
            "count": len(group_analysis.most_active_members)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving active members: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving active members: {str(e)}")


@router.get("/{group_id}/search", response_model=List[Post])
async def search_group_posts(
        group_id: str = Path(..., description="Facebook Group ID"),
        keyword: str = Query(..., description="Keyword to search for in posts and comments"),
        max_posts: int = Query(DEFAULT_MAX_POSTS, description="Maximum number of posts to analyze", ge=5, le=100),
        case_sensitive: bool = Query(False, description="Whether the search should be case-sensitive")
):
    """
    Search for posts containing a specific keyword in a Facebook Group.
    """
    try:
        matching_posts = get_group_posts_by_keyword(
            group_id=group_id,
            keyword=keyword,
            max_posts=max_posts,
            case_sensitive=case_sensitive
        )

        return matching_posts

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error searching group posts: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error searching group posts: {str(e)}")


@router.get("/{group_id}/members/{member_name}")
async def get_member_activity(
        group_id: str = Path(..., description="Facebook Group ID"),
        member_name: str = Path(..., description="Name of the member to analyze"),
        max_posts: int = Query(DEFAULT_MAX_POSTS, description="Maximum number of posts to analyze", ge=5, le=100)
):
    """
    Get activity details for a specific group member.
    """
    try:
        member_activity = get_group_member_activity(
            group_id=group_id,
            member_name=member_name,
            max_posts=max_posts
        )

        return member_activity

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error analyzing member activity: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error analyzing member activity: {str(e)}")