"""Shared web scraping utilities — extracted from services/web_scraper.py"""
import re
from bs4 import BeautifulSoup
from config import logger


def clean_html(raw_html: str) -> str:
    """Remove scripts, styles, and HTML tags from raw HTML."""
    if not raw_html:
        return ""
    clean = re.sub(r"<script.*?</script>", "", raw_html, flags=re.DOTALL)
    clean = re.sub(r"<style.*?</style>", "", clean, flags=re.DOTALL)
    clean = re.sub(r'style="[^"]*"', "", clean)
    clean = re.sub(r"\n+", " ", clean)
    soup = BeautifulSoup(clean, "lxml")
    return soup.get_text(separator=" ", strip=True)
