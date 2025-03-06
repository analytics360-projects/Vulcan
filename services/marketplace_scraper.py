from typing import List, Dict, Any
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException
from fastapi import HTTPException
import time
import re

from config import (
    DEFAULT_MAX_RESULTS, DEFAULT_MAX_SCROLL_ATTEMPTS,
    DEFAULT_SCROLL_DELAY, logger
)
from services.webdriver import get_driver, handle_facebook_dialogs, wait_for_element
from utils.extractors import (
    extract_price, extract_posted_time, extract_image_url,
    extract_marketplace_url
)


def scrape_marketplace(
        city: str,
        product: str,
        min_price: int,
        max_price: int,
        days_listed: int,
        max_results: int = DEFAULT_MAX_RESULTS,
        max_scroll_attempts: int = DEFAULT_MAX_SCROLL_ATTEMPTS
) -> List[Dict[str, Any]]:
    """
    Scrape Facebook Marketplace for product listings.

    Args:
        city (str): City to search in
        product (str): Product to search for
        min_price (int): Minimum price
        max_price (int): Maximum price
        days_listed (int): Days since listed
        max_results (int): Maximum number of results to return
        max_scroll_attempts (int): Maximum number of scroll attempts

    Returns:
        List[Dict[str, Any]]: List of product listings

    Raises:
        HTTPException: If there's an error accessing the page
    """
    with get_driver() as driver:
        # Construct the search URL
        url = (f'https://www.facebook.com/marketplace/{city}/search?'
               f'query={product}&minPrice={min_price}&maxPrice={max_price}'
               f'&daysSinceListed={days_listed}&exact=false')

        logger.info(f"Searching Marketplace with URL: {url}")

        try:
            driver.get(url)

            # Wait for the page to load - look for a specific marketplace element
            wait_for_element(driver, By.CSS_SELECTOR, "div[role='main']")

            # Handle login or cookie dialogs
            handle_facebook_dialogs(driver)

            # Scroll to load more results
            scroll_attempts = 0
            last_height = driver.execute_script("return document.body.scrollHeight")
            item_count = 0

            # Keep track of item count to avoid infinite scrolling
            while scroll_attempts < max_scroll_attempts:
                # Scroll down
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(DEFAULT_SCROLL_DELAY)  # Wait for content to load

                # Get new page height
                new_height = driver.execute_script("return document.body.scrollHeight")

                # Check if we've reached the bottom or if we have enough results
                current_items = driver.find_elements(By.CSS_SELECTOR, "div[role='article']")
                item_count = len(current_items)

                logger.info(f"Scroll attempt {scroll_attempts + 1}/{max_scroll_attempts}: Found {item_count} items")

                if item_count >= max_results or new_height == last_height:
                    break

                last_height = new_height
                scroll_attempts += 1

            # Now get all actual marketplace links using JavaScript
            marketplace_links = driver.execute_script("""
                const links = [];
                document.querySelectorAll('a[href*="/marketplace/item/"]').forEach(a => {
                    links.push(a.href);
                });
                return links;
            """)

            logger.info(f"Found {len(marketplace_links)} direct marketplace links")

            # Get page HTML for parsing with BeautifulSoup
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')

        except TimeoutException as e:
            logger.error(f"Timeout loading page: {str(e)}")
            raise HTTPException(status_code=504, detail="Timed out loading marketplace page")
        except WebDriverException as e:
            logger.error(f"WebDriver error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error accessing page: {str(e)}")

    # Extract product listings - using multiple possible selectors as FB may change layout
    product_elements = []
    selectors = [
        "div[role='article']",
        "a[href*='/marketplace/item/']",
        "div[data-testid='marketplace-feed-item']"
    ]

    for selector in selectors:
        elements = soup.select(selector)
        if elements:
            product_elements = elements
            logger.info(f"Found {len(elements)} products using selector: {selector}")
            break

    if not product_elements:
        logger.warning("No product listings found")
        return []

    # Extract data from product listings
    extracted_data = []
    link_index = 0  # To match products with direct links if possible

    for item in product_elements[:max_results]:
        try:
            # Extract product URL - first try to match with direct links we collected
            product_url = None
            if link_index < len(marketplace_links):
                product_url = marketplace_links[link_index]
                link_index += 1

            # If no direct link, try to extract from the element
            if not product_url:
                product_url = extract_marketplace_url(item)

            # Get all text content
            text_content = ' '.join(item.stripped_strings)

            # Extract price
            price = extract_price(text_content)
            if not price:
                continue  # Skip items without price

            # Extract title with improved approach
            text_parts = list(item.stripped_strings)

            # First, look for the product keyword in any text part
            product_keyword = product.lower()
            product_matches = [p for p in text_parts if product_keyword in p.lower() and len(p) > len(product_keyword)]

            if product_matches:
                # If we found text containing our product keyword, use the longest one
                title = max(product_matches, key=len)
            else:
                # Try specific title elements first
                title_element = item.find(['span', 'div'],
                                          {'class': lambda c: c and ('title' in c.lower() or 'name' in c.lower())})
                if title_element and len(title_element.text.strip()) > 5:
                    title = title_element.text
                else:
                    # Filter out location and price-like strings
                    location_pattern = re.compile(f"{city}", re.IGNORECASE)
                    price_pattern = re.compile(r'^\$?\s*[\d,.]+')

                    # Find strings that aren't just the location and don't start with price
                    potential_titles = [p for p in text_parts if
                                        len(p) > 5 and
                                        not location_pattern.search(p) and
                                        not price_pattern.match(p)]

                    # Select the most appropriate potential title
                    if potential_titles:
                        title = max(potential_titles, key=len)
                    else:
                        # If all else fails, create a title with the product name
                        title = f"{product.title()} - Unknown Model"

            # Extract location
            location_pattern = re.compile(f"{city}", re.IGNORECASE)
            location_element = item.find(string=location_pattern)
            location = location_element if location_element else city

            # Extract image URL
            image_url = extract_image_url(item)

            # Extract posted time
            posted_time = extract_posted_time(text_content)

            # Add to results if we have the essential data
            if title and price and (product_url or marketplace_links):
                # Clean up the title
                clean_title = title.strip()

                # If our product name isn't in the title, add it as a prefix
                if product.lower() not in clean_title.lower():
                    clean_title = f"{product.title()} - {clean_title}"

                # Try to extract a year if this is a car
                year_pattern = re.compile(r'\b(19|20)\d{2}\b')
                year_match = year_pattern.search(text_content)
                if year_match and year_match.group() not in clean_title:
                    clean_title = f"{year_match.group()} {clean_title}"

                # If we still don't have a URL, use a default format
                if not product_url:
                    product_url = f"https://www.facebook.com/marketplace/{city}/search?query={product}"

                extracted_data.append({
                    'title': clean_title,
                    'price': price,
                    'location': location.strip() if isinstance(location, str) else city,
                    'url': product_url,
                    'image_url': image_url,
                    'posted_time': posted_time,
                    'description': ' '.join(text_parts[:5]) if len(text_parts) > 0 else None
                })
        except Exception as e:
            logger.error(f"Error extracting data from listing: {str(e)}")
            continue

    # Sort and filter results
    sorted_data = sorted(extracted_data, key=lambda x: x.get('price', 0))

    logger.info(f"Successfully extracted {len(sorted_data)} listings")
    return sorted_data