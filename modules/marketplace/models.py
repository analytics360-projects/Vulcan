"""Marketplace models — moved from models/marketplace.py"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class MarketplaceItem(BaseModel):
    title: str
    price: float
    location: str
    url: str
    image_url: Optional[str] = None
    posted_time: Optional[str] = None
    description: Optional[str] = None
    authorized: Optional[bool] = Field(False)


class MarketplaceSearchResults(BaseModel):
    results: List[MarketplaceItem]
    count: int
    query_params: Dict[str, Any]
    timestamp: str
