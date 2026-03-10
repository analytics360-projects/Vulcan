"""
Vulcan — Unified Configuration (Pydantic Settings)
Consolidates: Vulcan, Hades, nyx-crawler, Hugin, Skadi
"""
import logging
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── App ──
    app_name: str = "Vulcan OSINT Platform"
    app_version: str = "3.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # ── WebDriver (Selenium/Chrome) ──
    headless_browser: bool = True
    window_size: str = "1920,1080"
    default_timeout: int = 6000
    browser_user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # ── Scraping defaults ──
    max_results: int = 100
    max_scroll_attempts: int = 10
    scroll_delay: int = 3
    max_posts: int = 30
    max_comments: int = 50

    # ── News / LLM ──
    news_language: str = "es"
    news_country: str = "MX"
    news_max_results: int = 5
    llm_api_url: str = "http://10.19.5.244:11434/api/generate"
    llm_model: str = "deepseek-r1:7b"
    llm_timeout: int = 6000

    # ── RavenDB (Hades/SANS) ──
    ravendb_url: str = "http://10.19.5.41:8082/"
    ravendb_database: str = "Sans"

    # ── Tor (nyx-crawler / Dark Web) ──
    tor_socks_port: int = 9050
    tor_control_port: int = 9051
    tor_control_password: str = ""
    tor_request_delay: float = 2.0
    tor_max_retries: int = 3
    tor_timeout: int = 30

    # ── Intelligence (Hugin) ──
    ollama_api_url: str = "http://10.19.5.244:11434"
    ollama_model: str = "gemma3:27b"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "10.19.5.96:9000"
    minio_access_key_id: str = "RiiQ1Hd4xDYpBPPi"
    minio_secret_access_key: str = "yVDMrYpz4xZAVNBdtxXK6SrJQa3HVa9p"
    bucket_name: str = "orion-estatal"
    minio_secure: bool = False
    cuda_visible_devices: str = "0"
    max_concurrent_gpu_jobs: int = 2
    insightface_model_name: str = "antelopev2"
    yolo_model_size: str = "l"
    whisper_model_size: str = "large-v3"
    whisper_compute_type: str = "float16"
    face_min_confidence: float = 0.6
    face_min_size: int = 40
    face_include_demographics: bool = False

    # ── Scheduler (Skadi) ──
    balder_api_url: str = "http://localhost:5001/api"
    postgres_connection_string: str = ""
    postgres_main_connection_string: str = ""
    scheduler_enabled: bool = True

    # ── People Data Labs (PDL) ──
    pdl_api_key: str = ""

    # ── OSINT API Keys ──
    twitter_bearer_token: str = ""
    instagram_access_token: str = ""
    telegram_api_id: str = ""
    telegram_api_hash: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "Vulcan OSINT Bot 1.0"
    numverify_api_key: str = ""
    hunter_api_key: str = ""
    hibp_api_key: str = ""

    # ── Proxy Rotation ──
    proxy_enabled: bool = True
    proxy_list: str = ""  # comma-separated: socks5://host:port,http://user:pass@host:port
    brightdata_proxy_url: str = ""  # e.g. http://user:pass@brd.superproxy.io:22225
    residential_proxy_url: str = ""  # residential proxy for WAF-protected sites (REPUVE, etc.)

    # ── CAPTCHA Solving ──
    captcha_api_key: str = ""  # 2captcha.com API key for reCAPTCHA solving
    captcha_service: str = "2captcha"  # "2captcha" or "anti-captcha"

    # ── Google Search / Captures ──
    captures_dir: str = "/app/captures"
    max_google_captures: int = 5

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()

# ── Logging ──
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("vulcan.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("vulcan")
