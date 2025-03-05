from fastapi import FastAPI, Query, HTTPException, Depends, Path
from fastapi.middleware.cors import CORSMiddleware
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
from collections import Counter
import re
import nltk
from enum import Enum
from typing import List, Dict, Any, Optional, Union
import string
from nltk.sentiment.vader import SentimentIntensityAnalyzer
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
# Initialize NLTK resources if not already present
try:
    nltk.data.find('vader_lexicon')
except LookupError:
    nltk.download('vader_lexicon', quiet=True)

# Spanish offensive words list - can be expanded
SPANISH_OFFENSIVE_WORDS = [
    'puta', 'puto', 'pendejo', 'pendeja', 'culero', 'culera', 'joto', 'jota',
    'chinga', 'verga', 'cabron', 'cabrona', 'idiota', 'estupido', 'estupida',
    'imbecil', 'pinche', 'mierda', 'cagada', 'marica', 'maricon', 'perra',
    'zorra', 'panocha', 'coño', 'culo', 'chingada', 'chingado', 'hijo de puta',
    'puto el que lo lea', 'chinga tu madre', 'chinga a tu madre'
]


# Facebook reaction types
class ReactionType(str, Enum):
    LIKE = "like"
    LOVE = "love"
    HAHA = "haha"
    WOW = "wow"
    SAD = "sad"
    ANGRY = "angry"
    CARE = "care"

# Additional Pydantic models for group analysis
class Reaction(BaseModel):
    type: ReactionType
    count: int

class CommentSentiment(BaseModel):
    positive: float
    negative: float
    neutral: float
    compound: float

class Comment(BaseModel):
    text: str
    author: str
    timestamp: Optional[str] = None
    reactions: List[Reaction] = []
    offensive: bool = False
    likes_count: int = 0
    sentiment: Optional[CommentSentiment] = None
    replies: Optional[List["Comment"]] = []
    url: Optional[str] = None

Comment.update_forward_refs()  # Required for self-referencing models

class Post(BaseModel):
    post_id: str
    author: str
    content: str
    timestamp: Optional[str] = None
    reactions: List[Reaction] = []
    comments: List[Comment] = []
    url: str
    image_url: Optional[str] = None
    offensive: bool = False
    likes_count: int = 0
    comments_count: int = 0
    sentiment: Optional[CommentSentiment] = None

class GroupAnalysis(BaseModel):
    group_name: str
    group_id: str
    group_url: str
    members_count: Optional[int] = None
    posts: List[Post] = []
    top_comments: List[Comment] = []
    offensive_comments: List[Comment] = []
    reaction_stats: Dict[str, int] = {}
    sentiment_summary: Dict[str, float] = {}
    most_active_members: List[Dict[str, Any]] = []

@contextmanager
def get_driver():
    """Context manager for WebDriver to ensure proper cleanup"""
    driver = None
    try:
        chrome_driver_path = ChromeDriverManager().install()

        options = Options()
        # options.add_argument("--headless")
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

                # Try to extract a year if this is a car
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


# Helper functions for Facebook Group scraping
def detect_offensive_content(text: str) -> bool:
    """Detect if text contains offensive content in Spanish"""
    text_lower = text.lower()

    # Remove punctuation and split into words
    translator = str.maketrans('', '', string.punctuation)
    text_no_punctuation = text_lower.translate(translator)
    words = text_no_punctuation.split()

    # Check for offensive words
    for offensive_word in SPANISH_OFFENSIVE_WORDS:
        # Handle multi-word offensive phrases
        if ' ' in offensive_word:
            if offensive_word in text_lower:
                return True
        # Handle single offensive words
        elif offensive_word in words:
            return True

    return False


def analyze_sentiment(text: str) -> CommentSentiment:
    """Analyze sentiment of text using VADER"""
    sid = SentimentIntensityAnalyzer()
    sentiment_scores = sid.polarity_scores(text)

    return CommentSentiment(
        positive=sentiment_scores['pos'],
        negative=sentiment_scores['neg'],
        neutral=sentiment_scores['neu'],
        compound=sentiment_scores['compound']
    )


