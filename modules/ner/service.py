"""NER service — entity extraction using Ollama (gemma3:4b) with Mexican jargon."""
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from typing import List, Dict, Optional

from config import settings, logger
from modules.ner.models import (
    NerRequest, NerResponse, NerEntity, DeltaPreFill,
    ConfirmPreFillRequest, ConfirmPreFillResponse,
    UpdateJargonRequest, UpdateJargonResponse,
)

# ── Mexican law enforcement jargon ──
JERGA_MX: Dict[str, Dict[str, str]] = {
    "cuerno": {"canonical": "rifle de asalto", "tipo": "ARMA"},
    "cuerno de chivo": {"canonical": "AK-47", "tipo": "ARMA"},
    "fusca": {"canonical": "pistola", "tipo": "ARMA"},
    "fierro": {"canonical": "arma de fuego", "tipo": "ARMA"},
    "tuca": {"canonical": "arma corta", "tipo": "ARMA"},
    "plomo": {"canonical": "munición/disparo", "tipo": "ARMA"},
    "pastilla": {"canonical": "droga sintética", "tipo": "OBJETO"},
    "cristal": {"canonical": "metanfetamina", "tipo": "OBJETO"},
    "mota": {"canonical": "marihuana", "tipo": "OBJETO"},
    "piedra": {"canonical": "crack/cocaína base", "tipo": "OBJETO"},
    "pase": {"canonical": "dosis de cocaína", "tipo": "OBJETO"},
    "chiva": {"canonical": "heroína", "tipo": "OBJETO"},
    "perico": {"canonical": "cocaína", "tipo": "OBJETO"},
    "caro": {"canonical": "vehículo de lujo", "tipo": "VEHICULO"},
    "trocón": {"canonical": "pickup grande", "tipo": "VEHICULO"},
    "plaza": {"canonical": "territorio criminal", "tipo": "LUGAR"},
    "levantón": {"canonical": "secuestro express", "tipo": "OBJETO"},
    "encajuelado": {"canonical": "cadáver en cajuela", "tipo": "OBJETO"},
    "halcón": {"canonical": "vigía del crimen organizado", "tipo": "PERSONA"},
    "tiendita": {"canonical": "punto de venta de droga", "tipo": "LUGAR"},
    "sicario": {"canonical": "asesino a sueldo", "tipo": "PERSONA"},
    "narcomanta": {"canonical": "mensaje amenazante del crimen organizado", "tipo": "OBJETO"},
}

# Entity type → HTML color
ENTITY_COLORS = {
    "PERSONA": "#3B82F6",
    "VEHICULO": "#10B981",
    "ARMA": "#EF4444",
    "LUGAR": "#F59E0B",
    "FECHA_HORA": "#8B5CF6",
    "MONTO": "#F97316",
    "ORGANIZACIÓN": "#8B5CF6",
    "OBJETO": "#6B7280",
}

# NER schema for Ollama structured output
NER_SCHEMA = {
    "type": "object",
    "required": ["personas", "vehiculos", "armas", "lugares", "fechas", "montos", "organizaciones", "objetos"],
    "properties": {
        "personas": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["nombre", "rol"],
                "properties": {
                    "nombre": {"type": "string"},
                    "rol": {"type": "string", "enum": ["victima", "sospechoso", "testigo", "oficial", "desconocido"]},
                    "descripcion_fisica": {"type": "string"},
                    "edad_aproximada": {"type": "string"},
                    "apodo": {"type": "string"},
                },
            },
        },
        "vehiculos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tipo": {"type": "string"}, "color": {"type": "string"},
                    "placa": {"type": "string"}, "marca": {"type": "string"},
                    "modelo": {"type": "string"},
                },
            },
        },
        "armas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tipo": {"type": "string"}, "calibre": {"type": "string"},
                    "descripcion": {"type": "string"},
                },
            },
        },
        "lugares": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "descripcion": {"type": "string"},
                    "tipo": {"type": "string", "enum": ["domicilio", "calle", "negocio", "parque", "otro"]},
                    "colonia": {"type": "string"}, "municipio": {"type": "string"},
                },
            },
        },
        "fechas": {"type": "array", "items": {"type": "string"}},
        "montos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "valor": {"type": "number"},
                    "moneda": {"type": "string", "enum": ["MXN", "USD", "EUR", "desconocido"]},
                },
            },
        },
        "organizaciones": {"type": "array", "items": {"type": "string"}},
        "objetos": {"type": "array", "items": {"type": "string"}},
    },
}


def _custody_hash(user: str, modulo: str, accion: str, params: dict) -> str:
    payload = f"{user}|{modulo}|{accion}|{json.dumps(params, sort_keys=True)}|{datetime.now(timezone.utc).isoformat()}"
    return hashlib.sha256(payload.encode()).hexdigest()


