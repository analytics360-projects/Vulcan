"""Community detection — graph analysis models."""
from datetime import datetime
from typing import List, Optional, Dict, Literal
from pydantic import BaseModel


class GraphNode(BaseModel):
    id: str
    tipo: str = "PERSONA"  # PERSONA, VEHICULO, LUGAR, ORGANIZACIÓN, TELEFONO, EVENTO
    label: str
    metadata: Dict = {}


class GraphEdge(BaseModel):
    source: str
    target: str
    tipo_relacion: str = "relacion"
    peso: float = 1.0
    fuente_evidencia: Optional[str] = None
    fecha: Optional[str] = None


class DetectCommunitiesRequest(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    carpeta_id: Optional[str] = None
    resolution: float = 1.0
    min_community_size: int = 2
    user: str = ""


class NodeMetrics(BaseModel):
    node_id: str
    label: str
    tipo: str
    degree: int
    betweenness: float
    closeness: float
    rol: str  # LIDER, BROKER, MIEMBRO, PERIFERICO
    community_id: int
    prioridad_investigativa: int  # 1=highest


class CommunityResult(BaseModel):
    community_id: int
    nodos: List[str]
    tamano: int
    densidad_interna: float


class DetectCommunitiesResponse(BaseModel):
    communities: List[CommunityResult]
    node_metrics: List[NodeMetrics]
    top_actors: List[NodeMetrics]  # top 5 by betweenness
    vis_network_data: Dict  # vis.js/vis-network compatible
    hash_custodia: str = ""


class IntelligenceReportRequest(BaseModel):
    carpeta_id: str
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    user: str = ""


class IntelligenceReportResponse(BaseModel):
    reporte: str
    comunidades_detectadas: int
    actores_clave: List[str]
    hash_custodia: str = ""
