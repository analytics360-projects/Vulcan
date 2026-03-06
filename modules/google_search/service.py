"""Google Search OSINT service — Selenium stealth scraping + site capture"""
import os
import re
import hashlib
from datetime import datetime
from urllib.parse import urlparse, urljoin, quote_plus
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from config import settings, logger
from shared.webdriver import get_driver, human_delay, is_blocked
from shared.rate_limiter import rate_limited
from modules.google_search.models import GoogleSearchResult, SiteCapture, GoogleSearchResponse

CAPTURES_DIR = Path(os.getenv("CAPTURES_DIR", "/app/captures"))

# Google dorks for finding person profiles across platforms
PLATFORM_DORKS = {
    "facebook":  'site:facebook.com "{name}"',
    "linkedin":  'site:linkedin.com/in "{name}"',
    "youtube":   'site:youtube.com "{name}"',
    "github":    'site:github.com "{name}"',
    "pinterest": 'site:pinterest.com "{name}"',
    "medium":    'site:medium.com "{name}"',
    "vimeo":     'site:vimeo.com "{name}"',
    "flickr":    'site:flickr.com "{name}"',
    "soundcloud": 'site:soundcloud.com "{name}"',
    "quora":     'site:quora.com "{name}"',
}


def _ensure_capture_dir(query: str) -> Path:
    safe_name = re.sub(r'[^\w\s-]', '', query).strip().replace(' ', '_')[:50]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = CAPTURES_DIR / f"{safe_name}_{ts}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_to_minio(local_path: str, object_name: str) -> str | None:
    """Try to upload to MinIO. Returns URL or None."""
    try:
        from minio import Minio
        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key_id,
            secret_key=settings.minio_secret_access_key,
            secure=settings.minio_secure,
        )
        bucket = "vulcan-captures"
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        client.fput_object(bucket, object_name, local_path)
        protocol = "https" if settings.minio_secure else "http"
        return f"{protocol}://{settings.minio_endpoint}/{bucket}/{object_name}"
    except Exception as e:
        logger.debug(f"MinIO upload skipped: {e}")
        return None


def search_google(query: str, max_results: int = 10) -> list[GoogleSearchResult]:
    """Search Google with stealth mode and return organic results."""
    results = []
    with get_driver(stealth=True) as driver:
        driver.get("https://www.google.com")
        human_delay(1.0, 2.0)

        # Accept cookies if prompted
        for btn_text in ["Accept", "Aceptar", "Acepto", "I agree"]:
            try:
                accept_btn = driver.find_element(By.XPATH, f'//button[contains(text(), "{btn_text}")]')
                accept_btn.click()
                human_delay(0.5, 1.0)
                break
            except Exception:
                pass

        # Search
        search_box = driver.find_element(By.NAME, "q")
        search_box.clear()
        # Type like a human — character by character with tiny delays
        import random
        for char in query:
            search_box.send_keys(char)
            if random.random() < 0.3:
                human_delay(0.05, 0.15)
        human_delay(0.5, 1.0)
        search_box.send_keys(Keys.RETURN)
        human_delay(2.0, 3.0)

        # Check for CAPTCHA
        block = is_blocked(driver)
        if block:
            logger.warning(f"Google blocked ({block}) for: {query}")
            return results

        # Parse results
        result_divs = driver.find_elements(By.CSS_SELECTOR, "div.g")
        for div in result_divs[:max_results]:
            try:
                link = div.find_element(By.CSS_SELECTOR, "a")
                href = link.get_attribute("href")
                if not href or not href.startswith("http"):
                    continue

                title_el = div.find_element(By.CSS_SELECTOR, "h3")
                title = title_el.text if title_el else ""

                snippet = ""
                try:
                    snippet_el = div.find_element(By.CSS_SELECTOR, "div.VwiC3b, span.aCOpRe, div[data-sncf='1']")
                    snippet = snippet_el.text
                except Exception:
                    pass

                domain = urlparse(href).netloc
                results.append(GoogleSearchResult(
                    titulo=title, url=href, snippet=snippet, dominio=domain
                ))
            except Exception:
                continue

        # Scroll for more results
        if len(results) < max_results:
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                human_delay(1.0, 2.0)
                more_divs = driver.find_elements(By.CSS_SELECTOR, "div.g")
                for div in more_divs[len(results):max_results]:
                    try:
                        link = div.find_element(By.CSS_SELECTOR, "a")
                        href = link.get_attribute("href")
                        if not href or not href.startswith("http"):
                            continue
                        title_el = div.find_element(By.CSS_SELECTOR, "h3")
                        title = title_el.text if title_el else ""
                        domain = urlparse(href).netloc
                        results.append(GoogleSearchResult(
                            titulo=title, url=href, snippet="", dominio=domain
                        ))
                    except Exception:
                        continue
            except Exception:
                pass

    return results


def search_google_dork(dork: str, max_results: int = 5) -> list[GoogleSearchResult]:
    """Execute a specific Google dork query."""
    return search_google(dork, max_results=max_results)


