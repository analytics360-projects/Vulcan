#!/bin/bash

# Build the Docker image
docker build -t web-scraper-api .

# Run the container
docker run -d -p 8000:8000 --name web-scraper-container web-scraper-api

echo "Web Scraper API is running on http://localhost:8000"
echo "API documentation available at http://localhost:8000/docs"