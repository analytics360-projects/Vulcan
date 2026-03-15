"""Semantic search service — Spanish synonym expansion and contradiction detection."""
import re
import time
from typing import List, Dict, Tuple
from config import logger
from modules.semantic_search.models import (
    SemanticSearchRequest, SemanticSearchResponse, SearchHit,
    ContradictionRequest, ContradictionResponse, ContradictionPair,
)

# ── Spanish synonym groups for query expansion ──

SYNONYM_GROUPS = [
    ["arma", "pistola", "revolver", "fusil", "rifle", "escopeta", "fierro", "cuete", "fusca"],
    ["droga", "estupefaciente", "narcótico", "sustancia", "cristal", "mota", "coca", "marihuana"],
    ["vehículo", "carro", "auto", "coche", "camioneta", "automóvil", "unidad"],
    ["robo", "asalto", "atraco", "hurto", "despojo"],
    ["muerto", "occiso", "cadáver", "sin vida", "fallecido", "difunto", "víctima mortal"],
    ["herido", "lesionado", "lastimado", "golpeado", "agredido"],
    ["testigo", "declarante", "informante", "denunciante"],
    ["sospechoso", "imputado", "indiciado", "presunto", "probable responsable"],
    ["domicilio", "casa", "hogar", "residencia", "vivienda", "morada"],
    ["dinero", "efectivo", "lana", "billete", "recurso económico"],
    ["golpear", "agredir", "pegar", "atacar", "lesionar", "lastimar"],
    ["huir", "escapar", "fugarse", "darse a la fuga", "correr", "alejarse"],
    ["noche", "madrugada", "oscuridad", "nocturno"],
    ["mañana", "amanecer", "matutino", "temprano"],
]

# ── Temporal contradiction patterns ──

TEMPORAL_PATTERNS = [
    (r"(\d{1,2}:\d{2})", "hora"),
    (r"(lunes|martes|miércoles|jueves|viernes|sábado|domingo)", "dia"),
    (r"(mañana|tarde|noche|madrugada)", "periodo"),
]

NEGATION_PAIRS = [
    ("sí", "no"), ("presente", "ausente"), ("armado", "desarmado"),
    ("vivo", "muerto"), ("entró", "salió"), ("llegó", "se fue"),
    ("antes", "después"), ("izquierda", "derecha"), ("norte", "sur"),
    ("claro", "oscuro"), ("grande", "pequeño"), ("hombre", "mujer"),
]

QUANTITY_PATTERN = re.compile(r"(\d+)\s+(persona|sujeto|individuo|hombre|mujer|vehículo|disparo|tiro|balazo|golpe)", re.IGNORECASE)


