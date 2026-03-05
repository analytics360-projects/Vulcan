"""Email OSINT service — Hunter.io + HIBP"""
import httpx
from config import settings, logger
from shared.rate_limiter import rate_limited


@rate_limited("hunter")
async def search(email: str) -> dict:
    results = {"email": email, "sources": [], "errors": []}

    # Hunter.io email verification
    if settings.hunter_api_key:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.hunter.io/v2/email-verifier",
                    params={"email": email, "api_key": settings.hunter_api_key},
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    results["hunter"] = {
                        "status": data.get("status"),
                        "score": data.get("score"),
                        "smtp_server": data.get("smtp_server"),
                        "smtp_check": data.get("smtp_check"),
                    }
                    results["sources"].append("hunter.io")
        except Exception as e:
            logger.error(f"Hunter.io error: {e}")
            results["errors"].append(f"hunter: {e}")

    # Have I Been Pwned
    if settings.hibp_api_key:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}",
                    headers={"hibp-api-key": settings.hibp_api_key, "user-agent": "Vulcan OSINT"},
                )
                if resp.status_code == 200:
                    breaches = resp.json()
                    results["hibp"] = {
                        "breached": True,
                        "breach_count": len(breaches),
                        "breaches": [{"name": b.get("Name"), "date": b.get("BreachDate"), "data_classes": b.get("DataClasses", [])} for b in breaches[:10]],
                    }
                    results["sources"].append("hibp")
                elif resp.status_code == 404:
                    results["hibp"] = {"breached": False, "breach_count": 0, "breaches": []}
                    results["sources"].append("hibp")
        except Exception as e:
            logger.error(f"HIBP error: {e}")
            results["errors"].append(f"hibp: {e}")

    return results
