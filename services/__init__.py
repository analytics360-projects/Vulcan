# Import services for easy access
from services.webdriver import get_driver, handle_facebook_dialogs
from services.marketplace_scraper import scrape_marketplace
from services.group_scraper import scrape_facebook_group
from services.web_scraper import (
    fetch_google_news, extract_article_content, fetch_news_with_content
)