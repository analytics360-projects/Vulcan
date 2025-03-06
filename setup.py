from setuptools import setup, find_packages

setup(
    name="web-scraper-api",
    version="2.0.0",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.95.0",
        "uvicorn>=0.21.1",
        "selenium>=4.8.3",
        "beautifulsoup4>=4.12.0",
        "webdriver-manager>=3.8.5",
        "pandas>=1.5.3",
        "requests>=2.28.2",
        "feedparser>=6.0.10",
        "pydantic>=1.10.7",
    ],
    author="Your Name",
    author_email="your.email@example.com",
    description="API for scraping web content including Facebook Marketplace, Groups, and News Articles",
    keywords="scraper, facebook, marketplace, groups, news, api",
    python_requires=">=3.8",
)