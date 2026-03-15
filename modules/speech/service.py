"""Speech-to-Text — Service (base Whisper + forensic STT with diarization)."""
import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from config import settings, logger
from modules.speech.models import (
    TranscriptionSegment, TranscriptionResult,
    NerEntity, SentimentResult, AnalysisResult,
    TranscriptSegment, KeywordDetected, ForensicTranscriptionResult,
)

# ── Whisper lazy-load ──
_whisper = None
_whisper_model = None
_whisper_available = False


def _load_whisper():
    global _whisper, _whisper_model, _whisper_available
    if _whisper_model is not None:
        return
    try:
        import whisper
        _whisper = whisper
        model_name = getattr(settings, "whisper_model_size", "base")
        logger.info(f"Loading whisper model: {model_name}")
        _whisper_model = whisper.load_model(model_name)
        _whisper_available = True
        logger.info(f"Whisper model '{model_name}' loaded")
    except ImportError:
        logger.warning("openai-whisper not installed — speech module will return errors")
        _whisper_available = False
    except Exception as e:
        logger.error(f"Failed to load whisper model: {e}")
        _whisper_available = False


# ── NER regex patterns (Spanish) ──
_PERSONA_PATTERN = re.compile(
    r"(?:señor|señora|don|doña|ciudadano|ciudadana|el\s+(?:señor|ciudadano)|la\s+(?:señora|ciudadana))"
    r"\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,3})", re.UNICODE)
_LUGAR_PATTERN = re.compile(
    r"(?:calle|avenida|colonia|boulevard|privada|fraccionamiento|en|hacia|por)"
    r"\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ0-9]+){0,4})", re.UNICODE)
_VEHICULO_PATTERN = re.compile(
    r"(?:vehículo|vehiculo|carro|camioneta|automóvil|auto|motocicleta|moto|taxi|camión)"
    r"\s+((?:color\s+)?[a-záéíóúñA-ZÁÉÍÓÚÑ]+(?:\s+[a-záéíóúñA-ZÁÉÍÓÚÑ]+){0,3})", re.UNICODE | re.IGNORECASE)
_PLACA_PATTERN = re.compile(r"\b([A-Z]{2,3}[-\s]?\d{2,4}[-\s]?[A-Z]{0,3})\b")
_FECHA_PATTERN = re.compile(
    r"\b(\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)"
    r"(?:\s+(?:del?\s+)?\d{4})?)\b", re.IGNORECASE)

# ── Sentiment word lists ──
_NEGATIVE_WORDS = {
    "amenaza", "amenazas", "amenazó", "peligro", "peligroso", "herido", "herida",
    "muerto", "muerta", "arma", "armas", "sangre", "disparo", "disparos",
    "golpe", "golpes", "violencia", "violento", "secuestro", "secuestrado",
    "robo", "asalto", "homicidio", "asesinato", "droga", "drogas",
    "extorsión", "desaparecido", "cadáver", "víctima", "emergencia", "grave",
    "miedo", "terror", "pánico", "grito", "gritos", "persecución",
    "choque", "accidente", "lesión", "lesiones",
}
_POSITIVE_WORDS = {
    "bien", "seguro", "segura", "tranquilo", "tranquila", "normal", "estable",
    "controlado", "resuelto", "recuperado", "sano", "gracias", "ayuda", "rescate",
}

# Default forensic keywords
DEFAULT_KEYWORDS = [
    "disparo", "arma", "muerto", "herido", "secuestro",
    "droga", "amenaza", "violencia", "ayuda", "sangre",
]


def _custody_hash(user: str, modulo: str, accion: str, params: dict) -> str:
    payload = f"{user}|{modulo}|{accion}|{json.dumps(params, sort_keys=True)}|{datetime.now(timezone.utc).isoformat()}"
    return hashlib.sha256(payload.encode()).hexdigest()


