"""Phone OSINT service — NumVerify + social aggregation"""
import httpx
from config import settings, logger
from shared.rate_limiter import rate_limited


@rate_limited("numverify")
async def search(number: str) -> dict:
    results = {"number": number, "sources": [], "errors": []}

    # NumVerify lookup
    if settings.numverify_api_key:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "http://apilayer.net/api/validate",
                    params={"access_key": settings.numverify_api_key, "number": number},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results["numverify"] = {
                        "valid": data.get("valid"),
                        "country": data.get("country_name"),
                        "carrier": data.get("carrier"),
                        "line_type": data.get("line_type"),
                        "location": data.get("location"),
                    }
                    results["sources"].append("numverify")
        except Exception as e:
            logger.error(f"NumVerify error: {e}")
            results["errors"].append(f"numverify: {e}")
    else:
        results["errors"].append("numverify: API key not configured")

    return results
