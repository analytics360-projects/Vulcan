"""Marketplace scraper — moved from services/marketplace_scraper.py"""
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException
from fastapi import HTTPException
import time
import re

from config import settings, logger
from shared.webdriver import get_driver, handle_facebook_dialogs, wait_for_element
from shared.extractors import extract_price, extract_posted_time, extract_image_url, extract_marketplace_url


def scrape_marketplace(
    city: str,
    product: str,
    min_price: int,
    max_price: int,
    days_listed: int,
    max_results: int = None,
    max_scroll_attempts: int = None,
) -> List[Dict[str, Any]]:
    max_results = max_results or settings.max_results
    max_scroll_attempts = max_scroll_attempts or settings.max_scroll_attempts

    with get_driver() as driver:
        url = (
            f"https://www.facebook.com/marketplace/{city}/search?"
            f"query={product}&minPrice={min_price}&maxPrice={max_price}"
            f"&daysSinceListed={days_listed}&exact=false"
        )
        logger.info(f"Searching Marketplace: {url}")

        try:
            driver.get(url)
            wait_for_element(driver, By.CSS_SELECTOR, "div[role='main']")
            handle_facebook_dialogs(driver)

            scroll_attempts = 0
            last_height = driver.execute_script("return document.body.scrollHeight")

            while scroll_attempts < max_scroll_attempts:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(settings.scroll_delay)
                new_height = driver.execute_script("return document.body.scrollHeight")
                current_items = driver.find_elements(By.CSS_SELECTOR, "div[role='article']")
                if len(current_items) >= max_results or new_height == last_height:
                    break
                last_height = new_height
                scroll_attempts += 1

            marketplace_links = driver.execute_script("""
                const links = [];
                document.querySelectorAll('a[href*="/marketplace/item/"]').forEach(a => links.push(a.href));
                return links;
            """)
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, "html.parser")

        except TimeoutException:
            raise HTTPException(status_code=504, detail="Timed out loading marketplace page")
        except WebDriverException as e:
            raise HTTPException(status_code=500, detail=f"Error accessing page: {e}")

    selectors = ["div[role='article']", "a[href*='/marketplace/item/']", "div[data-testid='marketplace-feed-item']"]
    product_elements = []
    for sel in selectors:
        elements = soup.select(sel)
        if elements:
            product_elements = elements
            break

    if not product_elements:
        return []

    extracted = []
    link_idx = 0

    for item in product_elements[:max_results]:
        try:
            product_url = marketplace_links[link_idx] if link_idx < len(marketplace_links) else None
            link_idx += 1
            if not product_url:
                product_url = extract_marketplace_url(item)

            text_content = " ".join(item.stripped_strings)
            price = extract_price(text_content)
            if not price:
                continue

            text_parts = list(item.stripped_strings)
            keyword = product.lower()
            matches = [p for p in text_parts if keyword in p.lower() and len(p) > len(keyword)]

            if matches:
                title = max(matches, key=len)
            else:
                title_el = item.find(["span", "div"], {"class": lambda c: c and ("title" in c.lower() or "name" in c.lower())})
                if title_el and len(title_el.text.strip()) > 5:
                    title = title_el.text
                else:
                    loc_pat = re.compile(city, re.IGNORECASE)
                    pr_pat = re.compile(r"^\$?\s*[\d,.]+")
                    potentials = [p for p in text_parts if len(p) > 5 and not loc_pat.search(p) and not pr_pat.match(p)]
                    title = max(potentials, key=len) if potentials else f"{product.title()} - Unknown Model"

            loc_el = item.find(string=re.compile(city, re.IGNORECASE))
            location = loc_el if loc_el else city
            image_url = extract_image_url(item)
            posted_time = extract_posted_time(text_content)

            if title and price:
                clean_title = title.strip()
                if product.lower() not in clean_title.lower():
                    clean_title = f"{product.title()} - {clean_title}"
                year_match = re.search(r"\b(19|20)\d{2}\b", text_content)
                if year_match and year_match.group() not in clean_title:
                    clean_title = f"{year_match.group()} {clean_title}"
                if not product_url:
                    product_url = f"https://www.facebook.com/marketplace/{city}/search?query={product}"

                extracted.append({
                    "title": clean_title,
                    "price": price,
                    "location": location.strip() if isinstance(location, str) else city,
                    "url": product_url,
                    "image_url": image_url,
                    "posted_time": posted_time,
                    "description": " ".join(text_parts[:5]) if text_parts else None,
                })
        except Exception as e:
            logger.error(f"Error extracting listing: {e}")
            continue

    return sorted(extracted, key=lambda x: x.get("price", 0))
