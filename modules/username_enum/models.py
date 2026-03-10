"""Username enumeration models — findme-based platform detection."""
from pydantic import BaseModel
from typing import List, Optional


class PlatformHit(BaseModel):
    platform: str
    url: str
    status: str  # "found" | "not_found" | "error"
    http_code: Optional[int] = None


class UsernameEnumResponse(BaseModel):
    username: str
    total_found: int = 0
    total_checked: int = 0
    platforms_found: List[PlatformHit] = []
    platforms_not_found: List[str] = []
    errors: List[str] = []