def search_person_across_platforms(name: str, platforms: list[str] = None) -> dict[str, list[GoogleSearchResult]]:
    """
    Use Google dorks to find a person across multiple platforms.
    Returns dict of platform -> results.
    """
    if platforms is None:
        platforms = list(PLATFORM_DORKS.keys())

    all_results = {}
    for platform in platforms:
        if platform not in PLATFORM_DORKS:
            continue
        dork = PLATFORM_DORKS[platform].format(name=name)
        try:
            results = search_google_dork(dork, max_results=5)
            if results:
                all_results[platform] = results
            human_delay(2.0, 4.0)  # Extra delay between dork searches
        except Exception as e:
            logger.error(f"Dork search error for {platform}: {e}")

    return all_results


def capture_site(url: str, capture_dir: Path) -> SiteCapture:
    """Visit a site, take screenshot, save HTML and download images."""
    capture = SiteCapture(url=url)
    url_hash = hashlib.md5(url.encode()).hexdigest()[:10]
    domain = urlparse(url).netloc.replace('.', '_')
    prefix = f"{domain}_{url_hash}"

    with get_driver(stealth=True) as driver:
        try:
            driver.get(url)
            human_delay(2.0, 4.0)

            # Title
            capture.titulo = driver.title or ""

            # Full-page screenshot
            screenshot_path = capture_dir / f"{prefix}_screenshot.png"
            # Try full page first
            try:
                total_height = driver.execute_script("return document.body.scrollHeight")
                driver.set_window_size(1920, min(total_height, 10000))
                human_delay(0.5, 1.0)
            except Exception:
                pass
            driver.save_screenshot(str(screenshot_path))
            capture.screenshot_path = str(screenshot_path)

            minio_url = _save_to_minio(str(screenshot_path), f"{prefix}_screenshot.png")
            if minio_url:
                capture.screenshot_path = minio_url

            # HTML
            html_content = driver.page_source
            html_path = capture_dir / f"{prefix}.html"
            html_path.write_text(html_content, encoding="utf-8")
            capture.html_path = str(html_path)

            minio_url = _save_to_minio(str(html_path), f"{prefix}.html")
            if minio_url:
                capture.html_path = minio_url

            # Extract text
            soup = BeautifulSoup(html_content, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            capture.texto_extraido = soup.get_text(separator="\n", strip=True)[:5000]

            # Meta data
            meta = {}
            for tag in soup.find_all("meta"):
                name = tag.get("name") or tag.get("property", "")
                content = tag.get("content", "")
                if name and content:
                    meta[name] = content[:200]
            capture.meta_datos = meta

            # Download images
            img_dir = capture_dir / f"{prefix}_images"
            img_dir.mkdir(exist_ok=True)
            img_elements = driver.find_elements(By.TAG_NAME, "img")
            downloaded = 0

            for img in img_elements[:20]:
                try:
                    src = img.get_attribute("src")
                    if not src or src.startswith("data:"):
                        continue
                    src = urljoin(url, src)
                    img_resp = httpx.get(src, timeout=10, follow_redirects=True)
                    if img_resp.status_code == 200 and "image" in img_resp.headers.get("content-type", ""):
                        ext = _guess_extension(img_resp.headers.get("content-type", ""))
                        img_filename = f"img_{downloaded:03d}{ext}"
                        img_path = img_dir / img_filename
                        img_path.write_bytes(img_resp.content)
                        capture.imagenes.append(str(img_path))
                        _save_to_minio(str(img_path), f"{prefix}_images/{img_filename}")
                        downloaded += 1
                except Exception:
                    continue

        except Exception as e:
            logger.error(f"Error capturing site {url}: {e}")

    return capture


def _guess_extension(content_type: str) -> str:
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
    }
    return mapping.get(content_type.split(";")[0].strip(), ".jpg")


@rate_limited("google")
async def search_and_capture(
    query: str,
    max_results: int = 10,
    max_captures: int = 5,
) -> GoogleSearchResponse:
    """Search Google, then visit and capture top results."""
    response = GoogleSearchResponse(query=query)

    try:
        results = search_google(query, max_results=max_results)
        response.resultados = results
        response.total_resultados = len(results)
    except Exception as e:
        logger.error(f"Google search error: {e}")
        response.errores.append(f"search: {e}")
        return response

    # Capture top sites
    if results:
        capture_dir = _ensure_capture_dir(query)
        for result in results[:max_captures]:
            try:
                capture = capture_site(result.url, capture_dir)
                response.capturas.append(capture)
            except Exception as e:
                logger.error(f"Capture error for {result.url}: {e}")
                response.errores.append(f"capture {result.url}: {e}")

    return response


@rate_limited("google")
async def dork_search_person(name: str, platforms: list[str] = None) -> dict:
    """Search a person across platforms using Google dorks."""
    results = search_person_across_platforms(name, platforms)
    return {
        platform: [r.model_dump() for r in items]
        for platform, items in results.items()
    }
