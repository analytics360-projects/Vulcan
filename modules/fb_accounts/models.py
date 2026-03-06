"""Facebook accounts — Pydantic models (legacy, delegates to social_accounts)"""
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime


class FBAccountCreate(BaseModel):
    email: str
    password: str
    notes: Optional[str] = None


class FBAccountStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(active|disabled)$")


class FBAccountOut(BaseModel):
    id: int
    email: str
    status: str
    last_used: Optional[datetime] = None
    last_login: Optional[datetime] = None
    user_agent: Optional[str] = None
    fail_count: int = 0
    cooldown_until: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


class FBAccountStats(BaseModel):
    total: int
    active: int
    cooldown: int
    banned: int
    disabled: int


class FBAccountTestResult(BaseModel):
    account_id: int
    email: str
    success: bool
    detail: str
