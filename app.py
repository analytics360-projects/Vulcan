from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time
import re
import pandas as pd
import logging
import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from contextlib import contextmanager
import os
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("marketplace_scraper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("marketplace_scraper")


# Pydantic models for request and response validation
class MarketplaceItem(BaseModel):
    title: str
    price: float
    location: str
    url: str
    image_url: Optional[str] = None
    posted_time: Optional[str] = None
    description: Optional[str] = None


class MarketplaceSearchResults(BaseModel):
    results: List[MarketplaceItem]
    count: int
    query_params: Dict[str, Any]
    timestamp: str


app = FastAPI(
    title="Facebook Marketplace Scraper API",
    description="API for scraping product listings from Facebook Marketplace",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Set specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@contextmanager
def get_driver():
    """Context manager for WebDriver to ensure proper cleanup"""
    driver = None
    try:
        chrome_driver_path = ChromeDriverManager().install()

        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        # Use a realistic user agent
        options.add_argument(
            "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        driver = webdriver.Chrome(service=Service(chrome_driver_path), options=options)
        driver.set_page_load_timeout(30)
        yield driver
    except Exception as e:
        logger.error(f"Error setting up WebDriver: {str(e)}")
        raise
    finally:
        if driver:
            driver.quit()


def extract_price(text: str) -> Optional[float]:
    """Extract price from text with better handling of currency formats"""
    # Look for patterns like $1,234.56 or 1,234.56€ or 1.234,56€
    price_pattern = re.compile(r'(?:[$€£¥])?(?:\s)?([0-9][0-9\s,.]*(?:\.[0-9]{2}|\,[0-9]{2})?)\s?(?:[$€£¥])?')

    # First, try to find price patterns that aren't part of a year
    matches = price_pattern.finditer(text)
    price_candidates = []

    for match in matches:
        price_str = match.group(1)
        # Skip if it's a 4-digit number that looks like a year (for car listings)
        if re.match(r'^(19|20)\d{2}$', price_str):
            continue
        price_candidates.append(price_str)

    # If no candidates found, return None
    if not price_candidates:
        return None

    # Process the most likely price candidate (usually the first one)
    price_str = price_candidates[0]

    # Remove any spaces in the number
    price_str = price_str.replace(' ', '')

    # Fix an issue with years being appended to prices (like 2010 in 165.0002012)
    # This happens with car listings where the year might be parsed as part of the price
    if len(price_str) > 8 and ('.' in price_str or ',' in price_str):
        # Find the decimal point position
        decimal_pos = price_str.find('.') if '.' in price_str else price_str.find(',')
        if decimal_pos > 0 and len(price_str) - decimal_pos > 6:
            # Truncate to a reasonable number of decimal places
            price_str = price_str[:decimal_pos + 3]

    # Handle both US and European number formats
    try:
        # US format: 1,234.56
        if '.' in price_str and ',' in price_str and price_str.rindex('.') > price_str.rindex(','):
            price_str = price_str.replace(',', '')
            return float(price_str)
        # European format: 1.234,56
        elif '.' in price_str and ',' in price_str and price_str.rindex(',') > price_str.rindex('.'):
            price_str = price_str.replace('.', '').replace(',', '.')
            return float(price_str)
        # Just decimal point
        elif '.' in price_str and ',' not in price_str:
            return float(price_str)
        # Just comma as decimal
        elif ',' in price_str and '.' not in price_str:
            price_str = price_str.replace(',', '.')
            return float(price_str)
        # No decimal separator
        else:
            return float(price_str)
    except Exception as e:
        logger.warning(f"Failed to parse price from '{price_str}': {str(e)}")
        return None


def extract_image_url(item_element) -> Optional[str]:
    """Extract image URL from product element"""
    try:
        # Look for image elements - multiple possible patterns
        img_tag = item_element.find('img')
        if img_tag and img_tag.get('src'):
            return img_tag.get('src')

        # Try background image in style attribute
        div_with_bg = item_element.find('div', style=lambda value: value and 'background-image' in value)
        if div_with_bg:
            style = div_with_bg.get('style', '')
            url_match = re.search(r'url\([\'"]?(.*?)[\'"]?\)', style)
            if url_match:
                return url_match.group(1)
    except Exception as e:
        logger.warning(f"Failed to extract image URL: {str(e)}")

    return None


def extract_posted_time(text: str) -> Optional[str]:
    """Extract posting time information from listing text"""
    time_patterns = [
        r'posted\s+(\d+\s+(?:minute|hour|day|week|month)s?\s+ago)',
        r'listed\s+(\d+\s+(?:minute|hour|day|week|month)s?\s+ago)',
        r'(\d+\s+(?:minute|hour|day|week|month)s?\s+ago)'
    ]

    for pattern in time_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def scrape_marketplace(
        city: str,
        product: str,
        min_price: int,
        max_price: int,
        days_listed: int,
        max_results: int = 100,
        max_scroll_attempts: int = 10
) -> List[Dict[str, Any]]:
    """
    Scrape Facebook Marketplace for product listings with improved extraction
    and pagination handling
    """
    with get_driver() as driver:
        # Construct the search URL
        url = f'https://www.facebook.com/marketplace/{city}/search?query={product}&minPrice={min_price}&maxPrice={max_price}&daysSinceListed={days_listed}&exact=false'

        logger.info(f"Searching Marketplace with URL: {url}")

        try:
            driver.get(url)

            # Wait for the page to load - look for a specific marketplace element
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='main']"))
            )

            # Handle login or cookie dialogs
            try:
                # Allow a short timeout to find and close dialogs
                WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, '//div[@aria-label="Close" and @role="button"]'))
                ).click()
                logger.info("Closed dialog popup")
            except TimeoutException:
                logger.info("No dialog popups found or they couldn't be closed")

            # Scroll to load more results
            scroll_attempts = 0
            last_height = driver.execute_script("return document.body.scrollHeight")
            item_count = 0

            # Keep track of item count to avoid infinite scrolling
            while scroll_attempts < max_scroll_attempts:
                # Scroll down
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)  # Wait for content to load

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

            # Get page source after scrolling
            page_source = driver.page_source

        except TimeoutException as e:
            logger.error(f"Timeout loading page: {str(e)}")
            raise HTTPException(status_code=504, detail="Timed out loading marketplace page")
        except WebDriverException as e:
            logger.error(f"WebDriver error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error accessing page: {str(e)}")

    # Parse with BeautifulSoup
    soup = BeautifulSoup(page_source, 'html.parser')

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

    for item in product_elements[:max_results]:
        try:
            # Extract product URL
            product_url = None
            link_element = item.find('a', href=lambda h: h and '/marketplace/item/' in h)
            if link_element:
                href = link_element.get('href')
                product_url = "https://www.facebook.com" + href.split('?')[0] if href else None

            # Get all text content
            text_content = ' '.join(item.stripped_strings)

            # Extract price
            price = extract_price(text_content)
            if not price:
                continue  # Skip items without price

            # Extract title with improved approach
            # Get all text fragments
            text_parts = list(item.stripped_strings)

            # First, look for the product keyword in any text part
            product_keyword = product.lower()
            product_matches = [p for p in text_parts if product_keyword in p.lower() and len(p) > len(product_keyword)]

            if product_matches:
                # If we found text containing our product keyword, use the longest one
                title = max(product_matches, key=len)
            else:
                # Otherwise try to find title-like elements
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
                        # Try to filter potential titles to include product-related ones
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
            if title and price:
                # Clean up the title to remove excessive whitespace and ensure product name is visible
                clean_title = title.strip()

                # If our product name isn't in the title, add it as a prefix
                if product.lower() not in clean_title.lower():
                    clean_title = f"{product.title()} - {clean_title}"

                # Try to extract a year if this is a car (like Mustang)
                year_pattern = re.compile(r'\b(19|20)\d{2}\b')
                year_match = year_pattern.search(text_content)
                if year_match and year_match.group() not in clean_title:
                    clean_title = f"{year_match.group()} {clean_title}"

                extracted_data.append({
                    'title': clean_title,
                    'price': price,
                    'location': location.strip() if isinstance(location, str) else city,
                    'url': product_url or "No URL",
                    'image_url': image_url,
                    'posted_time': posted_time,
                    # Add additional information that may help identify the listing
                    'description': ' '.join(text_parts[:5]) if len(text_parts) > 0 else None
                })
        except Exception as e:
            logger.error(f"Error extracting data from listing: {str(e)}")
            continue

    # Sort and filter results
    sorted_data = sorted(extracted_data, key=lambda x: x.get('price', 0))

    logger.info(f"Successfully extracted {len(sorted_data)} listings")
    return sorted_data


