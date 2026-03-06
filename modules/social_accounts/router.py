"""Social accounts router — manage accounts for session rotation (multi-platform)"""
from fastapi import APIRouter, HTTPException, Query

from config import logger
from modules.social_accounts.models import (
    SocialAccountCreate,
    SocialAccountStatusUpdate,
    SocialAccountOut,
    SocialAccountStats,
    PlatformStats,
    SocialAccountTestResult,
)

router = APIRouter(prefix="/social-accounts", tags=["social-accounts"])


def _to_out(a: dict) -> SocialAccountOut:
    return SocialAccountOut(
        id=a["id"],
        platform=a["platform"],
        email=a["email"],
        status=a["status"],
        last_used=a.get("last_used"),
        last_login=a.get("last_login"),
        user_agent=a.get("user_agent"),
        fail_count=a.get("fail_count", 0),
        cooldown_until=a.get("cooldown_until"),
        notes=a.get("notes"),
        created_at=a.get("created_at"),
    )


@router.get("/", response_model=list[SocialAccountOut])
async def list_accounts(platform: str = Query(None, description="Filter by platform: facebook, instagram, tiktok")):
    """List all social accounts (passwords hidden)."""
    from shared.social_account_manager import social_account_manager
    accounts = social_account_manager.get_all_accounts(platform=platform)
    return [_to_out(a) for a in accounts]


@router.post("/", response_model=SocialAccountOut)
async def add_account(body: SocialAccountCreate):
    """Add a new social account."""
    from shared.social_account_manager import social_account_manager
    try:
        account_id = social_account_manager.add_account(
            platform=body.platform, email=body.email, password=body.password, notes=body.notes
        )
        account = social_account_manager.get_account_by_id(account_id)
        return _to_out(account)
    except Exception as e:
        logger.error(f"Error adding social account: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{account_id}")
async def delete_account(account_id: int):
    """Remove a social account."""
    from shared.social_account_manager import social_account_manager
    deleted = social_account_manager.delete_account(account_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"deleted": True, "id": account_id}


@router.put("/{account_id}/status")
async def update_account_status(account_id: int, body: SocialAccountStatusUpdate):
    """Change account status (active/disabled)."""
    from shared.social_account_manager import social_account_manager
    updated = social_account_manager.update_status(account_id, body.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"updated": True, "id": account_id, "status": body.status}


@router.post("/test/{account_id}", response_model=SocialAccountTestResult)
async def test_account_login(account_id: int):
    """Test login for a specific account."""
    from shared.social_account_manager import social_account_manager
    from shared.webdriver import get_driver

    account = social_account_manager.get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    try:
        with get_driver(stealth=True, use_proxy=True) as driver:
            success = social_account_manager.login(driver, account)
            if success:
                social_account_manager.save_cookies(account_id, driver.get_cookies())
            return SocialAccountTestResult(
                account_id=account_id,
                platform=account["platform"],
                email=account["email"],
                success=success,
                detail="Login successful" if success else "Login failed",
            )
    except Exception as e:
        logger.error(f"Test login error for account {account_id}: {e}")
        return SocialAccountTestResult(
            account_id=account_id,
            platform=account["platform"],
            email=account["email"],
            success=False,
            detail=f"Error: {str(e)}",
        )


@router.get("/stats", response_model=PlatformStats)
async def get_stats():
    """Summary stats for all platforms."""
    from shared.social_account_manager import social_account_manager
    try:
        all_stats = social_account_manager.get_stats_all()
        return PlatformStats(
            facebook=SocialAccountStats(**all_stats["facebook"]),
            instagram=SocialAccountStats(**all_stats["instagram"]),
            tiktok=SocialAccountStats(**all_stats["tiktok"]),
        )
    except Exception as e:
        logger.error(f"Error getting social account stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/{platform}", response_model=SocialAccountStats)
async def get_platform_stats(platform: str):
    """Stats for a specific platform."""
    from shared.social_account_manager import social_account_manager
    if platform not in ["facebook", "instagram", "tiktok"]:
        raise HTTPException(status_code=400, detail="Invalid platform")
    try:
        stats = social_account_manager.get_stats(platform)
        return SocialAccountStats(**stats)
    except Exception as e:
        logger.error(f"Error getting {platform} stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
