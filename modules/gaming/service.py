"""Gaming platforms OSINT — Steam, Xbox, PSN scraping by username"""
from datetime import datetime
from config import logger
from shared.rate_limiter import rate_limited
from modules.osint_social.models import OsintResult, PlatformHealth
import httpx


def get_health() -> PlatformHealth:
    return PlatformHealth(available=True, reason="Steam API + Selenium scraping")


@rate_limited("default")
async def search_steam(username: str) -> list[OsintResult]:
    """Search Steam profile by vanity URL / username."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Steam community profile (public, no API key needed)
            resp = await client.get(
                f"https://steamcommunity.com/id/{username}/?xml=1",
                follow_redirects=True,
            )
            if resp.status_code == 200 and "<profile>" in resp.text:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "xml")
                profile_data = {
                    "username": username,
                    "steam_id": soup.find("steamID64").text if soup.find("steamID64") else None,
                    "nombre": soup.find("steamID").text if soup.find("steamID") else None,
                    "avatar": soup.find("avatarFull").text if soup.find("avatarFull") else None,
                    "estado": soup.find("onlineState").text if soup.find("onlineState") else None,
                    "perfil_url": f"https://steamcommunity.com/id/{username}",
                    "ubicacion": soup.find("location").text if soup.find("location") else None,
                    "resumen": soup.find("summary").text[:500] if soup.find("summary") else None,
                    "miembro_desde": soup.find("memberSince").text if soup.find("memberSince") else None,
                    "visibilidad": soup.find("privacyState").text if soup.find("privacyState") else None,
                }
                results.append(OsintResult(
                    plataforma="steam",
                    tipo="perfil",
                    datos=profile_data,
                    timestamp=datetime.now().isoformat(),
                    fuente_url=f"https://steamcommunity.com/id/{username}",
                ))
    except Exception as e:
        logger.error(f"Steam search error: {e}")
    return results


@rate_limited("default")
async def search_xbox(username: str) -> list[OsintResult]:
    """Search Xbox/Gamertag profile via scraping."""
    results = []
    try:
        from shared.webdriver import get_driver, human_delay, is_blocked
        from selenium.webdriver.common.by import By

        with get_driver(stealth=True, use_proxy=True) as driver:
            driver.get(f"https://www.xbox.com/en-US/play/user/{username}")
            human_delay(3.0, 5.0)

            block = is_blocked(driver)
            if block:
                return results

            profile_data = {"username": username, "perfil_url": driver.current_url}

            try:
                gamertag = driver.find_element(By.CSS_SELECTOR, "h1, .gamertag").text
                profile_data["gamertag"] = gamertag
            except Exception:
                pass

            try:
                gamerscore = driver.find_element(By.CSS_SELECTOR, ".gamerscore, [class*='score']").text
                profile_data["gamerscore"] = gamerscore
            except Exception:
                pass

            try:
                avatar = driver.find_element(By.CSS_SELECTOR, "img[class*='avatar'], img[class*='gamerpic']")
                profile_data["avatar"] = avatar.get_attribute("src")
            except Exception:
                pass

            profile_data["page_title"] = driver.title
            if "not found" not in driver.title.lower():
                results.append(OsintResult(
                    plataforma="xbox",
                    tipo="perfil",
                    datos=profile_data,
                    timestamp=datetime.now().isoformat(),
                    fuente_url=driver.current_url,
                ))
    except Exception as e:
        logger.error(f"Xbox search error: {e}")
    return results


@rate_limited("default")
async def search_all(username: str) -> list[OsintResult]:
    """Search all gaming platforms."""
    results = []
    steam = await search_steam(username)
    results.extend(steam)
    xbox = await search_xbox(username)
    results.extend(xbox)
    return results
