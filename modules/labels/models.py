"""Label Taxonomy & Synonym models"""
from typing import Optional, List
from pydantic import BaseModel


class LabelNode(BaseModel):
    name: str
    parent: Optional[str] = None
    children: List[str] = []
    synonyms: List[str] = []


class TaxonomyResponse(BaseModel):
    tree: List[LabelNode]


class SynonymMap(BaseModel):
    label: str
    synonyms: List[str]
    category: str


class ResolveRequest(BaseModel):
    labels: List[str]


class ResolvedLabel(BaseModel):
    original: str
    spanish: str
    category: str
    hierarchy: List[str]  # e.g. ["Vehiculo", "Auto", "Sedan"]


class ResolveResponse(BaseModel):
    resolved: List[ResolvedLabel]
