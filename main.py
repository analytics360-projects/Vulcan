from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import (
    APP_NAME, APP_VERSION, APP_DESCRIPTION, logger
)
from routers import marketplace_router, group_router, news_router

# Create FastAPI application
app = FastAPI(
    title=APP_NAME,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Set specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add routers
app.include_router(marketplace_router)
app.include_router(group_router)
app.include_router(news_router)


# Root endpoint
@app.get("/")
async def read_root():
    """API root that provides documentation links."""
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "description": APP_DESCRIPTION,
        "docs_url": "/docs",
        "redoc_url": "/redoc"
    }


# Health check endpoint
@app.get("/health")
async def health_check():
    """Check if the API is up and running."""
    from datetime import datetime
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# Run the application
if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")
    uvicorn.run("facebook_scraper.main:app", host="0.0.0.0", port=8000, reload=True)