@app.get("/search", response_model=MarketplaceSearchResults)
async def search_marketplace(
        city: str = Query(..., description="City to search in"),
        product: str = Query(..., description="Product to search for"),
        min_price: int = Query(0, description="Minimum price", ge=0),
        max_price: int = Query(1000, description="Maximum price", ge=0),
        days_listed: int = Query(7, description="Days since listed", ge=1, le=30),
        max_results: int = Query(50, description="Maximum number of results to return", ge=1, le=200)
):
    """
    Search Facebook Marketplace for products matching the specified criteria.
    Returns a list of product listings with details and prices.
    """
    try:
        results = scrape_marketplace(
            city=city,
            product=product,
            min_price=min_price,
            max_price=max_price,
            days_listed=days_listed,
            max_results=max_results
        )

        # Prepare response
        response = {
            "results": results,
            "count": len(results),
            "query_params": {
                "city": city,
                "product": product,
                "min_price": min_price,
                "max_price": max_price,
                "days_listed": days_listed,
                "max_results": max_results
            },
            "timestamp": datetime.now().isoformat()
        }

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in search endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/health")
async def health_check():
    """Check if the API is up and running"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/export/{format}")
async def export_results(
        format: str,  # Path parameter, not a Query parameter
        city: str = Query(..., description="City to search in"),
        product: str = Query(..., description="Product to search for"),
        min_price: int = Query(0, description="Minimum price"),
        max_price: int = Query(1000, description="Maximum price"),
        days_listed: int = Query(7, description="Days since listed")
):
    """Export search results to CSV or JSON"""
    if format not in ["csv", "json"]:
        raise HTTPException(status_code=400, detail="Format must be either 'csv' or 'json'")

    results = scrape_marketplace(city, product, min_price, max_price, days_listed)

    filename = f"{product}_{city}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    if format == "csv":
        df = pd.DataFrame(results)
        csv_content = df.to_csv(index=False)
        return {"filename": f"{filename}.csv", "content": csv_content}
    else:
        return {"filename": f"{filename}.json", "content": results}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)