from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from datetime import datetime

class MarketplaceItem(BaseModel):
    """Model for a Facebook Marketplace item"""
    title: str
    price: float
    location: str
    url: str
    image_url: Optional[str] = None
    posted_time: Optional[str] = None
    description: Optional[str] = None


class MarketplaceSearchResults(BaseModel):
    """Model for search results from Facebook Marketplace"""
    results: List[MarketplaceItem]
    count: int
    query_params: Dict[str, Any]
    timestamp: str