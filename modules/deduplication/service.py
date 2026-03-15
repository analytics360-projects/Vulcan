"""Deduplication service — pg_trgm DB search + in-memory Levenshtein/Soundex."""
import hashlib
import json
import time
from datetime import datetime, timezone
from typing import List, Optional

from config import settings, logger
from modules.deduplication.models import (
    PersonRecord, MatchPair, DeduplicationRequest, DeduplicationResponse,
    CheckPersonRequest, CheckPersonResponse, DuplicateCandidate,
    MergePersonRequest, MergePersonResponse,
    MarkAliasRequest, MarkAliasResponse,
    normalize_name,
)

# ── Spanish Soundex ──
_SOUNDEX_MAP = {
    "b": "1", "v": "1", "f": "1",
    "c": "2", "s": "2", "z": "2", "g": "2", "j": "2", "x": "2",
    "d": "3", "t": "3",
    "l": "4",
    "m": "5", "n": "5", "ñ": "5",
    "r": "6",
}


def spanish_soundex(name: str, length: int = 6) -> str:
    if not name:
        return ""
    name = name.lower().strip()
    name = name.replace("ch", "s").replace("ll", "l").replace("rr", "r").replace("qu", "k").replace("gu", "g")
    code = [name[0].upper()]
    prev = _SOUNDEX_MAP.get(name[0], "0")
    for ch in name[1:]:
        digit = _SOUNDEX_MAP.get(ch, "0")
        if digit != "0" and digit != prev:
            code.append(digit)
        prev = digit if digit != "0" else prev
    return "".join(code)[:length].ljust(length, "0")


def levenshtein(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (0 if c1 == c2 else 1)))
        prev = curr
    return prev[-1]


def name_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    a, b = a.lower().strip(), b.lower().strip()
    if a == b:
        return 1.0
    return 1.0 - levenshtein(a, b) / max(len(a), len(b))


def _custody_hash(user: str, modulo: str, accion: str, params: dict) -> str:
    """Generate SHA-256 custody hash."""
    payload = f"{user}|{modulo}|{accion}|{json.dumps(params, sort_keys=True)}|{datetime.now(timezone.utc).isoformat()}"
    return hashlib.sha256(payload.encode()).hexdigest()


class DeduplicationService:
    """In-memory fuzzy person matching (legacy)."""

    def find_duplicates(self, req: DeduplicationRequest) -> DeduplicationResponse:
        personas = req.personas
        pairs: List[MatchPair] = []
        for i in range(len(personas)):
            for j in range(i + 1, len(personas)):
                match = self._compare_persons(personas[i], personas[j])
                if match and match.score_total >= req.umbral_revision:
                    match.recomendacion = "fusionar" if match.score_total >= req.umbral_fusion else "revisar"
                    pairs.append(match)
        pairs.sort(key=lambda p: p.score_total, reverse=True)
        tasa = len(pairs) / len(personas) if personas else 0
        return DeduplicationResponse(
            pares_duplicados=pairs, total_personas=len(personas),
            total_duplicados=len(pairs), tasa_duplicacion=round(tasa, 3),
        )

    def _compare_persons(self, a: PersonRecord, b: PersonRecord) -> MatchPair | None:
        campos = []
        name_a = f"{a.nombre} {a.apellido_paterno} {a.apellido_materno}".strip()
        name_b = f"{b.nombre} {b.apellido_paterno} {b.apellido_materno}".strip()
        score_name = name_similarity(name_a, name_b)
        sx_a, sx_b = spanish_soundex(name_a), spanish_soundex(name_b)
        score_phonetic = 1.0 if sx_a == sx_b else name_similarity(sx_a, sx_b)
        boost = 0.0
        if a.curp and b.curp and a.curp == b.curp:
            boost += 0.3; campos.append("curp")
        if a.telefono and b.telefono and a.telefono == b.telefono:
            boost += 0.2; campos.append("telefono")
        if a.fecha_nacimiento and b.fecha_nacimiento and a.fecha_nacimiento == b.fecha_nacimiento:
            boost += 0.15; campos.append("fecha_nacimiento")
        if score_name > 0.6: campos.append("nombre")
        if score_phonetic > 0.7: campos.append("fonetico")
        total = min(1.0, score_name * 0.4 + score_phonetic * 0.2 + boost + 0.1)
        return MatchPair(
            persona_a=a, persona_b=b, score_nombre=round(score_name, 3),
            score_fonetico=round(score_phonetic, 3), score_total=round(total, 3),
            campos_coincidentes=campos, recomendacion="descartar",
        )


