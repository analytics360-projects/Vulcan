from typing import List, Optional, Dict, Any
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from collections import Counter
import re
import time
import requests
from urllib.parse import quote_plus
from fastapi import HTTPException

from config import settings, logger
from modules.groups.models import Post, Comment, Reaction, ReactionType, GroupAnalysis, GroupCategoryResult, GroupCategorySearchResponse
from shared.webdriver import get_driver, handle_facebook_dialogs, wait_for_element

DEFAULT_MAX_POSTS = settings.max_posts
DEFAULT_MAX_COMMENTS = settings.max_comments
DEFAULT_MAX_SCROLL_ATTEMPTS = settings.max_scroll_attempts
DEFAULT_SCROLL_DELAY = settings.scroll_delay


def is_comment_url(url: str) -> bool:
    """
    Determine if a URL is for a comment based on its structure.

    Args:
        url (str): The URL to check

    Returns:
        bool: True if the URL is for a comment, False otherwise
    """
    return "comment_id=" in url or "/comments/" in url


def extract_author(element) -> str:
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

        # Approach 4: Try to find the first heading element
        if author == "Unknown":
            heading_elements = element.find_elements(By.CSS_SELECTOR, "h3, h4, h5, h6")
            for heading in heading_elements:
                if heading.text and len(heading.text) > 1:
                    author = heading.text
                    break
    except Exception as e:
        logger.warning(f"Error extracting author: {str(e)}")

    return author


def extract_reactions(element, driver) -> List[Reaction]:
    """
    Enhanced extraction of reaction counts from a post or comment element.

    Args:
        element: Selenium WebElement representing a post or comment
        driver: The WebDriver instance

    Returns:
        List[Reaction]: List of Reaction objects with type and count
    """
    reactions = []

    try:
        # Find reaction elements - expanded selector set for 2025 Facebook DOM
        reaction_selectors = [
            # Standard reaction containers
            "span[aria-label*='reaccion']",
            "span[aria-label*='reaction']",
            "div[aria-label*='reaccion']",
            "div[aria-label*='reaction']",
            # New Facebook reaction containers
            "div.x78zum5.x1n2onr6",  # Common reaction container class
            "span.x1e558r4",  # Often contains reaction counts
            # Specific reaction wrappers
            "div.xrbpyxo.x1c4vz4f",
            "div.x1i10hfl.xdl72j9"
        ]

        # First try to find the reaction count as direct text
        reaction_text_elements = []
        for selector in reaction_selectors:
            elements = element.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                reaction_text_elements.extend(elements)

        if reaction_text_elements:
            for reaction_element in reaction_text_elements:
                try:
                    reaction_text = reaction_element.text.strip()
                    # Look for numbers in the text
                    count_match = re.search(r'(\d+(?:,\d+)*)', reaction_text)
                    if count_match:
                        count_str = count_match.group(1).replace(',', '')
                        count = int(count_str)
                        # Default to LIKE if we can't determine type
                        reactions.append(Reaction(type=ReactionType.LIKE, count=count))
                except Exception as e:
                    logger.warning(f"Error parsing reaction text: {str(e)}")

        # If no reactions found yet, try the hover method
        if not reactions:
            hover_selectors = [
                "div.x1i10hfl.x1qjc9v5",  # Common class for reaction areas
                "span.x4k7w5x.x1h91t0o",  # Often contains like counts
                "span[data-testid='UFI2ReactionsCount']",
                "div[data-testid='UFI2ReactionsCount/root']",
                "div.xod5an3"  # Another reaction container class
            ]

            hover_elements = []
            for selector in hover_selectors:
                elements = element.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    hover_elements.extend(elements)

            if hover_elements:
                # Use the first hover element we found
                try:
                    ActionChains(driver).move_to_element(hover_elements[0]).perform()
                    time.sleep(1)

                    # Try to find the tooltip with reaction details
                    tooltips = driver.find_elements(By.CSS_SELECTOR, "div[role='tooltip'], div.x1iy3rx6")
                    if tooltips:
                        tooltip_text = tooltips[0].text

                        # Look for reaction counts in the tooltip
                        reaction_patterns = {
                            ReactionType.LIKE: r'(\d+(?:,\d+)*)\s*(?:Me gusta|Like)',
                            ReactionType.LOVE: r'(\d+(?:,\d+)*)\s*(?:Me encanta|Love)',
                            ReactionType.HAHA: r'(\d+(?:,\d+)*)\s*(?:Me divierte|Haha)',
                            ReactionType.WOW: r'(\d+(?:,\d+)*)\s*(?:Me asombra|Wow)',
                            ReactionType.SAD: r'(\d+(?:,\d+)*)\s*(?:Me entristece|Sad)',
                            ReactionType.ANGRY: r'(\d+(?:,\d+)*)\s*(?:Me enoja|Angry)',
                            ReactionType.CARE: r'(\d+(?:,\d+)*)\s*(?:Me importa|Care)'
                        }

                        for reaction_type, pattern in reaction_patterns.items():
                            match = re.search(pattern, tooltip_text, re.IGNORECASE)
                            if match:
                                count_str = match.group(1).replace(',', '')
                                count = int(count_str)
                                reactions.append(Reaction(type=reaction_type, count=count))
                except Exception as e:
                    logger.warning(f"Error extracting reaction tooltip: {str(e)}")

        # If still no reactions found but we see text that hints at reactions
        if not reactions:
            # Try direct text extraction from anywhere in the post that might have like counts
            like_indicators = element.find_elements(By.XPATH,
                                                    "//*[contains(text(), 'Like') or contains(text(), 'Me gusta') or contains(text(), '👍')]")

            if like_indicators:
                for indicator in like_indicators:
                    try:
                        parent = indicator.find_element(By.XPATH, "./..")
                        parent_text = parent.text
                        count_match = re.search(r'(\d+(?:,\d+)*)', parent_text)
                        if count_match:
                            count_str = count_match.group(1).replace(',', '')
                            count = int(count_str)
                            reactions.append(Reaction(type=ReactionType.LIKE, count=count))
                            break
                    except:
                        continue

        # Final fallback: check for reaction images and estimate from those
        if not reactions:
            reaction_images = element.find_elements(By.CSS_SELECTOR, "img[src*='reaction'], img[src*='emoji']")
            if reaction_images:
                # If we find reaction images but no counts, assume at least 1 like
                reactions.append(Reaction(type=ReactionType.LIKE, count=len(reaction_images)))

    except Exception as e:
        logger.warning(f"Failed to extract reactions: {str(e)}")

    # Deduplicate by reaction type (keep highest count)
    reaction_dict = {}
    for reaction in reactions:
        if reaction.type not in reaction_dict or reaction.count > reaction_dict[reaction.type].count:
            reaction_dict[reaction.type] = reaction

    # If still no reactions but clearly interactive content, add placeholder
    if not reaction_dict and element.find_elements(By.CSS_SELECTOR, "div[role='button']"):
        reaction_dict[ReactionType.LIKE] = Reaction(type=ReactionType.LIKE, count=0)

    return list(reaction_dict.values())


