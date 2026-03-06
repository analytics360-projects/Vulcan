"""TikTok OSINT service — Selenium stealth scraping"""
from datetime import datetime
from config import logger
from shared.rate_limiter import rate_limited
from modules.osint_social.models import OsintResult, PlatformHealth


def get_health() -> PlatformHealth:
    return PlatformHealth(available=True, reason="Selenium stealth scraping (no API key needed)")


@rate_limited("tiktok")
async def search(username: str = None, query: str = None, max_results: int = 10) -> list[OsintResult]:
    results = []
    try:
        from shared.webdriver import get_driver, is_blocked, human_delay
        from selenium.webdriver.common.by import By

        with get_driver(stealth=True, use_proxy=True) as driver:
            # Try to login with an available TikTok account
            try:
                from shared.social_account_manager import social_account_manager
                social_account_manager.ensure_logged_in(driver, "tiktok")
            except Exception as login_err:
                logger.debug(f"TikTok login skipped (no accounts or error): {login_err}")

            if username:
                driver.get(f"https://www.tiktok.com/@{username}")
                human_delay(3.0, 5.0)

                block = is_blocked(driver)
                if block:
                    logger.warning(f"TikTok blocked ({block}) for @{username}")
                    return results

                profile_data = {"username": username}

                try:
                    bio = driver.find_element(By.CSS_SELECTOR, "h2[data-e2e='user-subtitle']").text
                    profile_data["bio"] = bio
                except Exception:
                    pass

                try:
                    name_el = driver.find_element(By.CSS_SELECTOR, "h1[data-e2e='user-title'], span[data-e2e='user-title']")
                    profile_data["nombre"] = name_el.text
                except Exception:
                    pass

                # Stats
                stat_map = {
                    "followers": "[data-e2e='followers-count']",
                    "following": "[data-e2e='following-count']",
                    "likes": "[data-e2e='likes-count']",
                }
                for key, selector in stat_map.items():
                    try:
                        el = driver.find_element(By.CSS_SELECTOR, selector)
                        profile_data[key] = el.text
                    except Exception:
                        pass

                # Profile picture
                try:
                    avatar = driver.find_element(By.CSS_SELECTOR, "[data-e2e='user-avatar'] img, .css-1zpj2q-ImgAvatar img")
                    profile_data["profile_pic"] = avatar.get_attribute("src")
                except Exception:
                    pass

                # Verified badge
                try:
                    driver.find_element(By.CSS_SELECTOR, "svg[data-e2e='verify-badge']")
                    profile_data["verificado"] = True
                except Exception:
                    profile_data["verificado"] = False

                # Recent videos
                human_delay(1.0, 2.0)
                video_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/video/']")
                videos = []
                for link in video_links[:max_results]:
                    try:
                        href = link.get_attribute("href")
                        text = link.text or ""
                        # Try to get thumbnail
                        thumb = None
                        try:
                            img = link.find_element(By.TAG_NAME, "img")
                            thumb = img.get_attribute("src")
                        except Exception:
                            pass
                        videos.append({"url": href, "texto": text[:200], "thumbnail": thumb})
                    except Exception:
                        continue
                profile_data["videos_recientes"] = videos

                results.append(OsintResult(
                    plataforma="tiktok",
                    tipo="perfil",
                    datos=profile_data,
                    timestamp=datetime.now().isoformat(),
                    fuente_url=f"https://www.tiktok.com/@{username}",
                ))

            if query:
                from urllib.parse import quote_plus
                driver.get(f"https://www.tiktok.com/search?q={quote_plus(query)}")
                human_delay(3.0, 5.0)

                block = is_blocked(driver)
                if block:
                    logger.warning(f"TikTok blocked ({block}) for search: {query}")
                    return results

                # User results
                user_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/@']")
                seen_users = set()
                for link in user_links[:5]:
                    try:
                        href = link.get_attribute("href")
                        if "/@" not in href or href in seen_users:
                            continue
                        seen_users.add(href)
                        text = link.text or ""
                        results.append(OsintResult(
                            plataforma="tiktok",
                            tipo="usuario",
                            datos={"url": href, "texto": text[:200]},
                            timestamp=datetime.now().isoformat(),
                            fuente_url=href,
                        ))
                    except Exception:
                        continue

                # Video results
                video_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/video/']")
                for link in video_links[:max_results]:
                    try:
                        href = link.get_attribute("href")
                        text = link.text or ""
                        results.append(OsintResult(
                            plataforma="tiktok",
                            tipo="video",
                            datos={"url": href, "texto": text[:200]},
                            timestamp=datetime.now().isoformat(),
                            fuente_url=href,
                        ))
                    except Exception:
                        continue

    except Exception as e:
        logger.error(f"TikTok search error: {e}")
    return results
