"""Group models — moved from models/group.py"""
from typing import List, Dict, Any, Optional
from enum import Enum
from pydantic import BaseModel, Field


class ReactionType(str, Enum):
    LIKE = "like"
    LOVE = "love"
    HAHA = "haha"
    WOW = "wow"
    SAD = "sad"
    ANGRY = "angry"
    CARE = "care"


class Reaction(BaseModel):
    type: ReactionType
    count: int


class Comment(BaseModel):
    text: str
    author: str
    timestamp: Optional[str] = None
    reactions: List[Reaction] = []
    likes_count: int = 0
    replies: Optional[List["Comment"]] = []
    url: Optional[str] = None


Comment.model_rebuild()


class Post(BaseModel):
    post_id: str
    author: str
    content: str
    timestamp: Optional[str] = None
    reactions: List[Reaction] = []
    comments: List[Comment] = []
    url: str
    image_url: Optional[str] = None
    likes_count: int = 0
    comments_count: int = 0
    authorized: Optional[bool] = Field(False)


class GroupAnalysis(BaseModel):
    group_name: str
    group_id: str
    group_url: str
    members_count: Optional[int] = None
    posts: List[Post] = []
    top_comments: List[Comment] = []
    reaction_stats: Dict[str, int] = {}
    most_active_members: List[Dict[str, Any]] = []