def extract_comments(post_element, driver, max_comments: int = DEFAULT_MAX_COMMENTS) -> List[Comment]:
    """
    Enhanced extraction of comments from a post element.

    Args:
        post_element: Selenium WebElement representing a post
        driver: The WebDriver instance
        max_comments: Maximum number of comments to extract

    Returns:
        List[Comment]: List of Comment objects
    """
    comments = []

    try:
        # Try to expand comments first
        expand_selectors = [
            # Text-based selectors
            "//span[contains(text(), 'Ver más comentarios') or contains(text(), 'View more comments')]",
            "//span[contains(text(), 'Ver comentarios') or contains(text(), 'View comments')]",
            "//span[contains(text(), 'comentarios') or contains(text(), 'comments')]",
            # Button-based selectors
            "//div[@role='button' and contains(@aria-label, 'comment')]"
        ]

        # Try each expansion approach
        for selector in expand_selectors:
            try:
                buttons = post_element.find_elements(By.XPATH, selector)
                for button in buttons[:3]:  # Limit to avoid excessive clicking
                    try:
                        driver.execute_script("arguments[0].click();", button)
                        time.sleep(1.5)
                    except:
                        pass
            except:
                pass

        # Expanded comment selector list for 2025 Facebook DOM
        comment_selectors = [
            # Standard comment selectors
            "div[aria-label='Comentario']",
            "div[aria-label='Comment']",
            "div[data-testid='UFI2Comment']",
            # New Facebook comment containers
            "div.x1n2onr6.x1iorvi4.x4uap5.x18d9i69",  # Common pattern in 2024/2025
            "div.x78zum5.x1iyjqo2.xs83m0k.xeuugli",  # Alternative pattern
            "ul.x78zum5 > li.x1n2onr6",  # List-based comments
            "div[role='article'][tabindex='-1']",  # Role-based comment container
            "div.xdj266r.x11i5rnm.xat24cr.x1mh8g0r"  # Deep nested comments
        ]

        # Try each comment selector
        comment_elements = []
        for selector in comment_selectors:
            elements = post_element.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                comment_elements.extend(elements)
                # Don't break, collect all potential comments

        # Remove duplicates by comparing element IDs
        unique_elements = []
        seen_ids = set()
        for element in comment_elements:
            element_id = element.id
            if element_id not in seen_ids:
                seen_ids.add(element_id)
                unique_elements.append(element)

        comment_elements = unique_elements[:max_comments]

        # Process each potential comment
        for comment_element in comment_elements:
            try:
                # Extract comment URL
                comment_url = None
                try:
                    permalink_elements = comment_element.find_elements(By.CSS_SELECTOR,
                                                                       "a[href*='comment_id'], a[href*='permalink'], a[href*='reply_comment_id']")
                    if permalink_elements:
                        comment_url = permalink_elements[0].get_attribute("href")
                except:
                    pass

                # Extract author with enhanced approach
                author = extract_author(comment_element)

                # Extract text with enhanced approach
                comment_text = extract_comment_text(comment_element, author)

                # Skip if we couldn't extract meaningful text
                if not comment_text or len(comment_text.strip()) < 3:
                    continue

                # Extract timestamp with multiple approaches
                timestamp = None
                timestamp_selectors = [
                    "a[role='link'] span:not([data-visualcompletion])",  # Standard timestamp
                    "span.x4k7w5x.x1h91t0o",  # New timestamp class
                    "span.x1e56ztr",  # Another timestamp container
                    "a.x1i10hfl span"  # Link-based timestamp
                ]

                for selector in timestamp_selectors:
                    elements = comment_element.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        text = element.text.strip()
                        if text and any(time_word in text.lower() for time_word in
                                        ['min', 'hr', 'h', 'seg', 'hour', 'day', 'hora', 'día', 's', 'd', 'm']):
                            timestamp = text
                            break
                    if timestamp:
                        break

                # Extract reactions with enhanced function
                reactions = extract_reactions(comment_element, driver)

                # Get likes count
                likes_count = sum(reaction.count for reaction in reactions)

                # Create comment object
                comment = Comment(
                    text=comment_text,
                    author=author,
                    timestamp=timestamp,
                    reactions=reactions,
                    likes_count=likes_count,
                    url=comment_url,
                    replies=[]
                )

                # Extract replies with similar enhanced approach
                try:
                    # First try to expand replies
                    reply_buttons = comment_element.find_elements(By.XPATH,
                                                                  ".//span[contains(text(), 'Ver respuestas') or contains(text(), 'View replies') or " +
                                                                  "contains(text(), 'respuesta') or contains(text(), 'reply')]")

                    for button in reply_buttons[:2]:  # Limit to 2 buttons
                        try:
                            driver.execute_script("arguments[0].click();", button)
                            time.sleep(1.5)
                        except:
                            pass

                    # Multiple approaches to find replies
                    reply_selectors = [
                        "div.xdj266r.x11i5rnm div[role='article']",  # Nested article replies
                        "div.x1n2onr6.x1iorvi4 div[role='article']",  # Another nested structure
                        "ul.x78zum5 li.x1n2onr6:not(:first-child)",
                        # List-based replies (skip first as it's the comment)
                        "div[aria-label='Comment reply']"  # Directly labeled replies
                    ]

                    reply_elements = []
                    for selector in reply_selectors:
                        elements = comment_element.find_elements(By.CSS_SELECTOR, selector)
                        if elements:
                            reply_elements.extend(elements)

                    # Process up to 10 replies, prioritizing those with real content
                    valid_replies = []
                    for reply_element in reply_elements[:20]:  # Look at more to find valid ones
                        reply_author = extract_author(reply_element)
                        reply_text = extract_comment_text(reply_element, reply_author)

                        # Only include replies with meaningful text
                        if reply_text and len(reply_text.strip()) >= 3:
                            valid_replies.append((reply_element, reply_author, reply_text))
                            # Stop if we have 10 valid replies
                            if len(valid_replies) >= 10:
                                break

                    # Now process the valid replies in detail
                    for reply_element, reply_author, reply_text in valid_replies:
                        # Extract URL
                        reply_url = None
                        try:
                            reply_permalink = reply_element.find_elements(By.CSS_SELECTOR,
                                                                          "a[href*='comment_id'], a[href*='reply_comment_id']")
                            if reply_permalink:
                                reply_url = reply_permalink[0].get_attribute("href")
                        except:
                            pass

                        # Extract reactions
                        reply_reactions = extract_reactions(reply_element, driver)
                        reply_likes = sum(reaction.count for reaction in reply_reactions)

                        # Extract timestamp
                        reply_timestamp = None
                        for selector in timestamp_selectors:
                            elements = reply_element.find_elements(By.CSS_SELECTOR, selector)
                            for element in elements:
                                text = element.text.strip()
                                if text and any(time_word in text.lower() for time_word in
                                                ['min', 'hr', 'h', 'seg', 'hour', 'day', 'hora', 'día', 's', 'd', 'm']):
                                    reply_timestamp = text
                                    break
                            if reply_timestamp:
                                break

                        reply = Comment(
                            text=reply_text,
                            author=reply_author,
                            timestamp=reply_timestamp,
                            likes_count=reply_likes,
                            reactions=reply_reactions,
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


def extract_author(element) -> str:
    """
    Enhanced extraction of author information from a post or comment element.

    Args:
        element: Selenium WebElement representing a post or comment

    Returns:
        str: The author name, or "Unknown" if no author is found
    """
    author = "Unknown"
    try:
        # Enhanced selector list for 2025 Facebook DOM
        author_selectors = [
            # Standard selectors
            "h3[dir='auto'] span",  # Main post author format
            "h4 span[dir='auto']",  # Secondary header format
            "a[role='link'] span.x1lliihq",  # Profile link format
            # New class-based selectors
            "span.x193iq5w.xeuugli.x13faqbe.x1vvkbs",  # Common author class pattern
            "span.x1lliihq.x6ikm8r.x10wlt62",  # Alternative author class pattern
            "h2.x1heor9g span",  # Header-based author format
            "a[aria-hidden='false'] span",  # Accessible author link
            "span.xt0psk2",  # Simple author class
            # Attribute-based selectors
            "span[dir='auto'][aria-hidden='false']"  # Direct attributes
        ]

        # Try each selector strategy
        for selector in author_selectors:
            elements = element.find_elements(By.CSS_SELECTOR, selector)
            for el in elements:
                text = el.text.strip()
                if text and len(text) > 1:
                    # Skip if it looks like a timestamp or common UI text
                    skip_terms = ['hr', 'min', 'sec', 'day', 'week', 'month', 'año', 'hora', 'día',
                                  'ver', 'view', 'edit', 'editar', 'translated', 'traducido']

                    if not any(term in text.lower() for term in skip_terms):
                        author = text
                        return author  # Return immediately if found

        # If not found, try the link approach with better filtering
        if author == "Unknown":
            link_elements = element.find_elements(By.CSS_SELECTOR, "a[role='link']")
            for link in link_elements:
                # Check if this looks like a profile link
                href = link.get_attribute("href")
                if href and ("facebook.com/" in href or "fb.com/" in href) and not any(
                        x in href for x in ["photo", "video", "hashtag"]):
                    link_text = link.text.strip()
                    # Skip if empty or looks like a timestamp
                    if not link_text or len(link_text) < 2:
                        continue
                    if any(time_word in link_text.lower() for time_word in
                           ['min', 'hr', 'h', 'seg', 'hour', 'día', 'day']):
                        continue
                    author = link_text
                    break

        # Final approach: search up the DOM for role="article" and then look for links
        if author == "Unknown":
            try:
                article = element
                try_count = 0
                # Try to find parent article if this isn't one
                while article.get_attribute("role") != "article" and try_count < 5:
                    article = article.find_element(By.XPATH, "./..")
                    try_count += 1

                if article.get_attribute("role") == "article":
                    # Now search for the first good link in this article that looks like an author
                    profile_links = article.find_elements(By.CSS_SELECTOR, "a[role='link']")
                    for link in profile_links:
                        href = link.get_attribute("href")
                        if href and ("facebook.com/" in href or "fb.com/" in href) and not any(
                                x in href for x in ["photo", "video", "hashtag"]):
                            text = link.text.strip()
                            if text and len(text) > 1 and not any(time_word in text.lower() for time_word in
                                                                  ['min', 'hr', 'h', 'seg', 'hour', 'day']):
                                author = text
                                break
            except:
                pass

    except Exception as e:
        logger.warning(f"Error extracting author: {str(e)}")

    return author


def extract_comment_text(comment_element, author_name: str) -> str:
    """
    Enhanced extraction of comment text with improved author filtering.

    Args:
        comment_element: Selenium WebElement representing a comment
        author_name: The name of the comment author to filter out

    Returns:
        str: The extracted comment text
    """
    comment_text = ""
    try:
        # First try dedicated content elements with modern selectors
        content_selectors = [
            "div[data-ad-comet-preview='message']",  # Standard preview container
            "div.xdj266r.x11i5rnm.xat24cr.x1mh8g0r",  # Common text container
            "span[dir='auto'][data-ad-preview='message']",  # Span-based preview
            "div.x1mh8g0r.x1x2crx6",  # Another content class pattern
            "div[dir='auto'] span.x193iq5w"  # Nested content structure
        ]

        for selector in content_selectors:
            content_elements = comment_element.find_elements(By.CSS_SELECTOR, selector)
            if content_elements:
                for element in content_elements:
                    text = element.text.strip()
                    if len(text) > 3:  # Require at least some content
                        comment_text = text
                        break

            if comment_text:
                break

        # If not found, try the span approach with improved filtering
        if not comment_text:
            # Get all author names to filter out
            author_names = [author_name] if author_name and author_name != "Unknown" else []

            # Add any other authors from links
            author_elements = comment_element.find_elements(By.CSS_SELECTOR, "a[role='link']")
            for a in author_elements:
                if a.text and len(a.text.strip()) > 1:
                    author_names.append(a.text.strip())

            # Add common Facebook UI text to filter
            filter_phrases = author_names + [
                "Like", "Reply", "Me gusta", "Responder", "See Translation",
                "Ver traducción", "Edit", "Editar", "Share", "Compartir"
            ]

            # Get all spans with dir="auto" attribute (typical for comment text)
            text_elements = comment_element.find_elements(By.CSS_SELECTOR, "span[dir='auto']")
            candidate_texts = []

            for element in text_elements:
                text = element.text.strip()

                # Skip empty or very short text
                if not text or len(text) < 3:
                    continue

                # Skip if text is just a filtered phrase
                if any(filter_text.lower() == text.lower() for filter_text in filter_phrases):
                    continue

                # Skip if text closely resembles author name
                author_match = False
                for author in author_names:
                    # If text is very close to author name in length, skip it
                    if author.lower() in text.lower() and len(text) <= len(author) + 10:
                        author_match = True
                        break

                if author_match:
                    continue

                # Skip if text is a timestamp
                if any(time_word in text.lower() for time_word in
                       ['min', 'hr', 'h', 'seg', 'hour', 'day', 'hora', 'día', 'month']):
                    if len(text) < 15:  # Only skip short timestamp texts
                        continue

                candidate_texts.append(text)

            # Also try div elements with dir="auto"
            div_elements = comment_element.find_elements(By.CSS_SELECTOR, "div[dir='auto']")
            for element in div_elements:
                text = element.text.strip()
                if text and len(text) > 5:  # Require slightly longer text for divs
                    # Apply same filtering
                    if not any(filter_text.lower() in text.lower() for filter_text in filter_phrases):
                        candidate_texts.append(text)

            # Sort by length (descending) to prefer longer texts
            candidate_texts.sort(key=len, reverse=True)

            # Take the longest text as the comment content
            if candidate_texts:
                comment_text = candidate_texts[0]

        # Fallback: Try to get any content by analyzing the complete text
        if not comment_text:
            fallback_content = comment_element.text

            # Remove common button text and UI elements
            for phrase in ["Like", "Reply", "Me gusta", "Responder", "Edit", "Editar",
                           "Share", "Compartir", "See Translation", "Ver traducción"]:
                fallback_content = re.sub(r'\b' + re.escape(phrase) + r'\b', '', fallback_content)

            # Remove author name from the text if possible
            if author_name and author_name != "Unknown":
                fallback_content = fallback_content.replace(author_name, "").strip()

            # Remove timestamps
            fallback_content = re.sub(r'\b\d+\s*(?:min|hr|h|seg|hour|day|hora|día|d|m|s)\b', '', fallback_content)

            # Clean up whitespace
            fallback_content = re.sub(r'\s+', ' ', fallback_content).strip()

            if len(fallback_content) > 5:
                comment_text = fallback_content

    except Exception as e:
        logger.warning(f"Error extracting comment text: {str(e)}")

    return comment_text


def extract_comment_text(comment_element, author_name: str) -> str:
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

        # Fallback: Try to get any content
        if not comment_text:
            fallback_content = comment_element.text
            # Remove author name from the text if possible
            if author_name and author_name != "Unknown" and author_name in fallback_content:
                fallback_content = fallback_content.replace(author_name, "").strip()
            if len(fallback_content) > 5:
                comment_text = fallback_content

    except Exception as e:
        logger.warning(f"Error extracting comment text: {str(e)}")

    return comment_text


def extract_comments(post_element, driver, max_comments: int = DEFAULT_MAX_COMMENTS) -> List[Comment]:
    """
    Extract comments from a post element.

    Args:
        post_element: Selenium WebElement representing a post
        driver: The WebDriver instance
        max_comments: Maximum number of comments to extract

    Returns:
        List[Comment]: List of Comment objects
    """
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
            elements = post_element.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                comment_elements = elements
                break

        for comment_element in comment_elements[:max_comments]:
            try:
                # Extract comment URL
                comment_url = None
                try:
                    permalink_elements = comment_element.find_elements(By.CSS_SELECTOR, "a[href*='comment_id']")
                    if permalink_elements:
                        comment_url = permalink_elements[0].get_attribute("href")
                except:
                    pass

                # Extract author
                author = extract_author(comment_element)

                # Extract text, filtering out author name
                comment_text = extract_comment_text(comment_element, author)

                if not comment_text:
                    continue

                # Extract timestamp
                timestamp_elements = comment_element.find_elements(By.CSS_SELECTOR, "a[role='link'] span")
                timestamp = None
                for timestamp_element in timestamp_elements:
                    text = timestamp_element.text
                    if text and any(time_word in text.lower() for time_word in
                                    ['min', 'hr', 'h', 'seg', 'hour', 'day', 'hora', 'día']):
                        timestamp = text
                        break

                # Extract reactions
                reactions = extract_reactions(comment_element, driver)

                # Get likes count
                likes_count = sum(reaction.count for reaction in reactions)

                # Create comment object
                comment = Comment(
                    text=comment_text,
                    author=author,
                    timestamp=timestamp,
                    reactions=reactions,
                    likes_count=likes_count,
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
                        if not reply_elements:
                            # Try alternative selectors
                            reply_elements = comment_element.find_elements(By.CSS_SELECTOR,
                                                                           "div[aria-label='Comment reply'] div[role='article']")

                        for reply_element in reply_elements[:10]:  # Limit to 10 replies
                            # Extract reply author first
                            reply_url = None
                            try:
                                reply_permalink = reply_element.find_elements(By.CSS_SELECTOR, "a[href*='comment_id']")
                                if reply_permalink:
                                    reply_url = reply_permalink[0].get_attribute("href")
                            except:
                                pass

                            reply_author = extract_author(reply_element)

                            # Then extract reply text, filtering out author
                            reply_text = extract_comment_text(reply_element, reply_author)

                            if not reply_text:
                                continue

                            # Extract reactions for the reply
                            reply_reactions = extract_reactions(reply_element, driver)
                            reply_likes = sum(reaction.count for reaction in reply_reactions)

                            # Extract timestamp for reply
                            reply_timestamp = None
                            reply_timestamp_elements = reply_element.find_elements(By.CSS_SELECTOR,
                                                                                   "a[role='link'] span")
                            for ts_element in reply_timestamp_elements:
                                text = ts_element.text
                                if text and any(time_word in text.lower() for time_word in
                                                ['min', 'hr', 'h', 'seg', 'hour', 'day', 'hora', 'día']):
                                    reply_timestamp = text
                                    break

                            reply = Comment(
                                text=reply_text,
                                author=reply_author,
                                timestamp=reply_timestamp,
                                likes_count=reply_likes,
                                reactions=reply_reactions,
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


def extract_post_data(post_element, driver) -> Optional[Post]:
    """
    Enhanced extraction of data from a post element with improved reaction counting.

    Args:
        post_element: Selenium WebElement representing a post
        driver: The WebDriver instance

    Returns:
        Optional[Post]: A Post object, or None if the post cannot be extracted
    """
    try:
        # Extract post ID from permalink with expanded selectors
        post_id = None
        post_url = None

        # Multiple approaches to find post URL
        url_selectors = [
            "a[href*='/posts/']",
            "a[href*='permalink']",
            "a[href*='groups/'][href*='/posts/']",
            "a[href*='groups/'][href*='/permalink/']",
            "a[aria-label*='comment']",
            "div[role='article'] a[href*='photo.php']"
        ]

        for selector in url_selectors:
            permalink_elements = post_element.find_elements(By.CSS_SELECTOR, selector)
            if permalink_elements:
                for element in permalink_elements:
                    href = element.get_attribute("href")
                    if not href:
                        continue

                    # Try different extraction patterns
                    post_id_patterns = [
                        r'/posts/(\d+)',
                        r'story_fbid=(\d+)',
                        r'groups/[^/]+/permalink/(\d+)',
                        r'groups/[^/]+/posts/(\d+)',
                        r'comment_id=(\d+)',
                        r'photo.php\?fbid=(\d+)'
                    ]

                    for pattern in post_id_patterns:
                        match = re.search(pattern, href)
                        if match:
                            post_id = match.group(1)
                            post_url = href
                            break

                    if post_id:
                        break

            if post_id:
                break

        # If still not found, try data-ft attributes for post IDs
        if not post_id:
            try:
                data_ft = post_element.get_attribute("data-ft")
                if data_ft:
                    data_json = json.loads(data_ft)
                    if 'top_level_post_id' in data_json:
                        post_id = data_json['top_level_post_id']
                    elif 'mf_story_key' in data_json:
                        post_id = data_json['mf_story_key']
            except:
                pass

        # Last resort: generate a pseudo ID based on content
        if not post_id:
            try:
                post_content = post_element.text[:100]  # Take first 100 chars
                import hashlib
                post_id = hashlib.md5(post_content.encode()).hexdigest()[:16]
                logger.warning(f"Generated pseudo ID for post: {post_id}")
            except:
                logger.warning("Could not extract or generate post ID, skipping post")
                return None

        # Extract post author with enhanced function
        author = extract_author(post_element)

        # Extract post content with enhanced approach
        content = ""
        try:
            # Updated content selectors for 2025 Facebook DOM
            content_selectors = [
                "div[data-ad-comet-preview='message']",
                "div[data-ad-preview='message']",
                "div.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.xvvkbs",  # New class pattern from example
                "div.x78zum5.xdt5ytf.xz62fqu.x16ldp7u div.xu06os2 span",  # Content span pattern
                "div.x1iorvi4 span.x193iq5w",  # Another content pattern
                "div.x1l90r2v.x1iorvi4.x1ye3gou.xn6708d",  # Direct content div
                "div[data-visualcompletion='ignore-dynamic']"  # Fallback
            ]

            for selector in content_selectors:
                content_containers = post_element.find_elements(By.CSS_SELECTOR, selector)
                for container in content_containers:
                    text = container.text.strip()
                    if text and len(text) > 10:  # Require meaningful content
                        content = text
                        break

                if content:
                    break
        except Exception as e:
            logger.warning(f"Error extracting post content: {str(e)}")

        # Extract timestamp with expanded selectors
        timestamp = None
        timestamp_selectors = [
            # Standard timestamp selectors
            "span.timestampContent",
            "span.fcg a",
            "a span[aria-label]",
            # New timestamp selectors based on the example
            "span.x4k7w5x.x1h91t0o.x1h9r5lt",
            "a[role='link'] span.x1e56ztr",
            "span[data-sigil='timestamp']"
        ]

        # Try each selector
        for selector in timestamp_selectors:
            elements = post_element.find_elements(By.CSS_SELECTOR, selector)
            for el in elements:
                text = el.text.strip()
                if text and any(time_word in text.lower() for time_word in
                                ['min', 'hr', 'h', 'seg', 'hour', 'day', 'hora', 'día', 'm']):
                    timestamp = text
                    break

            if timestamp:
                break

        # Extract image if any
        image_url = None
        try:
            # Try multiple selectors for images
            img_selectors = [
                "img.x1ey2m1c",  # From the example
                "img[src*='scontent']",
                "img[data-visualcompletion='media-vc-image']",
                "div[role='button'] img"
            ]

            for selector in img_selectors:
                img_elements = post_element.find_elements(By.CSS_SELECTOR, selector)
                if img_elements:
                    for img in img_elements:
                        src = img.get_attribute("src")
                        if src and len(src) > 20 and ("scontent" in src or "fbcdn" in src):
                            image_url = src
                            break

                if image_url:
                    break
        except Exception as e:
            logger.warning(f"Error extracting image URL: {str(e)}")

        # Get total reactions count using the new function
        likes_count = extract_reactions_count(post_element, driver)

        # If we have a reaction count but no reaction objects, create a default one
        reactions = []
        if likes_count > 0:
            reactions.append(Reaction(type=ReactionType.LIKE, count=likes_count))

        # Extract comments with enhanced function
        comments = extract_comments(post_element, driver)
        comments_count = len(comments)

        # If no comments found but there's evidence of comments, try to extract the count
        if comments_count == 0:
            try:
                comment_count_selectors = [
                    "span.x193iq5w[dir='auto']",  # From the example
                    "span[data-testid='UFI2CommentCount']",
                    "a[href*='comments'] span"
                ]

                for selector in comment_count_selectors:
                    elements = post_element.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        text = element.text.strip()
                        if ("comment" in text.lower() or "comentario" in text.lower()) and any(
                                c.isdigit() for c in text):
                            count_match = re.search(r'(\d+(?:,\d+)*)', text)
                            if count_match:
                                count_str = count_match.group(1).replace(',', '')
                                comments_count = int(count_str)
                                break

                    if comments_count > 0:
                        break
            except Exception as e:
                logger.warning(f"Error extracting comment count: {str(e)}")

        # Create post object
        # G2 — Classify sentiment using keyword-based heuristics
        _sentimiento = None
        _sentimiento_score = None
        if content and len(content.strip()) > 2:
            try:
                from modules.sentiment.service import classify_keyword
                _item = classify_keyword(content)
                _sentimiento = _item.sentimiento
                _sentimiento_score = _item.score
            except Exception:
                pass

        post = Post(
            post_id=post_id,
            author=author,
            content=content,
            timestamp=timestamp,
            reactions=reactions,
            comments=comments,
            url=post_url or "",  # Ensure URL is not None
            image_url=image_url,
            likes_count=likes_count,
            comments_count=comments_count,
            authorized=False,
            sentimiento=_sentimiento,
            sentimiento_score=_sentimiento_score,
        )

        return post

    except Exception as e:
        logger.warning(f"Failed to extract post data: {str(e)}")
        return None


def extract_comments_modern(post_element, driver, max_comments: int = DEFAULT_MAX_COMMENTS) -> List[Comment]:
    """
    Extract comments from a post element using patterns from the 2025 Facebook example.

    Args:
        post_element: Selenium WebElement representing a post
        driver: The WebDriver instance
        max_comments: Maximum number of comments to extract

    Returns:
        List[Comment]: List of Comment objects
    """
    comments = []

    try:
        # Try to find comment blocks based on the HTML example structure
        comment_selectors = [
            "div[role='article'][tabindex='-1']",  # Main comment container
            "div.x1n2onr6.x1ye3gou.x1iorvi4.x78zum5.x1q0g3np.x1a2a7pz",  # More specific selector
            "div.html-div.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.xexx8yu.x4uap5.x18d9i69.xkhd6sd div.x1n2onr6"
            # Another pattern
        ]

        comment_elements = []

        # Try each selector
        for selector in comment_selectors:
            elements = post_element.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                comment_elements.extend(elements)

        # Remove duplicates
        unique_ids = set()
        unique_comments = []

        for element in comment_elements:
            element_id = element.id
            if element_id not in unique_ids:
                unique_ids.add(element_id)
                unique_comments.append(element)

        comment_elements = unique_comments[:max_comments]

        # Now extract data from each comment element
        for comment_element in comment_elements:
            try:
                # Extract author using modern structure
                author = "Unknown"

                # Based on the example HTML
                author_selectors = [
                    "span.x193iq5w[dir='auto']",  # Main comment author
                    "div.x1n2onr6 span.x3nfvp2 span.x193iq5w",  # Another pattern
                    "a[role='link'] span.x193iq5w"  # Link-based author
                ]

                for selector in author_selectors:
                    elements = comment_element.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        name = element.text.strip()
                        if name and len(name) > 1:
                            author = name
                            break

                    if author != "Unknown":
                        break

                # Extract comment text from modern structure
                comment_text = ""

                text_selectors = [
                    "div.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.x1vvkbs div[dir='auto']",  # Main comment text
                    "span.x193iq5w[dir='auto'] div.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.x1vvkbs",  # Another pattern
                    "div.x1lliihq.xjkvuk6.x1iorvi4 span"  # Shorter pattern
                ]

                for selector in text_selectors:
                    elements = comment_element.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        text = element.text.strip()
                        if text and len(text) > 3:
                            comment_text = text
                            break

                    if comment_text:
                        break

                if not comment_text:
                    # If no specific text found, use the entire comment text minus the author
                    full_text = comment_element.text
                    if author != "Unknown" and author in full_text:
                        comment_text = full_text.replace(author, "", 1).strip()

                # Skip if still no text was found
                if not comment_text:
                    continue

                # Extract timestamp
                timestamp = None
                timestamp_selectors = [
                    "a[aria-label*='m']",  # Timestamp links with minutes
                    "a[href*='comment_id']",  # Comment links often have timestamps
                    "span.x4k7w5x.x1h91t0o.x1h9r5lt"  # Modern timestamp class
                ]

                for selector in timestamp_selectors:
                    elements = comment_element.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        # Try to get from aria-label first
                        time_text = element.get_attribute("aria-label")

                        # If not found in aria-label, get text content
                        if not time_text:
                            time_text = element.text.strip()

                        if time_text and any(unit in time_text.lower() for unit in ['m', 'min', 'h', 'hr', 'd', 'day']):
                            timestamp = time_text
                            break

                    if timestamp:
                        break

                # Extract URL
                comment_url = None
                try:
                    # Links with comment_id
                    url_elements = comment_element.find_elements(By.CSS_SELECTOR, "a[href*='comment_id']")
                    if url_elements:
                        comment_url = url_elements[0].get_attribute("href")
                except:
                    pass

                # Create basic comment structure
                comment = Comment(
                    text=comment_text,
                    author=author,
                    timestamp=timestamp,
                    reactions=[],
                    likes_count=0,
                    url=comment_url,
                    replies=[]
                )

                # Add comment to list
                comments.append(comment)

            except Exception as e:
                logger.warning(f"Error extracting modern comment: {str(e)}")
                continue

    except Exception as e:
        logger.warning(f"Failed to extract modern comments: {str(e)}")

    return comments


def extract_posts_integrated(driver, max_posts=DEFAULT_MAX_POSTS):
    """
    Integrated approach to extract posts from Facebook pages that works with both modern and classic interfaces.

    Args:
        driver (webdriver.Chrome): WebDriver instance
        max_posts (int): Maximum number of posts to extract

    Returns:
        List[Post]: List of extracted posts
    """
    posts = []

    try:
        # Detect elements for both modern and classic interfaces
        post_elements = []

        # Modern interface selectors from example
        modern_selectors = [
            "div[aria-label='Comment']",
            "div[role='article']",
            "div.x1n2onr6.x1iorvi4.x4k7w5x",
            "div.html-div.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.xexx8yu.x4uap5.x18d9i69.xkhd6sd",
            "div.xabvvm4.xeyy32k.x1ia1hqs"
        ]

        # Classic interface selectors
        classic_selectors = [
            "div.userContentWrapper",
            "div._5pcr",
            "div._1dwg",
            "div[data-pagelet*='FeedUnit']"
        ]

        # Combine all selectors
        all_selectors = modern_selectors + classic_selectors

        # Try each selector and collect all possible posts
        for selector in all_selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                post_elements.extend(elements)

        # Remove duplicates (using element id)
        seen_ids = set()
        unique_posts = []

        for element in post_elements:
            element_id = element.id
            if element_id not in seen_ids:
                seen_ids.add(element_id)
                unique_posts.append(element)

        # Limit to requested maximum
        post_elements = unique_posts[:max_posts]

        logger.info(f"Found {len(post_elements)} candidate post elements")

        # Process each post element
        for post_element in post_elements:
            try:
                # First try with the enhanced extraction function
                post = extract_post_data(post_element, driver)

                # If we got a good post, add it to the list
                if post and post.content:
                    # If we have no reaction info, try the dedicated function
                    if post.likes_count == 0:
                        post.likes_count = extract_reactions_count(post_element, driver)

                        # If we found reactions, update the reactions list
                        if post.likes_count > 0 and not post.reactions:
                            post.reactions = [Reaction(type=ReactionType.LIKE, count=post.likes_count)]

                    # Check for comments
                    if len(post.comments) == 0:
                        # Try modern comment extraction if regular extraction failed
                        modern_comments = extract_comments_modern(post_element, driver)
                        if modern_comments:
                            post.comments = modern_comments
                            post.comments_count = len(modern_comments)

                    # Now add the post to our list
                    posts.append(post)

                    logger.info(
                        f"Successfully extracted post with {post.likes_count} reactions and {post.comments_count} comments")
            except Exception as e:
                logger.warning(f"Error processing post element: {str(e)}")
                continue

        logger.info(f"Successfully extracted {len(posts)} posts")

    except Exception as e:
        logger.error(f"Error in integrated post extraction: {str(e)}")

    return posts


def scrape_facebook_group(
        group_id: str,
        max_posts: int = DEFAULT_MAX_POSTS,
        max_scroll_attempts: int = DEFAULT_MAX_SCROLL_ATTEMPTS
) -> GroupAnalysis:
    """
    Enhanced scraper for Facebook Groups to analyze posts, comments, and reactions.
    Updated to work with both modern and classic interfaces.

    Args:
        group_id (str): Facebook Group ID
        max_posts (int): Maximum number of posts to analyze
        max_scroll_attempts (int): Maximum number of scroll attempts

    Returns:
        GroupAnalysis: Analysis of the group's content

    Raises:
        HTTPException: If there's an error accessing the page
    """
    with get_driver(stealth=True, use_proxy=True) as driver:
        # Ensure we have an active Facebook session
        try:
            from shared.fb_account_manager import fb_account_manager
            fb_account_manager.ensure_logged_in(driver)
        except Exception as e:
            logger.warning(f"FB account login skipped: {e}")

        # Construct the group URL
        url = f'https://www.facebook.com/groups/{group_id}'

        logger.info(f"Analyzing Facebook Group with URL: {url}")

        try:
            driver.get(url)

            # Use a longer initial wait for the page to fully load
            try:
                wait_for_element(driver, By.CSS_SELECTOR, "div[role='main']", timeout=15)
            except:
                # Try alternative selectors if main content not found
                try:
                    wait_for_element(driver, By.CSS_SELECTOR, "div[data-pagelet='GroupFeed']", timeout=15)
                except:
                    # One more fallback for modern interface
                    wait_for_element(driver, By.CSS_SELECTOR, "div.x9f619", timeout=15)

            # Handle login/cookie dialogs
            handle_facebook_dialogs(driver)

            # Scroll slightly to trigger content loading
            driver.execute_script("window.scrollBy(0, 300);")
            time.sleep(2)

            # Extract group name with multiple approaches
            group_name = f"Group {group_id}"  # Default fallback
            group_name_selectors = [
                "h1[dir='auto']",  # Standard group name
                "a[role='link'] span.x193iq5w",  # Link-based name
                "div.x1gslohp h1",  # Header-based name
                "div[data-pagelet='GroupHeaderTitle'] span"  # Pagelet-based name
            ]

            for selector in group_name_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        name = element.text.strip()
                        if name and len(name) > 1:
                            group_name = name
                            break

                    if group_name != f"Group {group_id}":
                        break
                except:
                    continue

            # Try to extract member count with improved patterns
            members_count = None
            try:
                # Multiple approaches for different FB layouts
                member_selectors = [
                    "//span[contains(text(), 'miembro')]",
                    "//span[contains(text(), 'member')]",
                    "//div[contains(text(), 'miembro')]",
                    "//div[contains(text(), 'member')]",
                    "//span[contains(@class, 'xdj266r')][contains(text(), 'member')]"
                ]

                for selector in member_selectors:
                    member_elements = driver.find_elements(By.XPATH, selector)
                    for element in member_elements:
                        text = element.text.strip()
                        # Look for numbers in member text
                        count_match = re.search(r'([\d,.]+)', text)
                        if count_match:
                            members_text = count_match.group(1).replace(',', '').replace('.', '')
                            members_count = int(members_text)
                            break

                    if members_count:
                        break
            except Exception as e:
                logger.warning(f"Could not extract member count: {str(e)}")

            # Scroll to load content with the improved scroll mechanic
            scroll_attempts = 0
            last_height = driver.execute_script("return document.body.scrollHeight")

            while scroll_attempts < max_scroll_attempts:
                # Scroll down
                driver.execute_script("window.scrollBy(0, 800);")
                time.sleep(DEFAULT_SCROLL_DELAY)

                # Try to expand "See More" within posts occasionally
                if scroll_attempts % 2 == 0:
                    try:
                        see_more_buttons = driver.find_elements(
                            By.XPATH, "//div[@role='button' and contains(@aria-label, 'See more')]")

                        # Also try the specific text-based approach from example
                        text_buttons = driver.find_elements(
                            By.XPATH, "//div[contains(@class, 'x1i10hfl') and contains(text(), 'See more')]")

                        all_buttons = see_more_buttons + text_buttons

                        for button in all_buttons[:5]:  # Limit to 5 per scroll
                            try:
                                driver.execute_script("arguments[0].click();", button)
                                time.sleep(0.5)
                            except:
                                pass
                    except:
                        pass

                # Check if we've scrolled enough
                new_height = driver.execute_script("return document.body.scrollHeight")
                scroll_attempts += 1

                # If height hasn't changed, try different scroll tactics
                if new_height == last_height:
                    # Try different strategies based on attempt number
                    if scroll_attempts % 3 == 0:
                        # Random scroll jump
                        random_scroll = 500 + (scroll_attempts * 100)
                        driver.execute_script(f"window.scrollBy(0, {random_scroll});")
                    elif scroll_attempts % 3 == 1:
                        # Try scrolling to bottom
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    else:
                        # Try to find and click "View more comments" buttons
                        try:
                            more_buttons = driver.find_elements(By.XPATH,
                                                                "//span[contains(text(), 'View more comments') or contains(text(), 'Ver más comentarios')]")
                            for button in more_buttons[:3]:
                                try:
                                    driver.execute_script("arguments[0].click();", button)
                                    time.sleep(1)
                                except:
                                    pass
                        except:
                            pass

                last_height = new_height

                # Check if we have enough posts visible
                current_posts = len(driver.find_elements(By.CSS_SELECTOR, "div[role='article']"))
                if current_posts >= max_posts:
                    logger.info(f"Found {current_posts} posts, breaking scroll loop")
                    break

            # Allow the page to stabilize
            time.sleep(2)

            # Use our integrated extraction approach
            posts = extract_posts_integrated(driver, max_posts)

            # If we don't have enough posts, try one more extraction
            if len(posts) < max_posts / 2 and max_posts > 5:
                logger.warning(f"Only found {len(posts)} posts, trying more scrolling")

                # Do some more aggressive scrolling
                for _ in range(3):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)

                # Try extraction again
                more_posts = extract_posts_integrated(driver, max_posts - len(posts))
                posts.extend(more_posts)

            logger.info(f"Final post count: {len(posts)}")

            # Collect all comments for top comments selection
            all_comments = []
            reaction_counts = Counter()

            for post in posts:
                # Add to reaction counts
                for reaction in post.reactions:
                    reaction_counts[reaction.type] += reaction.count

                # Process comments
                for comment in post.comments:
                    all_comments.append(comment)

                    # Check replies too
                    if comment.replies:
                        for reply in comment.replies:
                            all_comments.append(reply)

            # Sort comments by likes to get top comments
            top_comments = sorted(all_comments, key=lambda x: x.likes_count, reverse=True)[:20]

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

            # Create group analysis object
            group_analysis = GroupAnalysis(
                group_name=group_name,
                group_id=group_id,
                group_url=url,
                members_count=members_count,
                posts=posts,
                top_comments=top_comments,
                reaction_stats={k.value: v for k, v in reaction_counts.items()},
                most_active_members=most_active_members
            )

            return group_analysis

        except TimeoutException as e:
            logger.error(f"Timeout loading page: {str(e)}")
            raise HTTPException(status_code=504, detail="Timed out loading Facebook group")
        except WebDriverException as e:
            logger.error(f"WebDriver error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error accessing page: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error scraping Facebook group: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Unexpected error scraping Facebook group: {str(e)}")


def extract_reactions_count(post_element, driver) -> int:
    """
    Extract the total reaction count from a post element.

    Args:
        post_element: Selenium WebElement representing a post
        driver: The WebDriver instance

    Returns:
        int: Total number of reactions
    """
    total_reactions = 0

    try:
        # Target the specific reaction count element from the example
        # Look for the specific structure where the reaction count is stored
        reaction_count_elements = post_element.find_elements(By.CSS_SELECTOR, "span.x1e558r4")

        for element in reaction_count_elements:
            try:
                # Try to get the text which should be the number
                count_text = element.text.strip()
                if count_text and count_text.isdigit():
                    total_reactions = int(count_text)
                    break
            except:
                continue

        # If not found, try alternative selectors
        if total_reactions == 0:
            # Look for the reaction summary element
            reaction_summary = post_element.find_elements(By.CSS_SELECTOR,
                                                          "div.x1i10hfl[aria-label*='All reactions:']")
            if reaction_summary:
                # Extract the value from the element
                for element in reaction_summary:
                    label = element.get_attribute("aria-label")
                    if label:
                        # Extract number from "All reactions: X"
                        count_match = re.search(r'All reactions:\s+(\d+)', label)
                        if count_match:
                            total_reactions = int(count_match.group(1))
                            break

        # If still not found, try looking for the reaction count directly
        if total_reactions == 0:
            # This specific class path was found in the example
            count_elements = post_element.find_elements(By.CSS_SELECTOR,
                                                        "span.x1e558r4")
            if count_elements:
                for element in count_elements:
                    try:
                        # Find parent elements that might contain the total count
                        parent = element.find_element(By.XPATH, "./..")
                        if "All reactions:" in parent.get_attribute("aria-label") or "":
                            # Get the text inside the span
                            count_text = element.text.strip()
                            if count_text and count_text.isdigit():
                                total_reactions = int(count_text)
                                break
                    except:
                        pass

        # Another approach: try to find the direct numeric span within the reaction area
        if total_reactions == 0:
            # Look for spans with numeric content near reaction icons
            reaction_area = post_element.find_elements(By.CSS_SELECTOR,
                                                       "div.x9f619.x1n2onr6.x1ja2u2z.x78zum5.xdt5ytf.x2lah0s.x193iq5w")
            for area in reaction_area:
                # Look for spans with numbers
                spans = area.find_elements(By.CSS_SELECTOR, "span")
                for span in spans:
                    text = span.text.strip()
                    if text and text.isdigit():
                        total_reactions = int(text)
                        break

                if total_reactions > 0:
                    break

        # Direct class-based approach from example HTML
        if total_reactions == 0:
            reaction_counts = post_element.find_elements(By.CSS_SELECTOR,
                                                         "span.x1e558r4")
            for span in reaction_counts:
                text = span.text.strip()
                if text and text.isdigit():
                    total_reactions = int(text)
                    break

    except Exception as e:
        logger.warning(f"Error extracting reaction count: {str(e)}")

    return total_reactions


def get_group_posts_by_keyword(
        group_id: str,
        keyword: str,
        max_posts: int = DEFAULT_MAX_POSTS,
        max_scroll_attempts: int = DEFAULT_MAX_SCROLL_ATTEMPTS,
        case_sensitive: bool = False
) -> List[Post]:
    """
    Search a Facebook Group for posts containing a specific keyword.

    Args:
        group_id (str): Facebook Group ID
        keyword (str): Keyword to search for
        max_posts (int): Maximum number of posts to analyze
        max_scroll_attempts (int): Maximum number of scroll attempts
        case_sensitive (bool): Whether the search should be case-sensitive

    Returns:
        List[Post]: List of posts containing the keyword

    Raises:
        HTTPException: If there's an error accessing the page
    """
    try:
        # Get all group data
        group_analysis = scrape_facebook_group(
            group_id=group_id,
            max_posts=max_posts,
            max_scroll_attempts=max_scroll_attempts
        )

        # Filter posts by keyword
        matching_posts = []

        for post in group_analysis.posts:
            # Check if keyword is in post content
            if case_sensitive:
                if keyword in post.content:
                    matching_posts.append(post)
                    continue
            else:
                if keyword.lower() in post.content.lower():
                    matching_posts.append(post)
                    continue

            # Check if keyword is in any comments
            for comment in post.comments:
                comment_found = False

                # Check comment text
                if case_sensitive:
                    if keyword in comment.text:
                        comment_found = True
                else:
                    if keyword.lower() in comment.text.lower():
                        comment_found = True

                # Check replies
                if not comment_found and comment.replies:
                    for reply in comment.replies:
                        if case_sensitive:
                            if keyword in reply.text:
                                comment_found = True
                                break
                        else:
                            if keyword.lower() in reply.text.lower():
                                comment_found = True
                                break

                if comment_found:
                    matching_posts.append(post)
                    break

        return matching_posts

    except Exception as e:
        logger.error(f"Error searching group posts by keyword: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error searching group posts: {str(e)}")


def get_group_member_activity(
        group_id: str,
        member_name: str,
        max_posts: int = DEFAULT_MAX_POSTS,
        max_scroll_attempts: int = DEFAULT_MAX_SCROLL_ATTEMPTS
) -> Dict[str, Any]:
    """
    Get activity details for a specific group member.

    Args:
        group_id (str): Facebook Group ID
        member_name (str): Name of the member to analyze
        max_posts (int): Maximum number of posts to analyze
        max_scroll_attempts (int): Maximum number of scroll attempts

    Returns:
        Dict[str, Any]: Member activity statistics

    Raises:
        HTTPException: If there's an error accessing the page
    """
    try:
        # Get all group data
        group_analysis = scrape_facebook_group(
            group_id=group_id,
            max_posts=max_posts,
            max_scroll_attempts=max_scroll_attempts
        )

        # Find member's posts
        member_posts = []
        for post in group_analysis.posts:
            if post.author.lower() == member_name.lower():
                member_posts.append(post)

        # Find member's comments and replies
        member_comments = []
        member_replies = []

        for post in group_analysis.posts:
            for comment in post.comments:
                if comment.author.lower() == member_name.lower():
                    # Add post context to the comment
                    comment_with_context = {
                        "comment": comment,
                        "post_id": post.post_id,
                        "post_author": post.author,
                        "post_content_preview": post.content[:100] + "..." if len(post.content) > 100 else post.content
                    }
                    member_comments.append(comment_with_context)

                # Check replies
                if comment.replies:
                    for reply in comment.replies:
                        if reply.author.lower() == member_name.lower():
                            # Add post and parent comment context
                            reply_with_context = {
                                "reply": reply,
                                "post_id": post.post_id,
                                "post_author": post.author,
                                "parent_comment_author": comment.author,
                                "parent_comment_preview": comment.text[:50] + "..." if len(
                                    comment.text) > 50 else comment.text
                            }
                            member_replies.append(reply_with_context)

        # Calculate total reactions received
        total_reactions = 0
        reaction_types = Counter()

        for post in member_posts:
            for reaction in post.reactions:
                total_reactions += reaction.count
                reaction_types[reaction.type] += reaction.count

        # Add comment and reply reactions
        for comment_data in member_comments:
            comment = comment_data["comment"]
            for reaction in comment.reactions:
                total_reactions += reaction.count
                reaction_types[reaction.type] += reaction.count

        for reply_data in member_replies:
            reply = reply_data["reply"]
            for reaction in reply.reactions:
                total_reactions += reaction.count
                reaction_types[reaction.type] += reaction.count

        # Calculate activity summary
        activity_summary = {
            "member_name": member_name,
            "posts_count": len(member_posts),
            "comments_count": len(member_comments),
            "replies_count": len(member_replies),
            "total_contributions": len(member_posts) + len(member_comments) + len(member_replies),
            "total_reactions_received": total_reactions,
            "reaction_breakdown": {k.value: v for k, v in reaction_types.items()},
            "posts": member_posts,
            "comments": member_comments,
            "replies": member_replies
        }

        return activity_summary

    except Exception as e:
        logger.error(f"Error analyzing group member activity: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error analyzing member activity: {str(e)}")


def analyze_group_posts_frequency(
        group_id: str,
        max_posts: int = DEFAULT_MAX_POSTS,
        max_scroll_attempts: int = DEFAULT_MAX_SCROLL_ATTEMPTS
) -> Dict[str, Any]:
    """
    Analyze the frequency of posts in a Facebook Group.

    Args:
        group_id (str): Facebook Group ID
        max_posts (int): Maximum number of posts to analyze
        max_scroll_attempts (int): Maximum number of scroll attempts

    Returns:
        Dict[str, Any]: Post frequency analysis

    Raises:
        HTTPException: If there's an error accessing the page
    """
    try:
        # Get all group data
        group_analysis = scrape_facebook_group(
            group_id=group_id,
            max_posts=max_posts,
            max_scroll_attempts=max_scroll_attempts
        )

        # Extract timestamps and organize by date/time
        post_times = []
        post_dates = []

        for post in group_analysis.posts:
            # Skip posts without timestamp
            if not post.timestamp:
                continue

            # Try to extract just the time component
            time_match = re.search(r'(\d+):(\d+)', post.timestamp)
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2))

                # Convert 12-hour format to 24-hour if needed
                if 'PM' in post.timestamp and hour < 12:
                    hour += 12
                elif 'AM' in post.timestamp and hour == 12:
                    hour = 0

                post_times.append(hour)

            # Extract day information if available
            day_match = re.search(r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)',
                                  post.timestamp, re.IGNORECASE)
            if day_match:
                post_dates.append(day_match.group(1).lower())

        # Calculate frequency by hour
        hour_frequency = Counter(post_times)
        hour_stats = [{"hour": hour, "count": count}
                      for hour, count in sorted(hour_frequency.items())]

        # Calculate frequency by day
        day_frequency = Counter(post_dates)

        # Ensure all days are represented
        days_of_week = ['monday', 'tuesday', 'wednesday', 'thursday',
                        'friday', 'saturday', 'sunday']

        day_stats = [{"day": day, "count": day_frequency.get(day, 0)}
                     for day in days_of_week]

        # Calculate most active periods
        most_active_hour = max(hour_stats, key=lambda x: x["count"]) if hour_stats else None
        most_active_day = max(day_stats, key=lambda x: x["count"]) if day_stats else None

        # Prepare analysis results
        frequency_analysis = {
            "group_name": group_analysis.group_name,
            "group_id": group_id,
            "total_posts_analyzed": len(group_analysis.posts),
            "posts_with_timestamps": len(post_times),
            "hourly_distribution": hour_stats,
            "daily_distribution": day_stats,
            "most_active_hour": most_active_hour,
            "most_active_day": most_active_day
        }

        return frequency_analysis

    except Exception as e:
        logger.error(f"Error analyzing post frequency: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error analyzing post frequency: {str(e)}")


