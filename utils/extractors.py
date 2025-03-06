import re
from typing import Optional, List
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
import time

from config import logger
from models.group import Reaction, ReactionType


def extract_price(text: str) -> Optional[float]:
    """
    Extract price from text with handling of different currency formats.

    Args:
        text (str): The text to extract the price from

    Returns:
        Optional[float]: The extracted price as a float, or None if no price is found
    """
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


def extract_posted_time(text: str) -> Optional[str]:
    """
    Extract posting time information from listing text.

    Args:
        text (str): The text to extract the posting time from

    Returns:
        Optional[str]: The extracted posting time as a string, or None if no time is found
    """
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


def extract_image_url(item_element) -> Optional[str]:
    """
    Extract image URL from product element.

    Args:
        item_element: BeautifulSoup element representing a product

    Returns:
        Optional[str]: The extracted image URL, or None if no URL is found
    """
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


def extract_marketplace_url(item_element) -> Optional[str]:
    """
    Extract product URL with pattern matching.

    Args:
        item_element: BeautifulSoup element representing a product

    Returns:
        Optional[str]: The extracted product URL, or None if no URL is found
    """
    try:
        # First try to find direct marketplace links
        link_elements = item_element.find_all('a', href=lambda h: h and '/marketplace/item/' in h)

        if link_elements:
            href = link_elements[0].get('href')
            if href:
                # Ensure it's a full URL
                if href.startswith('http'):
                    return href
                else:
                    return f"https://www.facebook.com{href}"

        # Try to find any link that might contain marketplace references
        all_links = item_element.find_all('a', href=True)
        for link in all_links:
            href = link.get('href')
            if href and ('/marketplace/' in href or '/item/' in href):
                # Ensure it's a full URL
                if href.startswith('http'):
                    return href
                else:
                    return f"https://www.facebook.com{href}"

        # If no direct links found, look for data attributes that might contain URLs
        elements_with_data = item_element.find_all(attrs={"data-href": True})
        for element in elements_with_data:
            data_href = element.get('data-href')
            if data_href and ('/marketplace/' in data_href):
                return f"https://www.facebook.com{data_href}"

    except Exception as e:
        logger.warning(f"Failed to extract product URL: {str(e)}")

    return None


def extract_author(element):
    """
    Extract author information from a post or comment element.

    Args:
        element: Selenium WebElement representing a post or comment

    Returns:
        str: The author name, or "Unknown" if no author is found
    """
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
    except Exception as e:
        logger.warning(f"Error extracting author: {str(e)}")

    return author


def extract_reactions(element, driver) -> List[Reaction]:
    """
    Extract reaction counts from a post or comment element.

    Args:
        element: Selenium WebElement representing a post or comment
        driver: The WebDriver instance

    Returns:
        List[Reaction]: List of Reaction objects with type and count
    """
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
                except Exception as e:
                    logger.warning(f"Failed to extract reaction count: {str(e)}")

    except Exception as e:
        logger.warning(f"Failed to extract reactions: {str(e)}")

    return reactions


def extract_comment_text(comment_element, author_name):
    """
    Extract comment text with better author filtering.

    Args:
        comment_element: Selenium WebElement representing a comment
        author_name: The name of the comment author to filter out

    Returns:
        str: The extracted comment text
    """
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