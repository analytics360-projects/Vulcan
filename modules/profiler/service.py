"""Profiler service — behavioral profiling from MIA detection data."""
import hashlib
import json
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import List, Dict, Optional

from config import settings, logger
from modules.profiler.models import (
    ProfileRequest, ProfileResponse,
    EmotionPattern, FrequentObject, ActivityWindow, BehavioralFlag,
    CompareProfilesRequest, CompareProfilesResponse,
)


def _custody_hash(user: str, modulo: str, accion: str, params: dict) -> str:
    payload = f"{user}|{modulo}|{accion}|{json.dumps(params, sort_keys=True)}|{datetime.now(timezone.utc).isoformat()}"
    return hashlib.sha256(payload.encode()).hexdigest()


# Object labels that trigger flags
FLAG_WEAPONS = {"gun", "rifle", "weapon", "knife", "pistol", "firearm", "sword"}
FLAG_DRUGS = {"drug", "pill", "syringe", "marijuana", "cocaine", "substance"}


class ProfilerService:
    """Generate behavioral profiles from MIA detection data."""

    def _get_detections(self, persona_id: str) -> list:
        """Fetch MIA detections from RavenDB."""
        try:
            from modules.sans.ravendb_client import get_store
            store = get_store()
            with store.open_session() as session:
                # Query all MIA results linked to this persona
                results = list(session.query_collection("mia_results"))
                filtered = [r for r in results
                           if str(getattr(r, 'persona_id', '')) == persona_id
                           or str(getattr(r, 'evidenciaCarpetaId', '')) == persona_id]
                return filtered
        except Exception as e:
            logger.warning(f"Failed to fetch MIA detections: {e}")
            return []

    def generate(self, req: ProfileRequest) -> ProfileResponse:
        """Generate behavioral profile from aggregated MIA data."""
        detections = self._get_detections(req.persona_id)
        total = len(detections) if detections else 0

        emotion_counts: Dict[str, int] = defaultdict(int)
        label_frequency: Dict[str, int] = defaultdict(int)
        co_occurrences: Dict[str, int] = defaultdict(int)
        timestamps: List[datetime] = []

        for det in detections:
            det_dict = det.__dict__ if hasattr(det, '__dict__') else det
            result = det_dict.get('result', {})
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except Exception:
                    result = {}

            # Emotions from DetectFaces
            for face in result.get("FaceDetails", []):
                for emotion in face.get("Emotions", []):
                    if emotion.get("Confidence", 0) > 70:
                        emotion_counts[emotion.get("Type", "UNKNOWN")] += 1

            # Labels
            for label in result.get("Labels", []):
                if label.get("Confidence", 0) > 75:
                    label_frequency[label.get("Name", "")] += 1

            # Timestamps
            ts = det_dict.get("created_at") or det_dict.get("timestamp")
            if ts:
                try:
                    if isinstance(ts, str):
                        timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
                    elif isinstance(ts, datetime):
                        timestamps.append(ts)
                except Exception:
                    pass

        denominator = max(total, 1)

        # Emotion patterns
        emotion_pattern = [
            EmotionPattern(emotion=k, percentage=round(v / denominator * 100, 1))
            for k, v in sorted(emotion_counts.items(), key=lambda x: -x[1])
        ]

        # Frequent objects (>20% of images)
        frequent_objects = [
            FrequentObject(label=k, frecuencia_pct=round(v / denominator * 100, 1))
            for k, v in sorted(label_frequency.items(), key=lambda x: -x[1])
            if v / denominator > 0.20
        ]

        # Activity windows
        hour_counts = Counter(ts.hour for ts in timestamps) if timestamps else {}
        avg_count = sum(hour_counts.values()) / 24 if hour_counts else 0
        activity_windows = []
        if hour_counts:
            active_hours = sorted([h for h, c in hour_counts.items() if c > avg_count])
            if active_hours:
                # Group consecutive hours
                start = active_hours[0]
                prev = start
                for h in active_hours[1:]:
                    if h != prev + 1:
                        freq = sum(hour_counts.get(i, 0) for i in range(start, prev + 1)) / denominator * 100
                        activity_windows.append(ActivityWindow(
                            hora_inicio=start, hora_fin=prev, frecuencia_pct=round(freq, 1),
                        ))
                        start = h
                    prev = h
                freq = sum(hour_counts.get(i, 0) for i in range(start, prev + 1)) / denominator * 100
                activity_windows.append(ActivityWindow(
                    hora_inicio=start, hora_fin=prev, frecuencia_pct=round(freq, 1),
                ))

        # Flags
        flags: List[BehavioralFlag] = []
        label_names_lower = {k.lower() for k in label_frequency.keys()}

        weapon_matches = FLAG_WEAPONS & label_names_lower
        if weapon_matches:
            max_pct = max(label_frequency.get(w, 0) / denominator for w in label_frequency if w.lower() in FLAG_WEAPONS)
            if max_pct > 0.40:
                flags.append(BehavioralFlag(
                    tipo="ARMA",
                    descripcion=f"Armas detectadas en >{int(max_pct*100)}% de las imágenes: {', '.join(weapon_matches)}",
                    confianza=min(1.0, max_pct + 0.1),
                ))

        drug_matches = FLAG_DRUGS & label_names_lower
        if drug_matches:
            max_pct = max(label_frequency.get(d, 0) / denominator for d in label_frequency if d.lower() in FLAG_DRUGS)
            if max_pct > 0.30:
                flags.append(BehavioralFlag(
                    tipo="DROGA",
                    descripcion=f"Sustancias detectadas en >{int(max_pct*100)}% de las imágenes",
                    confianza=min(1.0, max_pct + 0.1),
                ))

        # Nocturnal activity flag
        if timestamps:
            nocturnal = sum(1 for ts in timestamps if ts.hour >= 22 or ts.hour < 5)
            if nocturnal / denominator > 0.60:
                flags.append(BehavioralFlag(
                    tipo="NOCTURNO",
                    descripcion=f">{int(nocturnal/denominator*100)}% de actividad entre 22:00-05:00",
                    confianza=nocturnal / denominator,
                ))

        # Generate narrative with LLM (only if sufficient data)
        narrative = "Datos insuficientes para generar perfil conductual."
        if total >= 5:
            narrative = self._generate_narrative(
                total, emotion_pattern, frequent_objects[:10], activity_windows,
            )

        h = _custody_hash(req.user, "PROFILER", "Generate", {
            "persona_id": req.persona_id, "detections": total,
        })

        return ProfileResponse(
            persona_id=req.persona_id,
            total_detections=total,
            emotion_pattern=emotion_pattern,
            frequent_objects=frequent_objects,
            activity_windows=activity_windows,
            flags=flags,
            narrative=narrative,
            co_occurrences=[],
            hash_custodia=h,
        )

    async def generate_async(self, payload: dict) -> dict:
        """Queue-compatible wrapper."""
        req = ProfileRequest(
            persona_id=payload.get("persona_id", ""),
            carpeta_id=payload.get("carpeta_id"),
        )
        result = self.generate(req)
        return result.model_dump()

    def _generate_narrative(self, total, emotions, objects, windows) -> str:
        """Generate behavioral narrative using Ollama (sync, small model)."""
        try:
            import httpx
            import os
            ollama_base = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
            model = os.getenv("OLLAMA_MODEL_SMALL", "gemma3:4b")

            context = (
                f"Total de imágenes analizadas: {total}\n"
                f"Emociones predominantes: {json.dumps([e.model_dump() for e in emotions[:5]], ensure_ascii=False)}\n"
                f"Objetos frecuentes (>20%): {json.dumps([o.model_dump() for o in objects], ensure_ascii=False)}\n"
                f"Ventanas de actividad: {json.dumps([w.model_dump() for w in windows], ensure_ascii=False)}\n"
            )

            response = httpx.post(
                f"{ollama_base}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "Eres un analista forense. Genera un perfil conductual objetivo y factual basado en datos de análisis de imagen. Sé conciso, 3-4 oraciones."},
                        {"role": "user", "content": f"Genera un perfil conductual basado en estos datos:\n{context}"},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.1},
                },
                timeout=60.0,
            )
            response.raise_for_status()
            return response.json()["message"]["content"]
        except Exception as e:
            logger.warning(f"Profile narrative generation failed: {e}")
            return f"Perfil basado en {total} detecciones. Generación de narrativa no disponible."


profiler_service = ProfilerService()
