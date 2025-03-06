from typing import List, Dict, Any, Optional
import requests
import feedparser
from bs4 import BeautifulSoup
from urllib.parse import urlencode, quote_plus, urlparse, parse_qs
import re
import time
from fastapi import HTTPException

from config import logger
from services.webdriver import get_driver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException


def extract_original_url(google_url: str) -> str:
    """
    Extract the original article URL from Google News redirect URL.

    Args:
        google_url (str): Google News redirect URL

    Returns:
        str: Original article URL
    """
    try:
        # Skip extraction if it's not a Google URL
        if 'news.google.com' not in google_url:
            return google_url

        # Method 1: Try a direct request to follow redirects
        try:
            session = requests.Session()
            # Set a user agent to avoid being blocked
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            # Make a HEAD request first (faster) with timeout
            response = session.head(google_url, headers=headers, allow_redirects=True, timeout=5)

            # If HEAD doesn't work (some sites block it), try GET
            if 'news.google.com' in response.url:
                response = session.get(google_url, headers=headers, allow_redirects=True, timeout=5)

            # If we've been redirected away from Google, we have our URL
            if 'news.google.com' not in response.url:
                return response.url
        except Exception as e:
            logger.warning(f"Error following redirect: {str(e)}")

        # Method 2: Try to extract from HTML content
        try:
            response = requests.get(google_url, headers=headers, timeout=5)
            soup = BeautifulSoup(response.text, 'html.parser')

            # Google News often uses a meta refresh tag or canonical link
            meta_refresh = soup.find('meta', attrs={'http-equiv': 'refresh'})
            if meta_refresh:
                content = meta_refresh.get('content', '')
                url_match = re.search(r'URL=\'?(.*?)\'?$', content)
                if url_match:
                    return url_match.group(1)

            canonical = soup.find('link', rel='canonical')
            if canonical and 'news.google.com' not in canonical['href']:
                return canonical['href']

            # Look for redirects in JavaScript
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string:
                    url_match = re.search(r'window.location.replace\([\'"]([^\'"]+)[\'"]\)', script.string)
                    if url_match:
                        return url_match.group(1)
        except Exception as e:
            logger.warning(f"Error extracting from HTML: {str(e)}")

        # Method 3: Use Selenium as a last resort
        with get_driver() as driver:
            try:
                driver.get(google_url)
                time.sleep(3)  # Wait for redirects

                # Get the final URL
                final_url = driver.current_url

                # If we've been redirected away from Google, return the new URL
                if 'news.google.com' not in final_url:
                    return final_url

                # Otherwise try to find any obvious redirect links
                links = driver.find_elements(By.TAG_NAME, 'a')
                for link in links:
                    href = link.get_attribute('href')
                    if href and 'news.google.com' not in href and (
                            href.startswith('http://') or href.startswith('https://')):
                        return href
            except Exception as e:
                logger.warning(f"Error using Selenium for extraction: {str(e)}")

        # If all methods fail, extract the article URL directly from Google News HTML
        try:
            # For RSS links, try to parse the URL from the summary
            if '/rss/' in google_url:
                # Get the original response again to parse the summary
                response = requests.get(google_url, headers=headers, timeout=5)
                soup = BeautifulSoup(response.text, 'html.parser')

                # Find the first link in the article which should be the original source
                first_link = soup.find('a')
                if first_link and 'news.google.com' not in first_link['href']:
                    return first_link['href']

                # If we still don't have a URL, try to find it in any iframe
                iframes = soup.find_all('iframe')
                for iframe in iframes:
                    src = iframe.get('src')
                    if src and 'news.google.com' not in src:
                        return src
        except Exception as e:
            logger.warning(f"Error extracting from Google News HTML: {str(e)}")

        # If all else fails, try to directly use the article link from the RSS feed entry
        # This often doesn't work for Google News, but we'll try it anyway
        if '/rss/articles/' in google_url and '?oc=5' in google_url:
            try:
                # Remove the ?oc=5 parameter
                clean_url = google_url.split('?oc=5')[0]

                # Construct a direct URL to the article
                article_id = clean_url.split('/rss/articles/')[1]
                return f"https://news.google.com/articles/{article_id}"
            except Exception as e:
                logger.warning(f"Error constructing direct article URL: {str(e)}")

        # If all methods fail, return the original Google URL
        return google_url

    except Exception as e:
        logger.warning(f"Error extracting original URL: {str(e)}")
        return google_url