class NerService:
    """NER extraction using Ollama LLM with Mexican jargon dictionary."""

    def _preprocess_jerga(self, texto: str) -> tuple:
        """Replace jargon with canonical terms, keep position map."""
        texto_proc = texto
        replacements = []
        for jerga, info in sorted(JERGA_MX.items(), key=lambda x: -len(x[0])):
            pattern = re.compile(re.escape(jerga), re.IGNORECASE)
            for m in pattern.finditer(texto_proc):
                replacements.append({
                    "original": m.group(), "canonical": info["canonical"],
                    "tipo": info["tipo"], "start": m.start(), "end": m.end(),
                })
        return texto_proc, replacements

    async def extract(self, req: NerRequest) -> NerResponse:
        """Extract entities from narrative text using Ollama structured output."""
        from clients.ollama_client import ollama_chat, MODEL_SMALL

        start = time.perf_counter()
        texto_proc, jerga_replacements = self._preprocess_jerga(req.texto)

        messages = [
            {
                "role": "system",
                "content": (
                    "Eres un extractor de entidades para investigación criminal en México. "
                    "Analiza el texto y extrae ÚNICAMENTE entidades que aparecen explícitamente. "
                    "No inferras ni inventes. Responde SOLO con el JSON del schema. "
                    "Para el campo 'rol' de personas, usa: victima, sospechoso, testigo, oficial, desconocido."
                ),
            },
            {
                "role": "user",
                "content": f"Texto a analizar:\n---\n{texto_proc}\n---\n\nExtrae todas las entidades.",
            },
        ]

        try:
            result = await ollama_chat(
                model=MODEL_SMALL, messages=messages,
                schema=NER_SCHEMA, temperature=0.0,
            )
        except Exception as e:
            logger.error(f"NER Ollama call failed: {e}")
            result = {"personas": [], "vehiculos": [], "armas": [], "lugares": [],
                       "fechas": [], "montos": [], "organizaciones": [], "objetos": []}

        # Build entities list
        entities: List[NerEntity] = []
        for p in result.get("personas", []):
            entities.append(NerEntity(
                texto=p.get("nombre", ""), tipo="PERSONA", confianza=0.85,
                delta_sugerido="personas", campo_sugerido="nombre",
            ))
        for v in result.get("vehiculos", []):
            desc = f"{v.get('marca', '')} {v.get('modelo', '')} {v.get('color', '')}".strip()
            entities.append(NerEntity(
                texto=desc or v.get("tipo", ""), tipo="VEHICULO", confianza=0.80,
                delta_sugerido="vehiculos", campo_sugerido="tipo",
            ))
        for a in result.get("armas", []):
            entities.append(NerEntity(
                texto=a.get("tipo", "") or a.get("descripcion", ""), tipo="ARMA", confianza=0.80,
                delta_sugerido="armas", campo_sugerido="tipo",
            ))
        for l in result.get("lugares", []):
            entities.append(NerEntity(
                texto=l.get("descripcion", ""), tipo="LUGAR", confianza=0.75,
                delta_sugerido="lugares", campo_sugerido="descripcion",
            ))
        for f in result.get("fechas", []):
            entities.append(NerEntity(
                texto=str(f), tipo="FECHA_HORA", confianza=0.80,
                delta_sugerido="eventos", campo_sugerido="fecha",
            ))
        for m in result.get("montos", []):
            entities.append(NerEntity(
                texto=f"{m.get('valor', '')} {m.get('moneda', '')}", tipo="MONTO", confianza=0.75,
                delta_sugerido="objetos", campo_sugerido="valor",
            ))
        for o in result.get("organizaciones", []):
            entities.append(NerEntity(
                texto=str(o), tipo="ORGANIZACIÓN", confianza=0.70,
                delta_sugerido="corporaciones", campo_sugerido="nombre",
            ))
        for obj in result.get("objetos", []):
            entities.append(NerEntity(
                texto=str(obj), tipo="OBJETO", confianza=0.70,
                delta_sugerido="objetos", campo_sugerido="descripcion",
            ))

        # Add jerga entities
        for jr in jerga_replacements:
            entities.append(NerEntity(
                texto=f"{jr['original']} → {jr['canonical']}", tipo=jr["tipo"],
                confianza=0.95, delta_sugerido="", campo_sugerido="",
            ))

        # Build DeltaPreFill
        delta = DeltaPreFill(
            personas=result.get("personas", []),
            vehiculos=result.get("vehiculos", []),
            armas=result.get("armas", []),
            lugares=result.get("lugares", []),
            objetos=[{"descripcion": o} for o in result.get("objetos", [])],
            corporaciones=[{"nombre": o} for o in result.get("organizaciones", [])],
        )

        # Build highlighted text
        texto_resaltado = self._highlight_entities(req.texto, entities)

        h = _custody_hash(req.user, "NER", "ExtractFromNarrative", {
            "folio_id": req.folio_id, "carpeta_id": req.carpeta_id,
            "entidades_detectadas": len(entities),
        })

        return NerResponse(
            entities=entities, delta_pre_fill=delta,
            texto_resaltado=texto_resaltado, hash_custodia=h,
        )

    async def extract_async(self, payload: dict) -> dict:
        """Queue-compatible wrapper."""
        req = NerRequest(
            texto=payload.get("texto", ""),
            carpeta_id=payload.get("carpeta_id"),
            folio_id=payload.get("folio_id"),
        )
        result = await self.extract(req)
        return result.model_dump()

    def _highlight_entities(self, texto: str, entities: List[NerEntity]) -> str:
        """Generate HTML with colored spans for each entity."""
        highlighted = texto
        # Sort entities by text length desc to avoid partial replacements
        for ent in sorted(entities, key=lambda e: -len(e.texto)):
            if not ent.texto or "→" in ent.texto:
                continue
            color = ENTITY_COLORS.get(ent.tipo, "#6B7280")
            pattern = re.compile(re.escape(ent.texto), re.IGNORECASE)
            replacement = f'<span style="background:{color}22;color:{color};padding:0 2px;border-radius:2px" title="{ent.tipo}">{ent.texto}</span>'
            highlighted = pattern.sub(replacement, highlighted, count=1)
        return highlighted

    def update_jargon(self, req: UpdateJargonRequest) -> UpdateJargonResponse:
        """Add or update jargon dictionary entries."""
        for entry in req.entries:
            JERGA_MX[entry.jerga.lower()] = {
                "canonical": entry.canonical, "tipo": entry.tipo,
            }
        h = _custody_hash(req.user, "NER", "UpdateJargonDict", {"total": len(req.entries)})
        return UpdateJargonResponse(total=len(JERGA_MX), hash_custodia=h)


ner_service = NerService()
