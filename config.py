import logging
import os
from pathlib import Path

# Application settings
APP_NAME = "Web Scraper API"
APP_VERSION = "2.0.0"
APP_DESCRIPTION = "API for scraping Facebook Marketplace, Groups, and News Articles"

# Webdriver settings
HEADLESS = os.getenv("HEADLESS_BROWSER", "false").lower() == "false"
WINDOW_SIZE = "1920,1080"
DEFAULT_TIMEOUT = 30  # in seconds
BROWSER_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Scraping settings
DEFAULT_MAX_RESULTS = 100
DEFAULT_MAX_SCROLL_ATTEMPTS = 10
DEFAULT_SCROLL_DELAY = 3  # in seconds

# Marketplace defaults
DEFAULT_MIN_PRICE = 0
DEFAULT_MAX_PRICE = 1000
DEFAULT_DAYS_LISTED = 7

# Group defaults
DEFAULT_MAX_POSTS = 30
DEFAULT_MAX_COMMENTS = 50

# News defaults
DEFAULT_NEWS_LANGUAGE = "es"
DEFAULT_NEWS_COUNTRY = "MX"
DEFAULT_NEWS_MAX_RESULTS = 5

# Logging settings
LOG_LEVEL = logging.INFO
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_FILE = Path("web_scraper.log")

# Configure logging
logging.basicConfig(
    level=LOG_LEVEL,
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

# Create logger
logger = logging.getLogger("web_scraper")