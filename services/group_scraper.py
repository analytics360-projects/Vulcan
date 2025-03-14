from typing import List, Optional, Dict, Any
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from collections import Counter
import re
import time
from fastapi import HTTPException

from config import (
    DEFAULT_MAX_POSTS, DEFAULT_MAX_COMMENTS, DEFAULT_MAX_SCROLL_ATTEMPTS,
    DEFAULT_SCROLL_DELAY, logger
)
from models.group import Post, Comment, Reaction, ReactionType, GroupAnalysis
from services.webdriver import get_driver, handle_facebook_dialogs, wait_for_element


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

        reaction_elements = []
        for selector in reaction_selectors:
            elements = element.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                reaction_elements = elements
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
    Extract data from a post element.

    Args:
        post_element: Selenium WebElement representing a post
        driver: The WebDriver instance

    Returns:
        Optional[Post]: A Post object, or None if the post cannot be extracted
    """
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
            # Last resort: generate a pseudo ID based on content
            try:
                post_content = post_element.text[:100]  # Take first 100 chars
                import hashlib
                post_id = hashlib.md5(post_content.encode()).hexdigest()[:16]
                logger.warning(f"Generated pseudo ID for post: {post_id}")
            except:
                logger.warning("Could not extract or generate post ID, skipping post")
                return None

        # Extract post author
        author = extract_author(post_element)

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

            # If still no content, try div elements
            if not content:
                div_elements = post_element.find_elements(By.CSS_SELECTOR, "div[dir='auto']")
                filtered_div_texts = []
                for div in div_elements:
                    text = div.text.strip()
                    if text and len(text) > 20:  # More likely to be content if longer
                        filtered_div_texts.append(text)

                if filtered_div_texts:
                    content = max(filtered_div_texts, key=len)
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

        # If timestamp not found, try other selectors
        if not timestamp:
            for span in post_element.find_elements(By.CSS_SELECTOR, "span"):
                text = span.text
                if text and any(time_word in text.lower() for time_word in
                                ['min', 'hr', 'h', 'seg', 'hour', 'day', 'hora', 'día']):
                    timestamp = text
                    break

        # Extract image if any
        image_url = None
        img_elements = post_element.find_elements(By.CSS_SELECTOR, "img[src*='scontent']")
        if img_elements:
            image_url = img_elements[0].get_attribute("src")

        # Extract reactions
        reactions = extract_reactions(post_element, driver)

        # Extract likes count
        likes_count = sum(reaction.count for reaction in reactions)

        # Extract comments
        comments = extract_comments(post_element, driver)
        comments_count = len(comments)

        # Create post object
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
            authorized=False
        )

        return post

    except Exception as e:
        logger.warning(f"Failed to extract post data: {str(e)}")
        return None


def scrape_facebook_group(
        group_id: str,
        max_posts: int = DEFAULT_MAX_POSTS,
        max_scroll_attempts: int = DEFAULT_MAX_SCROLL_ATTEMPTS
) -> GroupAnalysis:
    """
    Scrape a Facebook Group to analyze posts, comments, and reactions.

    Args:
        group_id (str): Facebook Group ID
        max_posts (int): Maximum number of posts to analyze
        max_scroll_attempts (int): Maximum number of scroll attempts

    Returns:
        GroupAnalysis: Analysis of the group's content

    Raises:
        HTTPException: If there's an error accessing the page
    """
    with get_driver() as driver:
        # Construct the group URL
        url = f'https://www.facebook.com/groups/{group_id}'

        logger.info(f"Analyzing Facebook Group with URL: {url}")

        try:
            driver.get(url)

            # Wait for the page to load
            wait_for_element(driver, By.CSS_SELECTOR, "div[role='main']")

            # Handle various login/cookie dialogs
            handle_facebook_dialogs(driver)

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
            except Exception as e:
                logger.warning(f"Could not extract member count: {str(e)}")

            # Scroll to load more posts with improved scroll mechanism
            scroll_attempts = 0
            last_post_count = 0
            stuck_count = 0

            while scroll_attempts < max_scroll_attempts:
                # Scroll down gradually
                driver.execute_script("window.scrollBy(0, 800);")
                time.sleep(DEFAULT_SCROLL_DELAY)

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
                        # Try different scroll strategies
                        if stuck_count == 3:
                            # Random scrolling
                            random_scroll = 500 + (scroll_attempts * 100)
                            driver.execute_script(f"window.scrollBy(0, {random_scroll});")
                            time.sleep(1)
                            driver.execute_script("window.scrollBy(0, -200);")  # Scroll back up a bit
                        elif stuck_count == 4:
                            # Try scrolling to bottom
                            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        elif stuck_count == 5:
                            # Try clicking "See More" buttons
                            try:
                                more_buttons = driver.find_elements(By.XPATH,
                                                                    "//span[contains(text(), 'See More') or contains(text(), 'Ver más') or contains(text(), 'Show more')]")
                                for button in more_buttons[:5]:
                                    try:
                                        button.click()
                                        time.sleep(0.5)
                                    except:
                                        pass
                            except:
                                pass
                            stuck_count = 0  # Reset after trying all strategies
                        time.sleep(1)
                else:
                    # Reset stuck counter if we're making progress
                    stuck_count = 0

                last_post_count = post_count
                scroll_attempts += 1

                # After several scroll attempts, try to click buttons to show more content
                if scroll_attempts % 3 == 0:
                    try:
                        # Try clicking various buttons that might show more content
                        button_selectors = [
                            "//span[contains(text(), 'See More') or contains(text(), 'Ver más')]",
                            "//span[contains(text(), 'Show more posts') or contains(text(), 'Mostrar más publicaciones')]",
                            "//span[contains(text(), 'Show more comments') or contains(text(), 'Ver más comentarios')]",
                            "//span[contains(text(), 'View more comments') or contains(text(), 'Ver más comentarios')]"
                        ]

                        for selector in button_selectors:
                            buttons = driver.find_elements(By.XPATH, selector)
                            for button in buttons[:3]:  # Limit to 3 buttons per type
                                try:
                                    button.click()
                                    time.sleep(1)
                                except:
                                    pass
                    except Exception as e:
                        logger.warning(f"Error clicking content expansion buttons: {str(e)}")

            # Find all post elements
            post_elements = driver.find_elements(By.CSS_SELECTOR, "div[role='article']")
            logger.info(f"Found {len(post_elements)} post elements in total")

            # Extract all post data
            posts = []
            all_comments = []
            reaction_counts = Counter()

            for post_element in post_elements[:max_posts]:
                try:
                    post = extract_post_data(post_element, driver)
                    if post:
                        posts.append(post)

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
                except Exception as e:
                    logger.warning(f"Error processing post: {str(e)}")
                    continue

            logger.info(f"Successfully extracted {len(posts)} posts with {len(all_comments)} comments")

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

            # Add "Unknown" if it's a significant contributor
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