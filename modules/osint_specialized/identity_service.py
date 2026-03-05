"""Identity OSINT service — Cross-platform + CURP/RFC validation"""
import re
from config import logger


def validate_curp(curp: str) -> bool:
    pattern = r"^[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d$"
    return bool(re.match(pattern, curp.upper()))


def validate_rfc(rfc: str) -> bool:
    pattern = r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$"
    return bool(re.match(pattern, rfc.upper()))


async def search(curp: str = None, rfc: str = None, nombre: str = None) -> dict:
    results = {"sources": [], "errors": [], "validations": {}}

    if curp:
        valid = validate_curp(curp)
        results["validations"]["curp"] = {"value": curp.upper(), "valid": valid}
        if not valid:
            results["errors"].append("CURP format invalid")

    if rfc:
        valid = validate_rfc(rfc)
        results["validations"]["rfc"] = {"value": rfc.upper(), "valid": valid}
        if not valid:
            results["errors"].append("RFC format invalid")

    # Cross-platform search by name
    if nombre:
        results["nombre"] = nombre
        try:
            from modules.osint_social.twitter_service import search as tw_search, get_health as tw_health
            if tw_health().available:
                tw_results = await tw_search(query=nombre, max_results=5)
                if tw_results:
                    results["twitter"] = [r.model_dump() for r in tw_results]
                    results["sources"].append("twitter")
        except Exception as e:
            logger.warning(f"Identity twitter search error: {e}")

    return results
