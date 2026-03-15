"""Social Graph models — G3 Redes de Vínculos Sociales"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class SocialGraphNode(BaseModel):
    id: str
    label: str
    type: str = Field(description="profile | page | group | post")
    platform: str
    url: Optional[str] = None
    metadata: Dict[str, Any] = {}


class SocialGraphEdge(BaseModel):
    source: str
    target: str
    relation: str = Field(description="interacts | comments | reacts | member_of | mentioned")
    weight: float = 1.0


class ProfilePost(BaseModel):
    text: str = ""
    reactions: int = 0
    comments: int = 0
    shares: int = 0
    author: Optional[str] = None
    timestamp: Optional[str] = None


class ProfileInput(BaseModel):
    name: str
    platform: str
    url: Optional[str] = None
    posts: List[ProfilePost] = []


class BuildGraphRequest(BaseModel):
    profiles: List[ProfileInput]


class BuildGraphResponse(BaseModel):
    nodes: List[SocialGraphNode]
    edges: List[SocialGraphEdge]
    communities: int = 0