def analyze_group_engagement(
        group_id: str,
        max_posts: int = DEFAULT_MAX_POSTS,
        max_scroll_attempts: int = DEFAULT_MAX_SCROLL_ATTEMPTS
) -> Dict[str, Any]:
    """
    Analyze engagement metrics for posts in a Facebook Group.

    Args:
        group_id (str): Facebook Group ID
        max_posts (int): Maximum number of posts to analyze
        max_scroll_attempts (int): Maximum number of scroll attempts

    Returns:
        Dict[str, Any]: Group engagement analysis

    Raises:
        HTTPException: If there's an error accessing the page
    """
    try:
        # Get all group data
        group_analysis = scrape_facebook_group(
            group_id=group_id,
            max_posts=max_posts,
            max_scroll_attempts=max_scroll_attempts
        )

        # Calculate engagement metrics
        total_likes = 0
        total_comments = 0
        total_reactions = 0
        posts_with_comments = 0
        post_engagement_rates = []

        for post in group_analysis.posts:
            # Count total likes
            total_likes += post.likes_count

            # Count total comments including replies
            comments_count = post.comments_count
            replies_count = sum(len(comment.replies) for comment in post.comments)
            post_comments_total = comments_count + replies_count

            total_comments += post_comments_total

            # Count if post has comments
            if post_comments_total > 0:
                posts_with_comments += 1

            # Count total reactions
            post_reactions = sum(reaction.count for reaction in post.reactions)
            total_reactions += post_reactions

            # Calculate engagement rate for this post
            # (likes + comments + reactions) / possible views (approximate with member count)
            if group_analysis.members_count:
                engagement_rate = (
                                              post.likes_count + post_comments_total + post_reactions) / group_analysis.members_count * 100
                post_engagement_rates.append({
                    "post_id": post.post_id,
                    "author": post.author,
                    "likes": post.likes_count,
                    "comments": post_comments_total,
                    "reactions": post_reactions,
                    "engagement_rate": round(engagement_rate, 2)
                })

        # Calculate averages
        avg_likes_per_post = total_likes / len(group_analysis.posts) if group_analysis.posts else 0
        avg_comments_per_post = total_comments / len(group_analysis.posts) if group_analysis.posts else 0
        avg_reactions_per_post = total_reactions / len(group_analysis.posts) if group_analysis.posts else 0

        # Percentage of posts with comments
        comments_percentage = (posts_with_comments / len(group_analysis.posts) * 100) if group_analysis.posts else 0

        # Find most engaging posts (sort by engagement rate)
        top_engaging_posts = sorted(post_engagement_rates, key=lambda x: x["engagement_rate"], reverse=True)[:5]

        # Prepare engagement analysis
        engagement_analysis = {
            "group_name": group_analysis.group_name,
            "group_id": group_id,
            "members_count": group_analysis.members_count,
            "total_posts_analyzed": len(group_analysis.posts),
            "total_likes": total_likes,
            "total_comments": total_comments,
            "total_reactions": total_reactions,
            "avg_likes_per_post": round(avg_likes_per_post, 2),
            "avg_comments_per_post": round(avg_comments_per_post, 2),
            "avg_reactions_per_post": round(avg_reactions_per_post, 2),
            "posts_with_comments_percentage": round(comments_percentage, 2),
            "top_engaging_posts": top_engaging_posts
        }

        return engagement_analysis

    except Exception as e:
        logger.error(f"Error analyzing group engagement: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error analyzing group engagement: {str(e)}")


