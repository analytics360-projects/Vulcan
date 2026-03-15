"""Speech-to-Text + TTS + Forensic STT — Router"""
import os
import io
import tempfile

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from config import logger
from modules.speech.models import (
    TranscriptionResult, AnalysisResult, SynthesizeRequest,
    ForensicTranscriptionResult,
)
from modules.speech.service import speech_service, forensic_speech_service

router = APIRouter(prefix="/speech", tags=["Speech"])


@router.post("/transcribe", response_model=TranscriptionResult)
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcribe audio to text with timestamps using Whisper."""
    tmp_path = None
    try:
        suffix = os.path.splitext(file.filename or "audio.wav")[1] or ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            tmp.write(await file.read())
        return speech_service.transcribe(tmp_path)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"Transcription error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/analyze", response_model=AnalysisResult)
async def analyze_audio(file: UploadFile = File(...)):
    """Full analysis: transcription + NER + sentiment."""
    tmp_path = None
    try:
        suffix = os.path.splitext(file.filename or "audio.wav")[1] or ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            tmp.write(await file.read())
        return speech_service.analyze(tmp_path)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"Analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/synthesize")
async def synthesize_speech(request: SynthesizeRequest):
    """Text to speech using gTTS."""
    try:
        audio_bytes = speech_service.synthesize(request.text, request.lang)
        return StreamingResponse(
            io.BytesIO(audio_bytes), media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=speech.mp3"},
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"Synthesis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/Transcribe", response_model=ForensicTranscriptionResult)
async def forensic_transcribe(
    file: UploadFile = File(...),
    origen: str = Form("otro"),
    folio_id: str = Form(None),
    carpeta_id: str = Form(None),
    keywords_alerta: str = Form(""),
    idioma: str = Form("es"),
    user: str = Form(""),
):
    """Forensic transcription with diarization, keywords, hash chain, and NER enqueue."""
    tmp_path = None
    try:
        suffix = os.path.splitext(file.filename or "audio.wav")[1] or ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            tmp.write(await file.read())

        kw_list = [k.strip() for k in keywords_alerta.split(",") if k.strip()] if keywords_alerta else []

        return forensic_speech_service.transcribe_forensic(
            tmp_path, origen=origen, folio_id=folio_id, carpeta_id=carpeta_id,
            keywords_alerta=kw_list, idioma=idioma, user=user,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"Forensic transcription error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.get("/Result/{transcript_id}")
async def get_transcript_result(transcript_id: str):
    """Get a stored forensic transcription result."""
    try:
        from modules.sans.ravendb_client import get_store
        store = get_store()
        with store.open_session() as session:
            doc = session.load(f"forensic_transcriptions/{transcript_id}")
            if not doc:
                raise HTTPException(status_code=404, detail="Transcript not found")
            return doc.__dict__ if hasattr(doc, '__dict__') else doc
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Get transcript error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ListByCarpeta/{carpeta_id}")
async def list_by_carpeta(carpeta_id: str):
    """List all forensic transcriptions for a carpeta."""
    try:
        from modules.sans.ravendb_client import get_store
        store = get_store()
        with store.open_session() as session:
            results = list(session.query_collection("forensic_transcriptions"))
            filtered = [r for r in results if getattr(r, 'carpeta_id', '') == carpeta_id]
            return [r.__dict__ if hasattr(r, '__dict__') else r for r in filtered]
    except Exception as e:
        logger.exception(f"List transcripts error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
