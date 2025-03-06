from fastapi import APIRouter, Query, Path, HTTPException
from typing import Dict, Any
from datetime import datetime
import pandas as pd

from config import (
    DEFAULT_MAX_RESULTS, DEFAULT_MIN_PRICE, DEFAULT_MAX_PRICE,
    DEFAULT_DAYS_LISTED, logger
)
from models.marketplace import MarketplaceSearchResults
from services.marketplace_scraper import scrape_marketplace

router = APIRouter(
    prefix="/marketplace",
    tags=["marketplace"],
    responses={
        404: {"description": "Not found"},
        500: {"description": "Internal server error"},
        504: {"description": "Gateway timeout"}
    }
)


@router.get("/search", response_model=MarketplaceSearchResults)
async def search_marketplace(
        city: str = Query(..., description="City to search in"),
        product: str = Query(..., description="Product to search for"),
        min_price: int = Query(DEFAULT_MIN_PRICE, description="Minimum price", ge=0),
        max_price: int = Query(DEFAULT_MAX_PRICE, description="Maximum price", ge=0),
        days_listed: int = Query(DEFAULT_DAYS_LISTED, description="Days since listed", ge=1, le=30),
        max_results: int = Query(DEFAULT_MAX_RESULTS, description="Maximum number of results to return", ge=1, le=200)
):
    """
    Search Facebook Marketplace for products matching the specified criteria.
    Returns a list of product listings with details and prices.
    """
    try:
        results = scrape_marketplace(
            city=city,
            product=product,
            min_price=min_price,
            max_price=max_price,
            days_listed=days_listed,
            max_results=max_results
        )

        # Prepare response
        response = {
            "results": results,
            "count": len(results),
            "query_params": {
                "city": city,
                "product": product,
                "min_price": min_price,
                "max_price": max_price,
                "days_listed": days_listed,
                "max_results": max_results
            },
            "timestamp": datetime.now().isoformat()
        }

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in search endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/export/{format}")
async def export_results(
        format: str = Path(..., description="Export format (csv or json)"),
        city: str = Query(..., description="City to search in"),
        product: str = Query(..., description="Product to search for"),
        min_price: int = Query(DEFAULT_MIN_PRICE, description="Minimum price"),
        max_price: int = Query(DEFAULT_MAX_PRICE, description="Maximum price"),
        days_listed: int = Query(DEFAULT_DAYS_LISTED, description="Days since listed")
):
    """
    Export search results to CSV or JSON.

    Args:
        format: Export format (csv or json)
        city: City to search in
        product: Product to search for
        min_price: Minimum price
        max_price: Maximum price
        days_listed: Days since listed

    Returns:
        Dict[str, Any]: Dictionary containing the filename and content
    """
    if format not in ["csv", "json"]:
        raise HTTPException(status_code=400, detail="Format must be either 'csv' or 'json'")

    results = scrape_marketplace(city, product, min_price, max_price, days_listed)

    filename = f"{product}_{city}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    if format == "csv":
        df = pd.DataFrame(results)
        csv_content = df.to_csv(index=False)
        return {"filename": f"{filename}.csv", "content": csv_content}
    else:
        return {"filename": f"{filename}.json", "content": results}