def extract_reactions(element, driver) -> List[Reaction]:
    """Extract reaction counts from a post or comment element"""
    reactions = []

    try:
        # Find reaction elements
        reaction_selectors = [
            "span[aria-label*='reaccion']",
            "span[aria-label*='reaction']",
            "div[aria-label*='reaccion']",
            "div[aria-label*='reaction']"
        ]

        for selector in reaction_selectors:
            reaction_elements = element.find_elements(By.CSS_SELECTOR, selector)
            if reaction_elements:
                break

        for reaction_element in reaction_elements:
            try:
                # Hover over reaction to see detailed breakdown
                ActionChains(driver).move_to_element(reaction_element).perform()
                time.sleep(1)

                # Try to get the tooltip with reaction details
                tooltips = driver.find_elements(By.CSS_SELECTOR, "div[role='tooltip']")
                if tooltips:
                    tooltip_text = tooltips[0].text

                    # Extract counts for each reaction type
                    for reaction_type in ReactionType:
                        pattern = None
                        if reaction_type == ReactionType.LIKE:
                            pattern = r'(\d+)\s+(?:Me gusta|Like)'
                        elif reaction_type == ReactionType.LOVE:
                            pattern = r'(\d+)\s+(?:Me encanta|Love)'
                        elif reaction_type == ReactionType.HAHA:
                            pattern = r'(\d+)\s+(?:Me divierte|Haha)'
                        elif reaction_type == ReactionType.WOW:
                            pattern = r'(\d+)\s+(?:Me asombra|Wow)'
                        elif reaction_type == ReactionType.SAD:
                            pattern = r'(\d+)\s+(?:Me entristece|Sad)'
                        elif reaction_type == ReactionType.ANGRY:
                            pattern = r'(\d+)\s+(?:Me enoja|Angry)'
                        elif reaction_type == ReactionType.CARE:
                            pattern = r'(\d+)\s+(?:Me importa|Care)'

                        if pattern:
                            match = re.search(pattern, tooltip_text, re.IGNORECASE)
                            if match:
                                count = int(match.group(1))
                                reactions.append(Reaction(type=reaction_type, count=count))
            except Exception as e:
                logger.warning(f"Error extracting reaction details: {str(e)}")

                # Fallback: Just extract the total reaction count
                try:
                    total_text = reaction_element.text.strip()
                    total_match = re.search(r'(\d+)', total_text)
                    if total_match:
                        total_count = int(total_match.group(1))
                        reactions.append(Reaction(type=ReactionType.LIKE, count=total_count))
                except:
                    pass

    except Exception as e:
        logger.warning(f"Failed to extract reactions: {str(e)}")

    return reactions


