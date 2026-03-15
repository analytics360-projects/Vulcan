"""Speech-to-Text — Pydantic models (base + forensic STT)."""
from typing import List, Optional
from pydantic import BaseModel


# ── Base models ──

class TranscriptionSegment(BaseModel):
    start: float
    end: float
    text: str
    confidence: float


class TranscriptionResult(BaseModel):
    text: str
    language: str
    segments: List[TranscriptionSegment]
    duration: float


class NerEntity(BaseModel):
    text: str
    tipo: str
    start: int
    end: int


class SentimentResult(BaseModel):
    sentimiento: str
    score: float
    nivel_estres: str


class AnalysisResult(BaseModel):
    transcription: TranscriptionResult
    entities: List[NerEntity]
    sentiment: SentimentResult


class SynthesizeRequest(BaseModel):
    text: str
    lang: str = "es"


# ── Forensic STT models ──

class TranscriptSegment(BaseModel):
    hablante: str  # HABLANTE_1, HABLANTE_2...
    inicio_ms: int
    fin_ms: int
    texto: str
    confianza: float


class KeywordDetected(BaseModel):
    keyword: str
    timestamp_ms: int
    hablante: str
    contexto: str  # ±30 chars around keyword


class ForensicTranscriptionResult(BaseModel):
    transcript_id: str
    texto_completo: str  # with [HABLANTE_X HH:MM:SS] labels
    segmentos: List[TranscriptSegment]
    keywords_detectados: List[KeywordDetected]
    metadata: dict  # duracion_ms, num_hablantes, idioma_detectado, calidad_audio
    hashes: dict  # audio_sha256, transcripcion_sha256, timestamp
    evidencia_id: Optional[str] = None
    hash_custodia: str = ""


class TranscribeRequest(BaseModel):
    origen: str = "otro"  # 911_call, bodycam, entrevista, whatsapp, radio_policial, llamada_carcel
    folio_id: Optional[str] = None
    carpeta_id: Optional[str] = None
    keywords_alerta: List[str] = []
    idioma: str = "es"
    user: str = ""


class SttSearchRequest(BaseModel):
    query: str
    carpeta_id: Optional[str] = None
    limit: int = 20


class SttSearchResult(BaseModel):
    transcript_id: str
    texto_match: str
    hablante: str
    timestamp_ms: int
    score: float