class SpeechService:
    """Base speech-to-text using OpenAI Whisper."""

    def __init__(self):
        self._initialized = False

    def _ensure_model(self):
        if not self._initialized:
            _load_whisper()
            self._initialized = True
        if not _whisper_available:
            raise RuntimeError("openai-whisper not installed or model failed to load")

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        self._ensure_model()
        result = _whisper_model.transcribe(audio_path, language="es", verbose=False)
        segments = []
        for seg in result.get("segments", []):
            segments.append(TranscriptionSegment(
                start=round(seg["start"], 2), end=round(seg["end"], 2),
                text=seg["text"].strip(),
                confidence=round(1.0 - seg.get("no_speech_prob", 0.0), 4),
            ))
        full_text = result.get("text", "").strip()
        duration = segments[-1].end if segments else 0.0
        return TranscriptionResult(
            text=full_text, language=result.get("language", "es"),
            segments=segments, duration=round(duration, 2),
        )

    def _extract_entities(self, text: str) -> List[NerEntity]:
        entities, seen = [], set()
        patterns = [
            (_PERSONA_PATTERN, "persona"), (_LUGAR_PATTERN, "lugar"),
            (_VEHICULO_PATTERN, "vehiculo"), (_PLACA_PATTERN, "vehiculo"),
            (_FECHA_PATTERN, "fecha"),
        ]
        for pattern, tipo in patterns:
            for match in pattern.finditer(text):
                entity_text = match.group(1).strip()
                if not entity_text or len(entity_text) < 2:
                    continue
                key = (entity_text.lower(), tipo)
                if key in seen:
                    continue
                seen.add(key)
                entities.append(NerEntity(
                    text=entity_text, tipo=tipo,
                    start=match.start(1), end=match.end(1),
                ))
        return entities

    def _analyze_sentiment(self, text: str) -> SentimentResult:
        words = re.findall(r"[a-záéíóúñü]+", text.lower())
        total = len(words) if words else 1
        neg_count = sum(1 for w in words if w in _NEGATIVE_WORDS)
        pos_count = sum(1 for w in words if w in _POSITIVE_WORDS)
        neg_ratio, pos_ratio = neg_count / total, pos_count / total
        if neg_ratio > 0.05:
            sentimiento, score = "negativo", min(1.0, neg_ratio * 10)
        elif pos_ratio > neg_ratio:
            sentimiento, score = "positivo", min(1.0, pos_ratio * 10)
        else:
            sentimiento, score = "neutral", 0.5
        if neg_ratio > 0.10: nivel = "critico"
        elif neg_ratio > 0.05: nivel = "alto"
        elif neg_ratio > 0.02: nivel = "medio"
        else: nivel = "bajo"
        return SentimentResult(sentimiento=sentimiento, score=round(score, 4), nivel_estres=nivel)

    def analyze(self, audio_path: str) -> AnalysisResult:
        transcription = self.transcribe(audio_path)
        return AnalysisResult(
            transcription=transcription,
            entities=self._extract_entities(transcription.text),
            sentiment=self._analyze_sentiment(transcription.text),
        )

    def synthesize(self, text: str, lang: str = "es") -> bytes:
        try:
            from gtts import gTTS
        except ImportError:
            raise RuntimeError("gTTS not installed")
        import tempfile
        tts = gTTS(text=text, lang=lang, slow=False)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            tmp_path = tmp.name
            tts.save(tmp_path)
        with open(tmp_path, "rb") as f:
            audio_bytes = f.read()
        os.unlink(tmp_path)
        return audio_bytes