def extract_comments(post_element, driver, max_comments=50) -> List[Comment]:
    """Extract comments from a post element with improved author handling"""
    comments = []

    try:
        # Try to expand comments if needed
        try:
            expand_buttons = post_element.find_elements(By.XPATH,
                                                        "//span[contains(text(), 'Ver más comentarios') or contains(text(), 'View more comments')]")
            for button in expand_buttons[:3]:  # Limit to avoid infinite expansion
                try:
                    button.click()
                    time.sleep(2)
                except:
                    pass
        except:
            pass

        # Find comment elements
        comment_selectors = [
            "div[aria-label='Comentario']",
            "div[aria-label='Comment']",
            "div[data-testid='UFI2Comment']",
            "div.UFIComment",
            "div[role='article']"  # This might be too broad but works as fallback
        ]

        comment_elements = []
        for selector in comment_selectors:
            comment_elements = post_element.find_elements(By.CSS_SELECTOR, selector)
            if comment_elements:
                break

        for comment_element in comment_elements[:max_comments]:
            try:
                # First extract the author so we can filter it from text
                comment_url = None
                try:
                    permalink_elements = comment_element.find_elements(By.CSS_SELECTOR, "a[href*='comment_id']")
                    if permalink_elements:
                        comment_url = permalink_elements[0].get_attribute("href")
                except:
                    pass

                # Extract author
                author = extract_author(comment_element, comment_url)

                # Extract text, filtering out author name
                comment_text = extract_comment_text(comment_element, author)

                if not comment_text:
                    continue

                # Extract timestamp
                timestamp_elements = comment_element.find_elements(By.CSS_SELECTOR, "a[role='link'] span")
                timestamp = None
                for timestamp_element in timestamp_elements:
                    if "min" in timestamp_element.text or "hr" in timestamp_element.text or "h" in timestamp_element.text:
                        timestamp = timestamp_element.text
                        break

                # Extract reactions
                reactions = extract_reactions(comment_element, driver)

                # Get likes count
                likes_count = sum(reaction.count for reaction in reactions)

                # Check if offensive
                offensive = detect_offensive_content(comment_text)

                # Analyze sentiment
                sentiment = analyze_sentiment(comment_text)

                # Create comment object
                comment = Comment(
                    text=comment_text,
                    author=author,
                    timestamp=timestamp,
                    reactions=reactions,
                    offensive=offensive,
                    likes_count=likes_count,
                    sentiment=sentiment,
                    url=comment_url,
                    replies=[]
                )

                # Extract replies if any
                try:
                    reply_buttons = comment_element.find_elements(By.XPATH,
                                                                  ".//span[contains(text(), 'Ver respuestas') or contains(text(), 'View replies')]")
                    if reply_buttons:
                        reply_buttons[0].click()
                        time.sleep(2)

                        reply_elements = comment_element.find_elements(By.CSS_SELECTOR,
                                                                       "div.UFIReplyList div[role='article']")
                        for reply_element in reply_elements[:10]:  # Limit to 10 replies
                            # Extract reply author first
                            reply_url = None
                            try:
                                reply_permalink = reply_element.find_elements(By.CSS_SELECTOR, "a[href*='comment_id']")
                                if reply_permalink:
                                    reply_url = reply_permalink[0].get_attribute("href")
                            except:
                                pass

                            reply_author = extract_author(reply_element, reply_url)

                            # Then extract reply text, filtering out author
                            reply_text = extract_comment_text(reply_element, reply_author)

                            if not reply_text:
                                continue

                            reply = Comment(
                                text=reply_text,
                                author=reply_author,
                                offensive=detect_offensive_content(reply_text),
                                sentiment=analyze_sentiment(reply_text),
                                url=reply_url
                            )

                            comment.replies.append(reply)
                except Exception as e:
                    logger.warning(f"Error extracting replies: {str(e)}")

                comments.append(comment)

            except Exception as e:
                logger.warning(f"Error extracting comment: {str(e)}")
                continue

    except Exception as e:
        logger.warning(f"Failed to extract comments: {str(e)}")

    return comments


