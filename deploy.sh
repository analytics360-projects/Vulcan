#!/bin/bash

# Build the Docker image
docker build -t web-scraper-api .

# Run the container
docker run -d \
  --network host \
  --name web-scraper-container \
  --env LLM_API_URL=http://10.19.5.55:11434/api/generate \
  --env LLM_MODEL=deepseek-r1:14b \
  --env LLM_TIMEOUT=6000 \
  --env DEFAULT_TIMEOUT=6000 \
  web-scraper-api

echo "Web Scraper API is running on http://localhost:8000"
echo "API documentation available at http://localhost:8000/docs"