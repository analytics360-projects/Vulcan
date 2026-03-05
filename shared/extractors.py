"""Shared DOM/text extraction utilities — moved from utils/extractors.py"""
import re
from typing import Optional
from config import logger


def extract_price(text: str) -> Optional[float]:
    price_pattern = re.compile(
        r'(?:[$€£¥])?(?:\s)?([0-9][0-9\s,.]*(?:\.[0-9]{2}|\,[0-9]{2})?)\s?(?:[$€£¥])?'
    )
    matches = price_pattern.finditer(text)
    candidates = []
    for m in matches:
        price_str = m.group(1)
        if re.match(r'^(19|20)\d{2}$', price_str):
            continue
        candidates.append(price_str)
    if not candidates:
        return None
    price_str = candidates[0].replace(' ', '')
    if len(price_str) > 8 and ('.' in price_str or ',' in price_str):
        decimal_pos = price_str.find('.') if '.' in price_str else price_str.find(',')
        if decimal_pos > 0 and len(price_str) - decimal_pos > 6:
            price_str = price_str[:decimal_pos + 3]
    try:
        if '.' in price_str and ',' in price_str and price_str.rindex('.') > price_str.rindex(','):
            return float(price_str.replace(',', ''))
        elif '.' in price_str and ',' in price_str and price_str.rindex(',') > price_str.rindex('.'):
            return float(price_str.replace('.', '').replace(',', '.'))
        elif '.' in price_str and ',' not in price_str:
            return float(price_str)
        elif ',' in price_str and '.' not in price_str:
            return float(price_str.replace(',', '.'))
        else:
            return float(price_str)
    except Exception as e:
        logger.warning(f"Failed to parse price from '{price_str}': {e}")
        return None


def extract_posted_time(text: str) -> Optional[str]:
    patterns = [
        r'posted\s+(\d+\s+(?:minute|hour|day|week|month)s?\s+ago)',
        r'listed\s+(\d+\s+(?:minute|hour|day|week|month)s?\s+ago)',
        r'(\d+\s+(?:minute|hour|day|week|month)s?\s+ago)',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def extract_image_url(item_element) -> Optional[str]:
    try:
        img_tag = item_element.find('img')
        if img_tag and img_tag.get('src'):
            return img_tag.get('src')
        div_with_bg = item_element.find('div', style=lambda v: v and 'background-image' in v)
        if div_with_bg:
            url_match = re.search(r'url\([\'"]?(.*?)[\'"]?\)', div_with_bg.get('style', ''))
            if url_match:
                return url_match.group(1)
    except Exception as e:
        logger.warning(f"Failed to extract image URL: {e}")
    return None


def extract_marketplace_url(item_element) -> Optional[str]:
    try:
        links = item_element.find_all('a', href=lambda h: h and '/marketplace/item/' in h)
        if links:
            href = links[0].get('href')
            if href:
                return href if href.startswith('http') else f"https://www.facebook.com{href}"
        for link in item_element.find_all('a', href=True):
            href = link.get('href')
            if href and ('/marketplace/' in href or '/item/' in href):
                return href if href.startswith('http') else f"https://www.facebook.com{href}"
        for el in item_element.find_all(attrs={"data-href": True}):
            dh = el.get('data-href')
            if dh and '/marketplace/' in dh:
                return f"https://www.facebook.com{dh}"
    except Exception as e:
        logger.warning(f"Failed to extract product URL: {e}")
    return None
