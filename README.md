# Web Scraper API

An API for scraping web content including Facebook Marketplace listings, Facebook Groups, and News Articles.

## Features

### Marketplace Scraping
- Search for products with filters (city, price range, etc.)
- Extract product details (title, price, location, image, URL)
- Export results to CSV or JSON formats

### Facebook Group Analysis
- Analyze post engagement and reaction statistics
- Extract comments with author information
- Identify most active group members
- Find top comments by like count

### News Article Scraping
- Search for news articles via Google News RSS
- Extract article content and images
- Get trending news or news by topic
- Support for different languages and countries

## Installation

### Prerequisites
- Python 3.8+
- Chrome browser

### Setup

1. Clone the repository:
```
git clone https://github.com/analytics360-projects/Vulcan.git
cd Vulcan
```

2. Install required packages:
```
pip install -e .
```

3. Run the application:
```
python -m facebook_scraper.main
```

The API will be available at http://localhost:8000. Documentation is available at http://localhost:8000/docs.

## API Endpoints

### Marketplace

- `GET /marketplace/search` - Search for products on Marketplace
- `GET /marketplace/export/{format}` - Export search results (CSV or JSON)

### Facebook Groups

- `GET /group/{group_id}` - Analyze a Facebook Group
- `GET /group/{group_id}/top-comments` - Get top comments from a group
- `GET /group/{group_id}/reaction-stats` - Get reaction statistics
- `GET /group/{group_id}/active-members` - Get most active members
- `GET /group/{group_id}/search` - Search posts by keyword
- `GET /group/{group_id}/members/{member_name}` - Get member activity

### News

- `GET /news/search` - Search for news articles
- `GET /news/article` - Extract content from a specific article URL
- `GET /news/topic/{topic}` - Get news by topic
- `GET /news/trending` - Get trending news

## Usage Examples

### Search for News Articles

```bash
curl -X GET "http://localhost:8000/news/search?query=artificial%20intelligence&max_results=3&include_content=true"
```

### Get Article Content

```bash
curl -X GET "http://localhost:8000/news/article?url=https://example.com/article"
```

### Get Trending News

```bash
curl -X GET "http://localhost:8000/news/trending?language=en&country=US&max_results=5"
```

## Configuration

Configuration settings can be modified in `config.py`.