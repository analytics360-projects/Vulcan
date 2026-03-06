"""Instagram OSINT service — Selenium stealth scraping (no API key needed)"""
from datetime import datetime
from config import logger
from shared.rate_limiter import rate_limited
from modules.osint_social.models import OsintResult, PlatformHealth


def get_health() -> PlatformHealth:
    return PlatformHealth(available=True, reason="Selenium stealth scraping (no API key needed)")


@rate_limited("instagram")
async def search(username: str = None, hashtag: str = None, max_results: int = 10) -> list[OsintResult]:
    results = []
    try:
        from shared.webdriver import get_driver, is_blocked, human_delay
        from selenium.webdriver.common.by import By

        with get_driver(stealth=True, use_proxy=True) as driver:
            if username:
                driver.get(f"https://www.instagram.com/{username}/")
                human_delay(3.0, 5.0)

                # Handle popups
                for btn_text in ["Not Now", "Ahora no", "Accept", "Aceptar", "Allow", "Permitir"]:
                    try:
                        btn = driver.find_element(By.XPATH, f'//button[contains(text(), "{btn_text}")]')
                        btn.click()
                        human_delay(0.5, 1.5)
                    except Exception:
                        pass

                # Check for blocks
                block = is_blocked(driver)
                if block:
                    logger.warning(f"Instagram blocked ({block}) for @{username}")
                    results.append(OsintResult(
                        plataforma="instagram",
                        tipo="error",
                        datos={"username": username, "bloqueado": True, "razon": block},
                        timestamp=datetime.now().isoformat(),
                        fuente_url=f"https://instagram.com/{username}",
                        confianza=0.0,
                    ))
                    return results

                profile_data = {"username": username}

                # Profile name
                try:
                    header = driver.find_element(By.CSS_SELECTOR, "header section")
                    profile_data["nombre"] = header.find_element(By.CSS_SELECTOR, "span").text
                except Exception:
                    pass

                # Bio
                try:
                    bio_el = driver.find_element(By.CSS_SELECTOR, "header section div.-vDIg span, header section div._aa_c")
                    profile_data["bio"] = bio_el.text
                except Exception:
                    try:
                        header = driver.find_element(By.TAG_NAME, "header")
                        profile_data["bio_raw"] = header.text[:500]
                    except Exception:
                        pass

                # Stats (followers, following, posts)
                try:
                    stat_elements = driver.find_elements(By.CSS_SELECTOR, "header section ul li span span, header section ul li a span")
                    if len(stat_elements) >= 3:
                        profile_data["posts"] = stat_elements[0].text
                        profile_data["followers"] = stat_elements[1].text
                        profile_data["following"] = stat_elements[2].text
                    elif len(stat_elements) > 0:
                        profile_data["stats_raw"] = [el.text for el in stat_elements]
                except Exception:
                    pass

                # Profile picture
                try:
                    img = driver.find_element(By.CSS_SELECTOR, "header img")
                    profile_data["profile_pic"] = img.get_attribute("src")
                except Exception:
                    pass

                # Check if private
                try:
                    page_text = driver.find_element(By.TAG_NAME, "body").text
                    profile_data["es_privado"] = "This account is private" in page_text or "Esta cuenta es privada" in page_text
                except Exception:
                    profile_data["es_privado"] = False

                # Recent posts (if public)
                post_links = driver.find_elements(By.CSS_SELECTOR, "article a[href*='/p/'], main a[href*='/p/']")
                posts = []
                for link in post_links[:max_results]:
                    try:
                        href = link.get_attribute("href")
                        img_el = link.find_element(By.TAG_NAME, "img")
                        img_src = img_el.get_attribute("src") if img_el else None
                        alt_text = img_el.get_attribute("alt") if img_el else ""
                        posts.append({"url": href, "imagen": img_src, "descripcion": alt_text[:200]})
                    except Exception:
                        continue
                profile_data["posts_recientes"] = posts
                profile_data["page_title"] = driver.title

                results.append(OsintResult(
                    plataforma="instagram",
                    tipo="perfil",
                    datos=profile_data,
                    timestamp=datetime.now().isoformat(),
                    fuente_url=f"https://instagram.com/{username}",
                ))

            if hashtag:
                tag = hashtag.lstrip("#")
                driver.get(f"https://www.instagram.com/explore/tags/{tag}/")
                human_delay(3.0, 5.0)

                for btn_text in ["Not Now", "Ahora no"]:
                    try:
                        btn = driver.find_element(By.XPATH, f'//button[contains(text(), "{btn_text}")]')
                        btn.click()
                        human_delay(0.5, 1.0)
                    except Exception:
                        pass

                block = is_blocked(driver)
                if block:
                    logger.warning(f"Instagram blocked ({block}) for #{tag}")
                    return results

                hashtag_data = {"hashtag": tag}
                try:
                    count_el = driver.find_element(By.CSS_SELECTOR, "header span span, header span")
                    hashtag_data["total_posts"] = count_el.text
                except Exception:
                    pass

                post_links = driver.find_elements(By.CSS_SELECTOR, "article a[href*='/p/'], main a[href*='/p/']")
                posts = []
                for link in post_links[:max_results]:
                    try:
                        href = link.get_attribute("href")
                        img_el = link.find_element(By.TAG_NAME, "img")
                        img_src = img_el.get_attribute("src") if img_el else None
                        posts.append({"url": href, "imagen": img_src})
                    except Exception:
                        continue
                hashtag_data["top_posts"] = posts

                results.append(OsintResult(
                    plataforma="instagram",
                    tipo="hashtag",
                    datos=hashtag_data,
                    timestamp=datetime.now().isoformat(),
                    fuente_url=f"https://instagram.com/explore/tags/{tag}/",
                ))

    except Exception as e:
        logger.error(f"Instagram search error: {e}")
    return results
