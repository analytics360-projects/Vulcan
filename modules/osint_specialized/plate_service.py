"""Plate OSINT service — REPUVE + marketplace cross-search"""
import httpx
from config import settings, logger


async def search(plate: str, country: str = "MX") -> dict:
    results = {"plate": plate, "country": country, "sources": [], "errors": []}

    # Marketplace cross-search for plate mentions
    try:
        from modules.marketplace.service import scrape_marketplace
        marketplace_results = scrape_marketplace(
            city="mexico", product=plate, min_price=0, max_price=999999,
            days_listed=30, max_results=5,
        )
        if marketplace_results:
            results["marketplace"] = marketplace_results
            results["sources"].append("marketplace")
    except Exception as e:
        logger.warning(f"Marketplace plate search error: {e}")
        results["errors"].append(f"marketplace: {e}")

    return results
