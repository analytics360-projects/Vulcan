"""News models — moved from models/news.py"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class NewsArticle(BaseModel):
    title: str
    source: str
    url: str
    google_url: Optional[str] = None
    domain: Optional[str] = None
    published: str
    summary: str = ""
    article_content: Optional[str] = None
    image_url: Optional[str] = None
    analysis: Optional[Dict[str, Any]] = Field(default={})
    authorized: Optional[bool] = Field(False)


class NewsArticleWithAnalysis(NewsArticle):
    analysis: Dict[str, Any] = Field(default={})


class NewsSearchResults(BaseModel):
    query: str
    language: str
    country: str
    results: List[NewsArticle] = []
    count: int = 0
    include_content: bool = False
    percentage: float = 0
    authorized: Optional[bool] = Field(False)


class NewsSearchResultsWithAnalysis(BaseModel):
    query: str
    language: str
    country: str
    results: List[NewsArticleWithAnalysis] = []
    count: int = 0
    include_content: bool = False
    percentage: float = 0
    authorized: Optional[bool] = Field(False)