def extract_comment_text(comment_element, author_name):
    """Extract comment text with better author filtering"""
    comment_text = ""
    try:
        # First try to find comments in dedicated content elements
        content_elements = comment_element.find_elements(By.CSS_SELECTOR, "div[data-ad-comet-preview='message']")
        if content_elements:
            for element in content_elements:
                text = element.text.strip()
                if len(text) > 5:
                    comment_text = text
                    break

        # If not found, try the span approach with better filtering
        if not comment_text:
            # Get all author names to filter out
            author_names = [author_name] if author_name and author_name != "Unknown" else []
            # Add any other authors from links
            author_elements = comment_element.find_elements(By.CSS_SELECTOR, "a[role='link']")
            for a in author_elements:
                if a.text and len(a.text.strip()) > 1:
                    author_names.append(a.text.strip())

            # Remove duplicates
            author_names = list(set(author_names))

            # Collect all text from spans
            text_elements = comment_element.find_elements(By.CSS_SELECTOR, "span[dir='auto']")
            all_spans_text = []

            for element in text_elements:
                text = element.text.strip()
                # Skip empty or very short text
                if not text or len(text) < 3:
                    continue

                # Skip if text is just the author name
                if any(author in text for author in author_names):
                    # Only skip if text is very close to author name length
                    # (to avoid skipping longer text that includes the author name)
                    for author in author_names:
                        if len(text) < len(author) + 10:
                            continue

                # Skip if text is a timestamp
                if any(time_word in text.lower() for time_word in
                       ['min', 'hr', 'h', 'seg', 'hour', 'day', 'hora', 'día']):
                    if len(text) < 20:  # Only skip short timestamp texts
                        continue

                all_spans_text.append(text)

            # Use the longest text as the comment content
            if all_spans_text:
                comment_text = max(all_spans_text, key=len)
    except Exception as e:
        logger.warning(f"Error extracting comment text: {str(e)}")

    return comment_text

def extract_author(element, url=None):
    """Extract author information from a post or comment element"""
    author = "Unknown"
    try:
        # Try specific Facebook author selectors
        # Approach 1: Look for the button element containing the author name
        author_elements = element.find_elements(By.CSS_SELECTOR, "div[role='button'] span[dir='auto']")
        if author_elements and author_elements[0].text:
            author = author_elements[0].text

        # Approach 2: Look for spans with specific classes often used for author names
        if author == "Unknown":
            author_spans = element.find_elements(By.CSS_SELECTOR, "span.x193iq5w, span.xeuugli")
            for span in author_spans:
                if span.text and len(span.text) > 1:
                    author = span.text
                    break

        # Approach 3: Find the first link with role='link' that doesn't contain timestamp words
        if author == "Unknown":
            link_elements = element.find_elements(By.CSS_SELECTOR, "a[role='link']")
            for link in link_elements:
                link_text = link.text.strip()
                # Skip if empty or looks like a timestamp
                if not link_text or len(link_text) < 2:
                    continue
                if any(time_word in link_text.lower() for time_word in ['min', 'hr', 'h', 'seg', 'hour', 'día']):
                    continue
                author = link_text
                break

        # Approach 4: Try to extract from URL if all else fails
        if author == "Unknown" and url:
            # Extract author from URL in certain patterns
            url_match = re.search(r'/([^/?]+)(?:\?|/comment)', url)
            if url_match:
                url_author = url_match.group(1)
                # Clean up URL encoding
                url_author = urllib.parse.unquote(url_author)
                # Clean up other URL artifacts
                url_author = re.sub(r'pfbid\w+', '', url_author)
                # If it looks like a name (no special chars except spaces), use it
                if re.match(r'^[\w\s\-]+$', url_author) and len(url_author) > 1:
                    author = url_author
    except Exception as e:
        logger.warning(f"Error extracting author: {str(e)}")

    return author

def handle_facebook_login_dialogs(driver):
    """Handle various Facebook login/cookie dialogs that might appear"""
    try:
        # List of possible dialog selectors and buttons
        dialog_buttons = [
            (By.XPATH, '//div[@aria-label="Close" and @role="button"]'),
            (By.XPATH, '//button[contains(text(), "Accept All")]'),
            (By.XPATH, '//button[contains(text(), "Accept")]'),
            (By.XPATH, '//button[contains(text(), "Aceptar")]'),
            (By.XPATH, '//button[contains(text(), "Continue")]'),
            (By.XPATH, '//button[contains(text(), "Continuar")]'),
            (By.XPATH, '//button[contains(text(), "Not Now")]'),
            (By.XPATH, '//button[contains(text(), "Ahora no")]')
        ]

        for selector_type, selector in dialog_buttons:
            try:
                # Short timeout to quickly check for each button
                button = WebDriverWait(driver, 2).until(
                    EC.element_to_be_clickable((selector_type, selector))
                )
                button.click()
                time.sleep(1)
                logger.info(f"Clicked dialog button: {selector}")
            except:
                pass
    except Exception as e:
        logger.warning(f"Error handling login dialogs: {str(e)}")

