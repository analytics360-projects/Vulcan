"""Social accounts — Pydantic models (multi-platform)"""
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime


class SocialAccountCreate(BaseModel):
    platform: str = Field(..., pattern="^(facebook|instagram|tiktok)$")
    email: str
    password: str
    notes: Optional[str] = None


class SocialAccountStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(active|disabled)$")


class SocialAccountOut(BaseModel):
    id: int
    platform: str
    email: str
    status: str
    last_used: Optional[datetime] = None
    last_login: Optional[datetime] = None
    user_agent: Optional[str] = None
    fail_count: int = 0
    cooldown_until: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


class SocialAccountStats(BaseModel):
    total: int
    active: int
    cooldown: int
    banned: int
    disabled: int


class PlatformStats(BaseModel):
    facebook: SocialAccountStats
    instagram: SocialAccountStats
    tiktok: SocialAccountStats


class SocialAccountTestResult(BaseModel):
    account_id: int
    platform: str
    email: str
    success: bool
    detail: str