class DbDeduplicationService:
    """PostgreSQL pg_trgm backed person deduplication."""

    def __init__(self):
        self._pool = None

    def _get_pool(self):
        if self._pool is None:
            import psycopg2
            from psycopg2 import pool as pg_pool
            conn_str = settings.postgres_main_connection_string
            if not conn_str:
                raise RuntimeError("postgres_main_connection_string not configured")
            self._pool = pg_pool.SimpleConnectionPool(1, 5, conn_str)
        return self._pool

    def _conn(self):
        return self._get_pool().getconn()

    def _release(self, conn):
        self._get_pool().putconn(conn)

    def _ensure_extensions(self, conn):
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            cur.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
            conn.commit()

    def check_person(self, req: CheckPersonRequest) -> CheckPersonResponse:
        """Check if a person exists: exact CURP/RFC → pg_trgm fuzzy → score composite."""
        start = time.perf_counter()
        nombre_norm = normalize_name(req.nombre)
        conn = self._conn()
        try:
            self._ensure_extensions(conn)
            candidates: List[DuplicateCandidate] = []

            with conn.cursor() as cur:
                # 1. Exact CURP match → definitive
                if req.curp:
                    cur.execute(
                        """SELECT "Id", "Nombre", "ApellidoPaterno", "ApellidoMaterno", "Curp"
                           FROM "SujetosCarpeta" WHERE "Curp" = %s LIMIT 10""",
                        (req.curp.upper(),)
                    )
                    for row in cur.fetchall():
                        candidates.append(DuplicateCandidate(
                            persona_id=row[0],
                            nombre=f"{row[1] or ''} {row[2] or ''} {row[3] or ''}".strip(),
                            score=1.0, campos_coincidentes=["curp"], curp=row[4],
                        ))

                # 2. Exact RFC match → definitive
                if req.rfc and not candidates:
                    cur.execute(
                        """SELECT "Id", "Nombre", "ApellidoPaterno", "ApellidoMaterno", "Curp"
                           FROM "SujetosCarpeta" WHERE "Rfc" = %s LIMIT 10""",
                        (req.rfc.upper(),)
                    )
                    for row in cur.fetchall():
                        if not any(c.persona_id == row[0] for c in candidates):
                            candidates.append(DuplicateCandidate(
                                persona_id=row[0],
                                nombre=f"{row[1] or ''} {row[2] or ''} {row[3] or ''}".strip(),
                                score=1.0, campos_coincidentes=["rfc"], curp=row[4],
                            ))

                # If definitive match found
                if candidates and candidates[0].score >= 1.0:
                    h = _custody_hash(req.user, "DEDUP", "CheckPerson", {"nombre": req.nombre, "status": "definitive_match"})
                    return CheckPersonResponse(
                        status="definitive_match", candidates=candidates,
                        suggested_action="merge", confidence=1.0, hash_custodia=h,
                    )

                # 3. pg_trgm fuzzy name match
                if nombre_norm:
                    cur.execute(
                        """SELECT "Id", "Nombre", "ApellidoPaterno", "ApellidoMaterno", "Curp",
                                  "FechaNacimiento", "Telefono",
                                  similarity(
                                    UPPER(unaccent(COALESCE("Nombre",'') || ' ' || COALESCE("ApellidoPaterno",'') || ' ' || COALESCE("ApellidoMaterno",''))),
                                    %s
                                  ) AS sim
                           FROM "SujetosCarpeta"
                           WHERE similarity(
                               UPPER(unaccent(COALESCE("Nombre",'') || ' ' || COALESCE("ApellidoPaterno",'') || ' ' || COALESCE("ApellidoMaterno",''))),
                               %s
                           ) > 0.4
                           ORDER BY sim DESC
                           LIMIT 20""",
                        (nombre_norm, nombre_norm)
                    )
                    for row in cur.fetchall():
                        if any(c.persona_id == row[0] for c in candidates):
                            continue
                        score_nombre = float(row[7])
                        campos = ["nombre"]

                        # Composite score
                        fecha_match = 0.0
                        if req.fecha_nacimiento and row[5]:
                            fecha_str = str(row[5])
                            if req.fecha_nacimiento in fecha_str or fecha_str in req.fecha_nacimiento:
                                fecha_match = 1.0
                                campos.append("fecha_nacimiento")

                        tel_match = 0.0
                        if req.telefono and row[6] and req.telefono.strip() == str(row[6]).strip():
                            tel_match = 1.0
                            campos.append("telefono")

                        score = (
                            score_nombre * 0.50 +
                            fecha_match * 0.20 +
                            tel_match * 0.15 +
                            0.0 * 0.15  # email placeholder
                        )

                        candidates.append(DuplicateCandidate(
                            persona_id=row[0],
                            nombre=f"{row[1] or ''} {row[2] or ''} {row[3] or ''}".strip(),
                            score=round(score, 4), campos_coincidentes=campos, curp=row[4],
                        ))

            # Classify
            candidates.sort(key=lambda c: c.score, reverse=True)
            # Filter only score >= 0.50 if not clear
            top_score = candidates[0].score if candidates else 0.0

            if top_score >= 0.90:
                status, action = "definitive_match", "merge"
            elif top_score >= 0.70:
                status, action = "review_required", "merge"
            elif top_score >= 0.50:
                status, action = "review_required", "link_as_alias"
            else:
                status, action = "clear", "insert"

            if status != "clear":
                candidates = [c for c in candidates if c.score >= 0.50]

            elapsed = (time.perf_counter() - start) * 1000
            h = _custody_hash(req.user, "DEDUP", "CheckPerson", {"nombre": req.nombre, "status": status})

            return CheckPersonResponse(
                status=status, candidates=candidates,
                suggested_action=action, confidence=top_score, hash_custodia=h,
            )
        finally:
            self._release(conn)

    def merge_persons(self, req: MergePersonRequest) -> MergePersonResponse:
        """Merge duplicate person: reassign references, collect aliases."""
        conn = self._conn()
        try:
            alias_added = []
            carpetas = []
            updated = 0

            with conn.cursor() as cur:
                cur.execute(
                    """SELECT "Nombre", "ApellidoPaterno", "ApellidoMaterno", "CarpetaInvestigacionId"
                       FROM "SujetosCarpeta" WHERE "Id" = %s""",
                    (req.persona_duplicada_id,)
                )
                dup = cur.fetchone()
                if not dup:
                    raise ValueError(f"Persona duplicada {req.persona_duplicada_id} not found")

                dup_nombre = f"{dup[0] or ''} {dup[1] or ''} {dup[2] or ''}".strip()
                if dup_nombre:
                    alias_added.append(dup_nombre)

                # Reassign nodo references
                cur.execute(
                    """UPDATE "CarpetasNodos" SET "PersonaId" = %s
                       WHERE "PersonaId" = %s""",
                    (req.persona_principal_id, req.persona_duplicada_id)
                )
                updated += cur.rowcount

                # Get affected carpetas
                if dup[3]:
                    carpetas.append(dup[3])

                # Soft-delete duplicate
                cur.execute(
                    """UPDATE "SujetosCarpeta" SET "Estatus" = 'fusionado_a_' || %s::text
                       WHERE "Id" = %s""",
                    (req.persona_principal_id, req.persona_duplicada_id)
                )
                updated += cur.rowcount
                conn.commit()

            h = _custody_hash(req.user, "DEDUP", "MergePerson", {
                "principal": req.persona_principal_id, "duplicada": req.persona_duplicada_id
            })

            return MergePersonResponse(
                persona_id=req.persona_principal_id,
                registros_actualizados=updated,
                alias_agregados=alias_added,
                carpetas_reasignadas=carpetas,
                hash_custodia=h,
            )
        except Exception:
            conn.rollback()
            raise
        finally:
            self._release(conn)

    def mark_alias(self, req: MarkAliasRequest) -> MarkAliasResponse:
        """Register an alias for a person."""
        try:
            from modules.sans.ravendb_client import get_store
            store = get_store()
            with store.open_session() as session:
                doc = {
                    "persona_id": req.persona_id, "alias": req.alias,
                    "tipo": req.tipo,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                session.store(doc, f"aliases/{req.persona_id}/{req.alias.lower().replace(' ', '_')}")
                session.save_changes()
        except Exception as e:
            logger.warning(f"RavenDB alias storage failed: {e}")

        h = _custody_hash(req.user, "DEDUP", "MarkAlias", {"persona_id": req.persona_id, "alias": req.alias})
        return MarkAliasResponse(
            persona_id=req.persona_id, alias_total=1, alias_nuevo=req.alias, hash_custodia=h,
        )

    def check_person_from_dict(self, data: dict) -> dict:
        """Convenience for event handlers."""
        req = CheckPersonRequest(
            nombre=data.get("nombre", ""),
            curp=data.get("curp"),
            rfc=data.get("rfc"),
            telefono=data.get("telefono"),
            fecha_nacimiento=data.get("fecha_nacimiento"),
        )
        result = self.check_person(req)
        return result.model_dump()


deduplication_service = DeduplicationService()
db_deduplication_service = DbDeduplicationService()