# ── G4: Group Taxonomy Search by Category ──

# Maps category codes to Google dork fragments for Facebook group/page search
CATEGORY_DORKS: Dict[str, Dict[str, str]] = {
    "negocios": {
        "label": "Negocios / Lugares locales",
        "dork": 'site:facebook.com/groups OR site:facebook.com/pages "{query}" ("negocio" OR "local" OR "tienda" OR "restaurante" OR "servicio")',
    },
    "empresas": {
        "label": "Empresas / Organizaciones",
        "dork": 'site:facebook.com/groups OR site:facebook.com/pages "{query}" ("empresa" OR "organización" OR "institución" OR "corporativo")',
    },
    "marcas": {
        "label": "Marcas / Productos",
        "dork": 'site:facebook.com/groups OR site:facebook.com/pages "{query}" ("marca" OR "producto" OR "oficial" OR "tienda oficial")',
    },
    "artistas": {
        "label": "Artistas / Figuras públicas",
        "dork": 'site:facebook.com/groups OR site:facebook.com/pages "{query}" ("artista" OR "banda" OR "músico" OR "figura pública" OR "cantante")',
    },
    "entretenimiento": {
        "label": "Entretenimiento",
        "dork": 'site:facebook.com/groups OR site:facebook.com/pages "{query}" ("entretenimiento" OR "diversión" OR "juegos" OR "eventos" OR "cine")',
    },
    "causas": {
        "label": "Causas / Comunidades",
        "dork": 'site:facebook.com/groups OR site:facebook.com/pages "{query}" ("causa" OR "comunidad" OR "voluntariado" OR "apoyo" OR "fundación")',
    },
}


