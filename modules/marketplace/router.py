"""Marketplace router — moved from routers/marketplace.py"""
from fastapi import APIRouter, Query, Path, HTTPException
from datetime import datetime
import pandas as pd

from config import settings, logger
from modules.marketplace.models import MarketplaceSearchResults
from modules.marketplace.service import scrape_marketplace

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


@router.get("/search", response_model=MarketplaceSearchResults)
async def search_marketplace_endpoint(
    city: str = Query(...),
    product: str = Query(...),
    min_price: int = Query(0, ge=0),
    max_price: int = Query(1000, ge=0),
    days_listed: int = Query(7, ge=1, le=30),
    max_results: int = Query(100, ge=1, le=200),
):
    try:
        results = scrape_marketplace(city=city, product=product, min_price=min_price, max_price=max_price, days_listed=days_listed, max_results=max_results)
        return {
            "results": results,
            "count": len(results),
            "query_params": {"city": city, "product": product, "min_price": min_price, "max_price": max_price, "days_listed": days_listed},
            "timestamp": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Marketplace search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/{format}")
async def export_results(
    format: str = Path(...),
    city: str = Query(...),
    product: str = Query(...),
    min_price: int = Query(0),
    max_price: int = Query(1000),
    days_listed: int = Query(7),
):
    if format not in ("csv", "json"):
        raise HTTPException(status_code=400, detail="Format must be 'csv' or 'json'")
    results = scrape_marketplace(city, product, min_price, max_price, days_listed)
    filename = f"{product}_{city}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if format == "csv":
        return {"filename": f"{filename}.csv", "content": pd.DataFrame(results).to_csv(index=False)}
    return {"filename": f"{filename}.json", "content": results}