class ForensicSpeechService:
    """Forensic STT with diarization, keyword detection, hash chain, and NER enqueue."""

    def __init__(self):
        self._base = None

    def _get_base(self):
        if self._base is None:
            self._base = speech_service
        return self._base

    def _compute_file_hash(self, file_path: str) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _diarize(self, segments: List[TranscriptionSegment]) -> List[TranscriptSegment]:
        """Speaker diarization by silence gaps (>0.5s = potential speaker change)."""
        diarized = []
        current_speaker = "HABLANTE_1"
        speaker_idx = 0

        for i, seg in enumerate(segments):
            if i > 0:
                gap = seg.start - segments[i - 1].end
                if gap > 0.5:
                    speaker_idx = (speaker_idx + 1) % 10
                    current_speaker = f"HABLANTE_{speaker_idx + 1}"

            diarized.append(TranscriptSegment(
                hablante=current_speaker,
                inicio_ms=int(seg.start * 1000),
                fin_ms=int(seg.end * 1000),
                texto=seg.text,
                confianza=seg.confidence,
            ))
        return diarized

    def _format_text(self, diarized: List[TranscriptSegment]) -> str:
        """Format text with [HABLANTE_X HH:MM:SS] labels."""
        lines = []
        current_speaker = None
        for seg in diarized:
            if seg.hablante != current_speaker:
                current_speaker = seg.hablante
                secs = seg.inicio_ms / 1000
                h, m, s = int(secs // 3600), int((secs % 3600) // 60), int(secs % 60)
                lines.append(f"\n[{current_speaker} {h:02d}:{m:02d}:{s:02d}] {seg.texto}")
            else:
                lines.append(seg.texto)
        return " ".join(lines).strip()

    def _detect_keywords(self, diarized: List[TranscriptSegment],
                          keywords: List[str]) -> List[KeywordDetected]:
        """Find keyword matches with context."""
        matches = []
        for seg in diarized:
            text_lower = seg.texto.lower()
            for kw in keywords:
                if kw.lower() in text_lower:
                    # Context: ±30 chars
                    idx = text_lower.find(kw.lower())
                    ctx_start = max(0, idx - 30)
                    ctx_end = min(len(seg.texto), idx + len(kw) + 30)
                    matches.append(KeywordDetected(
                        keyword=kw,
                        timestamp_ms=seg.inicio_ms,
                        hablante=seg.hablante,
                        contexto=seg.texto[ctx_start:ctx_end],
                    ))
        return matches

    def transcribe_forensic(self, audio_path: str, origen: str = "otro",
                             folio_id: str = None, carpeta_id: str = None,
                             keywords_alerta: List[str] = None,
                             idioma: str = "es", user: str = "") -> ForensicTranscriptionResult:
        """Full forensic transcription pipeline."""
        base = self._get_base()

        # 1. Audio hash BEFORE processing
        audio_hash = self._compute_file_hash(audio_path)

        # 2. Transcribe with Whisper
        base_result = base.transcribe(audio_path)

        # 3. Diarization
        diarized = self._diarize(base_result.segments)
        num_speakers = len(set(s.hablante for s in diarized))

        # 4. Format text
        texto_completo = self._format_text(diarized)

        # 5. Keyword detection
        all_keywords = DEFAULT_KEYWORDS + (keywords_alerta or [])
        kw_detected = self._detect_keywords(diarized, all_keywords)

        # 6. Text hash
        text_hash = hashlib.sha256(texto_completo.encode()).hexdigest()

        # 7. Generate transcript ID
        transcript_id = str(uuid.uuid4())

        # 8. Custody hash
        h = _custody_hash(user, "STT", "Transcribe", {
            "origen": origen, "duracion_ms": int(base_result.duration * 1000),
            "num_hablantes": num_speakers,
            "keywords_detectados_count": len(kw_detected),
        })

        # 9. Enqueue NER on transcribed text
        if carpeta_id and texto_completo:
            try:
                from services.llm_queue_service import enqueue_llm_task
                enqueue_llm_task("ner", {
                    "texto": texto_completo,
                    "carpeta_id": carpeta_id,
                    "folio_id": folio_id,
                }, carpeta_id=carpeta_id, priority=8)
            except Exception as e:
                logger.warning(f"Failed to enqueue NER for STT result: {e}")

        # 10. Store in RavenDB
        self._store_transcript(transcript_id, audio_hash, text_hash, carpeta_id,
                                base_result.duration, num_speakers, len(kw_detected))

        return ForensicTranscriptionResult(
            transcript_id=transcript_id,
            texto_completo=texto_completo,
            segmentos=diarized,
            keywords_detectados=kw_detected,
            metadata={
                "duracion_ms": int(base_result.duration * 1000),
                "num_hablantes": num_speakers,
                "idioma_detectado": base_result.language,
                "origen": origen,
            },
            hashes={
                "audio_sha256": audio_hash,
                "transcripcion_sha256": text_hash,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            hash_custodia=h,
        )

    def transcribe_from_payload(self, payload: dict) -> dict:
        """Queue-compatible wrapper (downloads audio_url first)."""
        # For queue processing, audio would need to be downloaded first
        # This is a placeholder for the queue integration
        return {"status": "not_implemented_for_queue", "payload": payload}

    def _store_transcript(self, transcript_id, audio_hash, text_hash,
                           carpeta_id, duration, num_speakers, kw_count):
        try:
            from modules.sans.ravendb_client import get_store
            store = get_store()
            with store.open_session() as session:
                doc = {
                    "transcript_id": transcript_id,
                    "audio_hash": audio_hash,
                    "text_hash": text_hash,
                    "carpeta_id": carpeta_id,
                    "duration": duration,
                    "num_speakers": num_speakers,
                    "keywords_count": kw_count,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                session.store(doc, f"forensic_transcriptions/{transcript_id}")
                session.save_changes()
        except Exception as e:
            logger.warning(f"Failed to store transcript: {e}")


speech_service = SpeechService()
forensic_speech_service = ForensicSpeechService()