def is_comment_url(url: str) -> bool:
    """Determine if a URL is for a comment based on its structure"""
    return "comment_id=" in url or "/comments/" in url


def extract_post_data(post_element, driver) -> Optional[Post]:
    """Extract data from a post element with improved author handling"""
    try:
        # Extract post ID from permalink
        post_id = None
        post_url = None

        permalink_elements = post_element.find_elements(By.CSS_SELECTOR, "a[href*='/posts/']")
        if permalink_elements:
            href = permalink_elements[0].get_attribute("href")
            if href:
                post_id_match = re.search(r'/posts/(\d+)', href)
                if post_id_match:
                    post_id = post_id_match.group(1)
                    post_url = href

        if not post_id:
            # Try alternate permalink format
            permalink_elements = post_element.find_elements(By.CSS_SELECTOR, "a[href*='permalink']")
            if permalink_elements:
                href = permalink_elements[0].get_attribute("href")
                if href:
                    post_id_match = re.search(r'story_fbid=(\d+)', href)
                    if post_id_match:
                        post_id = post_id_match.group(1)
                        post_url = href

        if not post_id:
            # Try to extract from comment URLs
            permalink_elements = post_element.find_elements(By.CSS_SELECTOR, "a[href*='comment_id']")
            if permalink_elements:
                href = permalink_elements[0].get_attribute("href")
                if href:
                    comment_id_match = re.search(r'comment_id=([^&]+)', href)
                    if comment_id_match:
                        post_id = comment_id_match.group(1)
                        post_url = href

            # Try to extract from group post URLs
            if not post_id:
                permalink_elements = post_element.find_elements(By.CSS_SELECTOR, "a[href*='groups/']")
                if permalink_elements:
                    href = permalink_elements[0].get_attribute("href")
                    if href:
                        group_post_match = re.search(r'groups/[^/]+/posts/(\d+)', href)
                        if group_post_match:
                            post_id = group_post_match.group(1)
                            post_url = href

        if not post_id:
            logger.warning("Could not extract post ID, skipping post")
            return None

        # Extract post author using our improved function
        author = extract_author(post_element, post_url)

        # Extract post content with better filtering
        content = ""
        try:
            # First try the direct content container
            content_containers = post_element.find_elements(By.CSS_SELECTOR, "div[data-ad-comet-preview='message']")
            for container in content_containers:
                if container.text and len(container.text) > 5:
                    content = container.text
                    break

            # If that didn't work, try span elements but with better filtering
            if not content:
                # Get author names to filter them out
                author_names = [author] if author and author != "Unknown" else []

                # Get spans with auto direction (usually content)
                span_elements = post_element.find_elements(By.CSS_SELECTOR, "span[dir='auto']")
                filtered_texts = []

                for span in span_elements:
                    text = span.text.strip()
                    # Skip empty, very short, or author name texts
                    if not text or len(text) < 5:
                        continue

                    # Skip if it's just the author name
                    if any(author in text for author in author_names) and len(text) < len(author) + 10:
                        continue

                    # Skip if it looks like metadata (short text with time indicators)
                    if len(text) < 20 and any(time_word in text.lower()
                                              for time_word in ['min', 'hr', 'hora', 'día', 'day']):
                        continue

                    filtered_texts.append(text)

                # Use the longest text as the post content
                if filtered_texts:
                    content = max(filtered_texts, key=len)
        except Exception as e:
            logger.warning(f"Error extracting post content: {str(e)}")

        # Extract timestamp
        timestamp_elements = post_element.find_elements(By.CSS_SELECTOR,
                                                        "span.timestampContent, span.fcg a, a span[aria-label]")
        timestamp = None
        for el in timestamp_elements:
            if "hr" in el.text or "min" in el.text or "h" in el.text:
                timestamp = el.text
                break

        # Extract image if any
        image_url = None
        img_elements = post_element.find_elements(By.CSS_SELECTOR, "img[src*='scontent']")
        if img_elements:
            image_url = img_elements[0].get_attribute("src")

        # Extract reactions
        reactions = extract_reactions(post_element, driver)

        # Extract likes count
        likes_count = sum(reaction.count for reaction in reactions if
                          reaction.type != ReactionType.ANGRY and reaction.type != ReactionType.SAD)

        # Extract comments
        comments = extract_comments(post_element, driver)
        comments_count = len(comments)

        # Check if post contains offensive content
        offensive = detect_offensive_content(content)

        # Analyze sentiment
        sentiment = analyze_sentiment(content)

        # Create post object
        post = Post(
            post_id=post_id,
            author=author,
            content=content,
            timestamp=timestamp,
            reactions=reactions,
            comments=comments,
            url=post_url,
            image_url=image_url,
            offensive=offensive,
            likes_count=likes_count,
            comments_count=comments_count,
            sentiment=sentiment
        )

        return post

    except Exception as e:
        logger.warning(f"Failed to extract post data: {str(e)}")
        return None