def _google_search(dork_query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Execute a Google search using the given dork query and return parsed results.
    Uses Google's standard search with scraping as a lightweight approach.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "es-MX,es;q=0.9",
    }
    url = f"https://www.google.com/search?q={quote_plus(dork_query)}&num={max_results}&hl=es"

    results: List[Dict[str, Any]] = []
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(resp.text, "html.parser")
        for g in soup.select("div.g, div[data-sokoban-container]"):
            link_el = g.select_one("a[href]")
            title_el = g.select_one("h3")
            snippet_el = g.select_one("div.VwiC3b, span.aCOpRe, div[data-sncf]")

            if not link_el:
                continue
            href = link_el.get("href", "")
            if not href.startswith("http"):
                continue

            results.append({
                "title": title_el.get_text(strip=True) if title_el else "",
                "url": href,
                "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
            })

            if len(results) >= max_results:
                break
    except Exception as e:
        logger.warning(f"Google dork search failed for query '{dork_query[:80]}...': {e}")

    return results


def search_groups_by_category(
    query: str,
    categories: List[str],
    max_results: int = 5,
) -> GroupCategorySearchResponse:
    """
    Search Facebook groups/pages segmented by taxonomy categories using Google dorks.
    """
    all_results: List[GroupCategoryResult] = []
    total = 0

    for cat_code in categories:
        cat_info = CATEGORY_DORKS.get(cat_code)
        if not cat_info:
            logger.warning(f"Unknown group category code: {cat_code}")
            continue

        dork = cat_info["dork"].replace("{query}", query)
        items = _google_search(dork, max_results)
        total += len(items)

        all_results.append(GroupCategoryResult(
            category=cat_code,
            category_label=cat_info["label"],
            dork_query=dork,
            results=items,
        ))

    return GroupCategorySearchResponse(
        query=query,
        categories=categories,
        results=all_results,
        total_results=total,
    )