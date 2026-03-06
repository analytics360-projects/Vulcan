"""Facebook accounts router — manage FB accounts for session rotation"""
from fastapi import APIRouter, HTTPException

from config import logger
from modules.fb_accounts.models import (
    FBAccountCreate,
    FBAccountStatusUpdate,
    FBAccountOut,
    FBAccountStats,
    FBAccountTestResult,
)

router = APIRouter(prefix="/fb-accounts", tags=["fb-accounts"])


@router.get("/", response_model=list[FBAccountOut])
async def list_accounts():
    """List all Facebook accounts (passwords hidden)."""
    from shared.fb_account_manager import fb_account_manager
    accounts = fb_account_manager.get_all_accounts()
    # Strip passwords before returning
    return [
        FBAccountOut(
            id=a["id"],
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
        for a in accounts
    ]


@router.post("/", response_model=FBAccountOut)
async def add_account(body: FBAccountCreate):
    """Add a new Facebook account."""
    from shared.fb_account_manager import fb_account_manager
    try:
        account_id = fb_account_manager.add_account(
            email=body.email, password=body.password, notes=body.notes
        )
        account = fb_account_manager.get_account_by_id(account_id)
        return FBAccountOut(
            id=account["id"],
            email=account["email"],
            status=account["status"],
            last_used=account.get("last_used"),
            last_login=account.get("last_login"),
            user_agent=account.get("user_agent"),
            fail_count=account.get("fail_count", 0),
            cooldown_until=account.get("cooldown_until"),
            notes=account.get("notes"),
            created_at=account.get("created_at"),
        )
    except Exception as e:
        logger.error(f"Error adding FB account: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{account_id}")
async def delete_account(account_id: int):
    """Remove a Facebook account."""
    from shared.fb_account_manager import fb_account_manager
    deleted = fb_account_manager.delete_account(account_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"deleted": True, "id": account_id}


@router.put("/{account_id}/status")
async def update_account_status(account_id: int, body: FBAccountStatusUpdate):
    """Change account status (active/disabled)."""
    from shared.fb_account_manager import fb_account_manager
    updated = fb_account_manager.update_status(account_id, body.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"updated": True, "id": account_id, "status": body.status}


@router.post("/test/{account_id}", response_model=FBAccountTestResult)
async def test_account_login(account_id: int):
    """Test login for a specific account."""
    from shared.fb_account_manager import fb_account_manager
    from shared.webdriver import get_driver

    account = fb_account_manager.get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    try:
        with get_driver(stealth=True, use_proxy=True) as driver:
            success = fb_account_manager.login_facebook(driver, account)
            return FBAccountTestResult(
                account_id=account_id,
                email=account["email"],
                success=success,
                detail="Login successful" if success else "Login failed",
            )
    except Exception as e:
        logger.error(f"Test login error for account {account_id}: {e}")
        return FBAccountTestResult(
            account_id=account_id,
            email=account["email"],
            success=False,
            detail=f"Error: {str(e)}",
        )


@router.get("/stats", response_model=FBAccountStats)
async def get_stats():
    """Summary stats for Facebook accounts."""
    from shared.fb_account_manager import fb_account_manager
    try:
        stats = fb_account_manager.get_stats()
        return FBAccountStats(**stats)
    except Exception as e:
        logger.error(f"Error getting FB account stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