def scrape_facebook_group(
        group_id: str,
        max_posts: int = 30,
        max_scroll_attempts: int = 15
) -> GroupAnalysis:
    """
    Scrape Facebook Group to analyze posts, comments, and reactions
    with improved comment organization
    """
    with get_driver() as driver:
        # Construct the group URL
        url = f'https://www.facebook.com/groups/{group_id}'

        logger.info(f"Analyzing Facebook Group with URL: {url}")

        try:
            driver.get(url)

            # Wait for the page to load
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='main']"))
            )

            # Handle various login/cookie dialogs
            handle_facebook_login_dialogs(driver)

            # Extract group name
            group_name_element = driver.find_element(By.CSS_SELECTOR, "h1[dir='auto']")
            group_name = group_name_element.text if group_name_element else f"Group {group_id}"

            # Try to extract member count
            members_count = None
            try:
                member_elements = driver.find_elements(By.XPATH,
                                                       "//span[contains(text(), 'miembro') or contains(text(), 'member')]")
                for element in member_elements:
                    count_match = re.search(r'([\d,.]+)', element.text)
                    if count_match:
                        members_text = count_match.group(1).replace(',', '').replace('.', '')
                        members_count = int(members_text)
                        break
            except:
                logger.warning("Could not extract member count")

            # Scroll to load more posts with improved scroll mechanism
            scroll_attempts = 0
            last_post_count = 0
            stuck_count = 0

            while scroll_attempts < max_scroll_attempts:
                # Scroll down more gradually
                driver.execute_script("window.scrollBy(0, 800);")
                time.sleep(2)

                # Check if we have enough posts
                post_elements = driver.find_elements(By.CSS_SELECTOR, "div[role='article']")
                post_count = len(post_elements)

                logger.info(f"Scroll attempt {scroll_attempts + 1}/{max_scroll_attempts}: Found {post_count} posts")

                # If we've loaded enough posts, break
                if post_count >= max_posts:
                    break

                # If post count hasn't changed after scrolling, we might be stuck
                if post_count == last_post_count:
                    stuck_count += 1
                    # If we're stuck for 3 attempts, try a different scroll approach
                    if stuck_count >= 3:
                        # Try random scrolling to break out of stuck state
                        random_scroll = 500 + (scroll_attempts * 100)  # Increase scroll distance each time
                        driver.execute_script(f"window.scrollBy(0, {random_scroll});")
                        time.sleep(1)
                        driver.execute_script("window.scrollBy(0, -200);")  # Scroll back up a bit
                        time.sleep(1)
                        stuck_count = 0
                else:
                    # Reset stuck counter if we're making progress
                    stuck_count = 0

                last_post_count = post_count
                scroll_attempts += 1

                # After several scroll attempts, try to click "See More" or "Show more posts" buttons if present
                if scroll_attempts % 4 == 0:
                    try:
                        more_buttons = driver.find_elements(By.XPATH,
                                                            "//span[contains(text(), 'See More') or contains(text(), 'Ver más') or contains(text(), 'Show more')]")
                        for button in more_buttons[:2]:
                            try:
                                button.click()
                                time.sleep(2)
                            except:
                                pass
                    except:
                        pass

            # Find all post elements
            post_elements = driver.find_elements(By.CSS_SELECTOR, "div[role='article']")

            # Two-pass approach for extracting post data
            # First pass: Extract all content
            raw_items = []
            for post_element in post_elements[:max_posts]:
                try:
                    item = extract_post_data(post_element, driver)
                    if item:
                        raw_items.append(item)
                except Exception as e:
                    logger.warning(f"Error processing item: {str(e)}")
                    continue

            # Keep track of all data
            posts = []
            all_comments = []
            offensive_comments = []
            reaction_counts = Counter()

            # Second pass: Organize content
            # Identify main posts vs. comments based on URL and if they already have comments
            for item in raw_items:
                # If the item has its own comments, it's a main post
                if item.comments:
                    posts.append(item)

                    # Add to reaction counts
                    for reaction in item.reactions:
                        reaction_counts[reaction.type] += reaction.count

                    # Process comments
                    for comment in item.comments:
                        all_comments.append(comment)
                        if comment.offensive:
                            offensive_comments.append(comment)

                        # Check replies
                        if comment.replies:
                            for reply in comment.replies:
                                if reply.offensive:
                                    offensive_comments.append(reply)

                # Otherwise check if it's a main post or comment
                else:
                    is_comment = is_comment_url(item.url) if item.url else False

                    if not is_comment:
                        posts.append(item)
                        # Add to reaction counts
                        for reaction in item.reactions:
                            reaction_counts[reaction.type] += reaction.count
                    else:
                        # Convert to comment and append to appropriate post
                        comment = Comment(
                            text=item.content,
                            author=item.author,
                            timestamp=item.timestamp,
                            reactions=item.reactions,
                            offensive=item.offensive,
                            likes_count=item.likes_count,
                            sentiment=item.sentiment,
                            url=item.url
                        )

                        all_comments.append(comment)
                        if comment.offensive:
                            offensive_comments.append(comment)

                        # Try to find parent post
                        found_parent = False
                        for post in posts:
                            if item.url and post.post_id in item.url:
                                post.comments.append(comment)
                                post.comments_count += 1
                                found_parent = True
                                break

                        # If parent not found, treat as separate post
                        if not found_parent:
                            posts.append(item)

            # Sort comments by likes to get top comments
            top_comments = sorted(all_comments, key=lambda x: x.likes_count, reverse=True)[:20]

            # Calculate average sentiment
            sentiment_summary = {
                "positive": sum(p.sentiment.positive for p in posts) / len(posts) if posts else 0,
                "negative": sum(p.sentiment.negative for p in posts) / len(posts) if posts else 0,
                "neutral": sum(p.sentiment.neutral for p in posts) / len(posts) if posts else 0,
                "compound": sum(p.sentiment.compound for p in posts) / len(posts) if posts else 0
            }

            # Find most active members
            author_counts = Counter()
            for post in posts:
                if post.author != "Unknown":
                    author_counts[post.author] += 1
                for comment in post.comments:
                    if comment.author != "Unknown":
                        author_counts[comment.author] += 1

            most_active_members = [
                {"name": author, "post_count": count}
                for author, count in author_counts.most_common(10)
            ]

            # Add "Unknown" if it's the most active member
            if "Unknown" in author_counts and author_counts["Unknown"] > 0:
                most_active_members.append({"name": "Unknown", "post_count": author_counts["Unknown"]})

            # Create group analysis object
            group_analysis = GroupAnalysis(
                group_name=group_name,
                group_id=group_id,
                group_url=url,
                members_count=members_count,
                posts=posts,
                top_comments=top_comments,
                offensive_comments=offensive_comments,
                reaction_stats={k.value: v for k, v in reaction_counts.items()},
                sentiment_summary=sentiment_summary,
                most_active_members=most_active_members
            )

            return group_analysis

        except TimeoutException as e:
            logger.error(f"Timeout loading page: {str(e)}")
            raise HTTPException(status_code=504, detail="Timed out loading Facebook group")
        except WebDriverException as e:
            logger.error(f"WebDriver error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error accessing page: {str(e)}")

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