class SemanticSearchService:
    """Synonym-aware search over transcriptions and contradiction detection."""

    def __init__(self):
        self._synonym_map: Dict[str, List[str]] = {}
        for group in SYNONYM_GROUPS:
            for word in group:
                self._synonym_map[word.lower()] = [w.lower() for w in group if w.lower() != word.lower()]

    def search(self, req: SemanticSearchRequest, corpus: List[Dict] = None) -> SemanticSearchResponse:
        """Search with Spanish synonym expansion."""
        start = time.time()
        expanded = self._expand_query(req.query)

        if corpus is None:
            corpus = []

        results: List[SearchHit] = []
        for doc in corpus:
            text = doc.get("texto", "").lower()
            score, keywords = self._score_document(text, expanded)
            if score >= req.umbral_similitud:
                fragment = self._extract_fragment(text, keywords)
                results.append(SearchHit(
                    source_id=doc.get("id", ""),
                    source_type=doc.get("tipo", "transcripcion"),
                    texto=doc.get("texto", "")[:200],
                    fragmento=fragment,
                    score=round(score, 3),
                    palabras_clave=keywords[:10],
                    fecha=doc.get("fecha"),
                ))

        results.sort(key=lambda h: h.score, reverse=True)
        results = results[:req.max_results]
        elapsed = int((time.time() - start) * 1000)

        return SemanticSearchResponse(
            resultados=results,
            total=len(results),
            query_expandida=expanded,
            tiempo_ms=elapsed,
        )

    def detect_contradictions(self, req: ContradictionRequest) -> ContradictionResponse:
        """Detect contradictions between multiple texts/statements."""
        contradictions: List[ContradictionPair] = []

        for i in range(len(req.textos)):
            for j in range(i + 1, len(req.textos)):
                a = req.textos[i]
                b = req.textos[j]
                pairs = self._find_contradictions(a, b)
                for typ, frag_a, frag_b, severity, explanation in pairs:
                    if severity >= req.umbral:
                        contradictions.append(ContradictionPair(
                            texto_a_id=a.get("id", str(i)),
                            texto_b_id=b.get("id", str(j)),
                            fragmento_a=frag_a,
                            fragmento_b=frag_b,
                            tipo=typ,
                            explicacion=explanation,
                            severidad=round(severity, 2),
                        ))

        total = len(contradictions)
        consistency = max(0, 1.0 - total * 0.1) if req.textos else 1.0

        return ContradictionResponse(
            contradicciones=contradictions,
            total=total,
            consistencia_global=round(consistency, 2),
        )

    # ── Private helpers ──

    def _expand_query(self, query: str) -> List[str]:
        words = query.lower().split()
        expanded = set(words)
        for word in words:
            if word in self._synonym_map:
                expanded.update(self._synonym_map[word])
        return list(expanded)

    def _score_document(self, text: str, terms: List[str]) -> Tuple[float, List[str]]:
        found = [t for t in terms if t in text]
        if not found:
            return 0.0, []
        score = len(found) / len(terms)
        return score, found

    def _extract_fragment(self, text: str, keywords: List[str], window: int = 80) -> str:
        if not keywords:
            return text[:150]
        for kw in keywords:
            idx = text.find(kw)
            if idx >= 0:
                start = max(0, idx - window)
                end = min(len(text), idx + len(kw) + window)
                return "..." + text[start:end] + "..."
        return text[:150]

    def _find_contradictions(self, a: Dict, b: Dict) -> List[Tuple[str, str, str, float, str]]:
        results = []
        text_a = a.get("texto", "").lower()
        text_b = b.get("texto", "").lower()

        # Check negation pairs
        for pos, neg in NEGATION_PAIRS:
            if pos in text_a and neg in text_b:
                results.append((
                    "factual",
                    self._extract_fragment(text_a, [pos], 40),
                    self._extract_fragment(text_b, [neg], 40),
                    0.7,
                    f"Contradicción: '{pos}' vs '{neg}'",
                ))
            elif neg in text_a and pos in text_b:
                results.append((
                    "factual",
                    self._extract_fragment(text_a, [neg], 40),
                    self._extract_fragment(text_b, [pos], 40),
                    0.7,
                    f"Contradicción: '{neg}' vs '{pos}'",
                ))

        # Check quantity discrepancies
        q_a = QUANTITY_PATTERN.findall(text_a)
        q_b = QUANTITY_PATTERN.findall(text_b)
        for num_a, obj_a in q_a:
            for num_b, obj_b in q_b:
                if obj_a == obj_b and num_a != num_b:
                    results.append((
                        "cuantitativa",
                        f"{num_a} {obj_a}",
                        f"{num_b} {obj_b}",
                        0.8,
                        f"Discrepancia numérica: {num_a} vs {num_b} {obj_a}(s)",
                    ))

        # Check temporal contradictions
        for pattern, label in TEMPORAL_PATTERNS:
            matches_a = re.findall(pattern, text_a, re.IGNORECASE)
            matches_b = re.findall(pattern, text_b, re.IGNORECASE)
            if matches_a and matches_b:
                for ma in matches_a:
                    for mb in matches_b:
                        if ma.lower() != mb.lower():
                            results.append((
                                "temporal",
                                f"{label}: {ma}",
                                f"{label}: {mb}",
                                0.6,
                                f"Discrepancia temporal ({label}): '{ma}' vs '{mb}'",
                            ))

        return results


semantic_search_service = SemanticSearchService()
