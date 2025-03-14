from typing import List, Dict, Any, Optional
from enum import Enum
from pydantic import BaseModel, Field

# Facebook reaction types
class ReactionType(str, Enum):
    LIKE = "like"
    LOVE = "love"
    HAHA = "haha"
    WOW = "wow"
    SAD = "sad"
    ANGRY = "angry"
    CARE = "care"


class Reaction(BaseModel):
    """Model for a Facebook reaction"""
    type: ReactionType
    count: int


class Comment(BaseModel):
    """Model for a Facebook comment"""
    text: str
    author: str
    timestamp: Optional[str] = None
    reactions: List[Reaction] = []
    likes_count: int = 0
    replies: Optional[List["Comment"]] = []
    url: Optional[str] = None


# Required for self-referencing models
Comment.update_forward_refs()


class Post(BaseModel):
    """Model for a Facebook post"""
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
    authorized: Optional[bool] = Field(False, description="Authorization of result")


class GroupAnalysis(BaseModel):
    """Model for a Facebook group analysis"""
    group_name: str
    group_id: str
    group_url: str
    members_count: Optional[int] = None
    posts: List[Post] = []
    top_comments: List[Comment] = []
    reaction_stats: Dict[str, int] = {}
    most_active_members: List[Dict[str, Any]] = []