@app.get("/group/{group_id}")
async def analyze_facebook_group(
        group_id: str = Path(..., description="Facebook Group ID"),
        max_posts: int = Query(30, description="Maximum number of posts to analyze", ge=5, le=100),
        max_scroll_attempts: int = Query(15, description="Maximum number of scroll attempts", ge=5, le=30)
):
    """
    Analyze a Facebook Group's content including posts, comments, and reactions.
    Detects offensive comments, identifies top-liked comments, and categorizes reactions.
    """
    try:
        group_analysis = scrape_facebook_group(
            group_id=group_id,
            max_posts=max_posts,
            max_scroll_attempts=max_scroll_attempts
        )

        return group_analysis

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error analyzing Facebook group: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error analyzing Facebook group: {str(e)}")


@app.get("/group/{group_id}/offensive-comments")
async def get_offensive_comments(
        group_id: str = Path(..., description="Facebook Group ID"),
        max_posts: int = Query(30, description="Maximum number of posts to analyze", ge=5, le=100)
):
    """
    Retrieve offensive comments from a Facebook Group.
    """
    try:
        group_analysis = scrape_facebook_group(
            group_id=group_id,
            max_posts=max_posts
        )

        return {
            "group_name": group_analysis.group_name,
            "group_id": group_analysis.group_id,
            "offensive_comments": group_analysis.offensive_comments,
            "count": len(group_analysis.offensive_comments)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving offensive comments: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving offensive comments: {str(e)}")


@app.get("/group/{group_id}/top-comments")
async def get_top_comments(
        group_id: str = Path(..., description="Facebook Group ID"),
        max_posts: int = Query(30, description="Maximum number of posts to analyze", ge=5, le=100),
        limit: int = Query(10, description="Number of top comments to return", ge=1, le=50)
):
    """
    Retrieve top comments (most liked) from a Facebook Group.
    """
    try:
        group_analysis = scrape_facebook_group(
            group_id=group_id,
            max_posts=max_posts
        )

        # Limit to requested number
        top_comments = group_analysis.top_comments[:limit]

        return {
            "group_name": group_analysis.group_name,
            "group_id": group_analysis.group_id,
            "top_comments": top_comments,
            "count": len(top_comments)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving top comments: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving top comments: {str(e)}")


@app.get("/group/{group_id}/reaction-stats")
async def get_reaction_stats(
        group_id: str = Path(..., description="Facebook Group ID"),
        max_posts: int = Query(30, description="Maximum number of posts to analyze", ge=5, le=100)
):
    """
    Retrieve reaction statistics from a Facebook Group.
    Provides counts for different reaction types (like, love, haha, etc.)
    """
    try:
        group_analysis = scrape_facebook_group(
            group_id=group_id,
            max_posts=max_posts
        )

        return {
            "group_name": group_analysis.group_name,
            "group_id": group_analysis.group_id,
            "reaction_stats": group_analysis.reaction_stats
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving reaction stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving reaction stats: {str(e)}")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)