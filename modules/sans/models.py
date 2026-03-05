"""SANS models — ported from Hades Pydantic models"""
from pydantic import BaseModel
from typing import List, Optional


class Item(BaseModel):
    full_path: str
    user: str
    nombre: str
    carpeta_investigacion: str
    investigacion: str
    tipo_busqueda: str
    status: int
    palabras: list


class ItemMultiUrl(BaseModel):
    urls: list
    user: str
    nombre: str
    carpeta_investigacion: str
    investigacion: str
    tipo_busqueda: str
    status: int
    palabras: list


class Carpeta(BaseModel):
    carpeta_investigacion: str
    user: str


class Investigacion(BaseModel):
    nombre: str
    carpeta_investigacion: int
    user: str


class CarpetaInvestigacion(BaseModel):
    investigacion_id: str
    resultado_id: str


class CarpetaInvestigacionCollectionById(BaseModel):
    carpetaId: str


class UbicacionRequest(BaseModel):
    investigacion_id: str
    latitud: float
    longitud: float
    resultado_id: str
    carpeta_id: str


class GrupoInvestigacion(BaseModel):
    investigacion_id: str
    grupo: str
    palabra: str
    carpeta_id: str
