"""TikTok OSINT service — Selenium headless scraping"""
from datetime import datetime
from config import settings, logger
from shared.rate_limiter import rate_limited
from modules.osint_social.models import OsintResult, PlatformHealth


def get_health() -> PlatformHealth:
    return PlatformHealth(available=True, reason="Selenium scraping (no API key needed)")


@rate_limited("tiktok")
async def search(username: str = None, query: str = None, max_results: int = 10) -> list[OsintResult]:
    results = []
    try:
        from shared.webdriver import get_driver
        from selenium.webdriver.common.by import By
        import time

        with get_driver() as driver:
            if username:
                driver.get(f"https://www.tiktok.com/@{username}")
                time.sleep(3)
                try:
                    bio = driver.find_element(By.CSS_SELECTOR, "h2[data-e2e='user-subtitle']").text
                except Exception:
                    bio = ""
                try:
                    followers = driver.find_element(By.CSS_SELECTOR, "[data-e2e='followers-count']").text
                except Exception:
                    followers = "0"
                results.append(OsintResult(
                    plataforma="tiktok",
                    tipo="perfil",
                    datos={"username": username, "bio": bio, "followers": followers},
                    timestamp=datetime.now().isoformat(),
                    fuente_url=f"https://www.tiktok.com/@{username}",
                ))

            if query:
                driver.get(f"https://www.tiktok.com/search?q={query}")
                time.sleep(3)
                video_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/video/']")
                for link in video_links[:max_results]:
                    href = link.get_attribute("href")
                    text = link.text or ""
                    results.append(OsintResult(
                        plataforma="tiktok",
                        tipo="video",
                        datos={"url": href, "text": text[:200]},
                        timestamp=datetime.now().isoformat(),
                        fuente_url=href,
                    ))
    except Exception as e:
        logger.error(f"TikTok search error: {e}")
    return results