def fetch_google_news(
        query: str,
        language: str = "en",
        country: str = "US",
        max_results: int = 10
) -> List[Dict[str, Any]]:
    """
    Fetch news articles from Google News RSS feed and extract original URLs.

    Args:
        query (str): Search query
        language (str): Language code (e.g., 'en', 'es')
        country (str): Country code (e.g., 'US', 'UK')
        max_results (int): Maximum number of results to return

    Returns:
        List[Dict[str, Any]]: List of news articles with metadata
    """
    # Construct the RSS feed URL
    base_url = "https://news.google.com/rss/search"
    params = {
        "q": query,
        "hl": f"{language}-{country}",
        "gl": country,
        "ceid": f"{country}:{language}"
    }

    # For trending news, use a different URL
    if not query:
        base_url = "https://news.google.com/rss"

    feed_url = f"{base_url}?{urlencode(params, quote_via=quote_plus)}" if query else base_url

    try:
        # Parse the RSS feed
        feed = feedparser.parse(feed_url)

        if not feed.entries:
            logger.warning(f"No news found for query: {query}")
            return []

        # Process feed entries
        articles = []

        # For trending news or regular searches
        for entry in feed.entries[:max_results]:
            try:
                # Extract source from title (Google News format: "Title - Source")
                title_parts = entry.title.split(" - ")
                source = title_parts[-1] if len(title_parts) > 1 else "Unknown"
                title = " - ".join(title_parts[:-1]) if len(title_parts) > 1 else entry.title

                # Extract direct URL from summary HTML if possible
                original_url = None
                if hasattr(entry, 'summary'):
                    soup = BeautifulSoup(entry.summary, 'html.parser')
                    first_link = soup.find('a')
                    if first_link and first_link.has_attr('href'):
                        href = first_link['href']
                        if 'news.google.com' not in href:
                            original_url = href

                # If we couldn't extract from summary, try to follow the redirect
                if not original_url:
                    original_url = extract_original_url(entry.link)

                # Get domain for the article
                try:
                    domain = urlparse(original_url).netloc if original_url else "news.google.com"
                except:
                    domain = "news.google.com"

                article = {
                    "title": title,
                    "source": source,
                    "url": original_url if original_url and 'news.google.com' not in original_url else entry.link,
                    "google_url": entry.link,
                    "domain": domain,
                    "published": entry.published,
                    "summary": getattr(entry, "summary", ""),
                    "article_content": None,
                    "image_url": None,
                }

                articles.append(article)

            except Exception as e:
                logger.warning(f"Error processing feed entry: {str(e)}")
                continue

        return articles

    except Exception as e:
        logger.error(f"Error fetching Google News RSS feed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching news: {str(e)}")


def extract_article_content(url: str) -> Dict[str, Any]:
    """
    Extract content and main image from a news article URL.

    Args:
        url (str): URL of the article

    Returns:
        Dict[str, Any]: Dictionary containing article content and image URL
    """
    with get_driver() as driver:
        try:
            driver.get(url)
            time.sleep(2)  # Allow page to load

            # Get the page HTML
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')

            # Extract the main content
            # Try various common article content selectors
            content_selectors = [
                "article",
                'div[itemprop="articleBody"]',
                'div.article-content',
                'div.entry-content',
                'div.post-content',
                'div.story-content',
                'div.story-body',
                '.article-body',
                'main'
            ]

            content = ""
            for selector in content_selectors:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    content = elements[0].text
                    break

            # If no content found, try a more generic approach
            if not content:
                # Get all paragraphs
                paragraphs = driver.find_elements(By.TAG_NAME, "p")
                paragraphs_text = [p.text for p in paragraphs if len(p.text) > 100]  # Only longer paragraphs
                if paragraphs_text:
                    content = "\n\n".join(paragraphs_text)

            # Extract the main image
            image_url = None

            # Try to find meta tags for og:image
            og_image = soup.find('meta', property='og:image')
            if og_image:
                image_url = og_image.get('content')

            # If no og:image, try various image containers
            if not image_url:
                image_selectors = [
                    "article img",
                    ".featured-image img",
                    ".article-image img",
                    ".post-thumbnail img",
                    "figure img"
                ]

                for selector in image_selectors:
                    images = driver.find_elements(By.CSS_SELECTOR, selector)
                    for img in images:
                        src = img.get_attribute("src")
                        if src and (src.startswith("http") or src.startswith("/")):
                            # Check image size to ensure it's not a tiny icon
                            width = img.get_attribute("width")
                            height = img.get_attribute("height")
                            try:
                                if width and height and int(width) > 200 and int(height) > 150:
                                    image_url = src
                                    break
                            except ValueError:
                                pass

                    if image_url:
                        break

            # Clean up content
            if content:
                # Remove excessive whitespace
                content = re.sub(r'\s+', ' ', content)
                content = content.strip()

            # Extract the website domain
            domain = urlparse(url).netloc

            return {
                "article_content": content,
                "image_url": image_url,
                "domain": domain
            }

        except TimeoutException as e:
            logger.error(f"Timeout loading page: {str(e)}")
            return {"article_content": "", "image_url": None, "domain": urlparse(url).netloc}
        except Exception as e:
            logger.error(f"Error extracting article content: {str(e)}")
            return {"article_content": "", "image_url": None, "domain": urlparse(url).netloc}


def fetch_news_with_content(
        query: str,
        language: str = "en",
        country: str = "US",
        max_results: int = 5,
        include_content: bool = True
) -> List[Dict[str, Any]]:
    """
    Fetch news articles from Google News and optionally extract content and images.

    Args:
        query (str): Search query
        language (str): Language code (e.g., 'en', 'es')
        country (str): Country code (e.g., 'US', 'UK')
        max_results (int): Maximum number of results to return
        include_content (bool): Whether to fetch full article content and images

    Returns:
        List[Dict[str, Any]]: List of news articles with content and metadata
    """
    try:
        # First, get articles from Google News RSS
        articles = fetch_google_news(query, language, country, max_results)

        if not articles:
            return []

        # If content extraction is requested, fetch content for each article
        if include_content:
            for article in articles:
                try:
                    # Extract content and image for the article
                    extracted_data = extract_article_content(article["url"])

                    # Update article with extracted data
                    article["article_content"] = extracted_data["article_content"]
                    article["image_url"] = extracted_data["image_url"]
                    article["domain"] = extracted_data["domain"]

                    # Wait briefly to avoid overloading websites
                    time.sleep(1)

                except Exception as e:
                    logger.error(f"Error processing article {article['url']}: {str(e)}")
                    # Keep the article but without content
                    article["article_content"] = ""
                    article["image_url"] = None
                    article["domain"] = urlparse(article["url"]).netloc

        return articles

    except Exception as e:
        logger.error(f"Error in fetch_news_with_content: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching news content: {str(e)}")