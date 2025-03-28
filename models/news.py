from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class NewsArticle(BaseModel):
    """Model for a news article"""
    title: str = Field(..., description="Title of the article")
    source: str = Field(..., description="Source/publisher of the article")
    url: str = Field(..., description="Original URL of the article")
    google_url: Optional[str] = Field(None, description="Google News redirect URL")
    domain: Optional[str] = Field(None, description="Domain of the article URL")
    published: str = Field(..., description="Publication date/time")
    summary: str = Field("", description="Brief summary or snippet from the article")
    article_content: Optional[str] = Field(None, description="Full article content")
    image_url: Optional[str] = Field(None, description="URL of the main article image")
    analysis: Optional[Dict[str, Any]] = Field(default={}, description="LLM analysis results")
    authorized: Optional[bool] = Field(False, description="Authorization of result")

class NewsArticleWithAnalysis(NewsArticle):
    """Model for a news article with analysis"""
    analysis: Dict[str, Any] = Field(default={}, description="LLM analysis results")


class NewsSearchResults(BaseModel):
    """Model for news search results"""
    query: str = Field(..., description="Search query")
    language: str = Field(..., description="Language code")
    country: str = Field(..., description="Country code")
    results: List[NewsArticle] = Field([], description="List of articles found")
    count: int = Field(0, description="Number of articles found")
    include_content: bool = Field(False, description="Whether article content is included")
    percentage: float = Field(0, description="Percentage of articles with content found")
    authorized: Optional[bool] = Field(False, description="Authorization of result")


class NewsSearchResultsWithAnalysis(BaseModel):
    """Model for news search results with analysis"""
    query: str = Field(..., description="Search query")
    language: str = Field(..., description="Language code")
    country: str = Field(..., description="Country code")
    results: List[NewsArticleWithAnalysis] = Field([], description="List of articles found with analysis")
    count: int = Field(0, description="Number of articles found")
    include_content: bool = Field(False, description="Whether article content is included")
    percentage: float = Field(0, description="Percentage of articles with content found")
    authorized: Optional[bool] = Field(False, description="Authorization of result")