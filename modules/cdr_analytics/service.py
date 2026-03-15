"""CDR Analytics service — Call detail record graph analysis and pattern detection."""
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Tuple, Set
from config import logger
from modules.cdr_analytics.models import (
    CallRecord, CDRUploadRequest, CDRAnalysisResponse,
    PhoneNode, CDREdge, CDRPattern,
    CDRTimelineRequest, CDRTimelineResponse, CDRTimelineEntry,
)


class CDRAnalyticsService:
    """Analyze call detail records for graph structure and behavioral patterns."""

    def analyze(self, req: CDRUploadRequest) -> CDRAnalysisResponse:
        records = req.registros
        if not records:
            return CDRAnalysisResponse(
                nodos=[], enlaces=[], patrones=[],
                total_registros=0, rango_fechas={},
            )

        # Build adjacency
        edges_map: Dict[Tuple[str, str], List[CallRecord]] = defaultdict(list)
        node_calls: Dict[str, List[CallRecord]] = defaultdict(list)

        for r in records:
            key = (r.numero_origen, r.numero_destino)
            edges_map[key].append(r)
            node_calls[r.numero_origen].append(r)
            node_calls[r.numero_destino].append(r)

        # Build nodes
        nodes: List[PhoneNode] = []
        contacts: Dict[str, Set[str]] = defaultdict(set)
        for r in records:
            contacts[r.numero_origen].add(r.numero_destino)
            contacts[r.numero_destino].add(r.numero_origen)

        max_contacts = max((len(c) for c in contacts.values()), default=1)

        for num, calls in node_calls.items():
            n_unique = len(contacts[num])
            centralidad = n_unique / max_contacts if max_contacts > 0 else 0
            nodes.append(PhoneNode(
                numero=num,
                total_llamadas=len(calls),
                total_duracion_seg=sum(c.duracion_seg for c in calls),
                contactos_unicos=n_unique,
                es_central=centralidad > 0.5,
                grado_centralidad=round(centralidad, 3),
            ))

        nodes.sort(key=lambda n: n.grado_centralidad, reverse=True)
        central = nodes[0].numero if nodes else None

        # Build edges
        edges: List[CDREdge] = []
        for (orig, dest), calls in edges_map.items():
            fechas = sorted(c.fecha for c in calls if c.fecha)
            edges.append(CDREdge(
                origen=orig, destino=dest,
                total_llamadas=len(calls),
                total_duracion_seg=sum(c.duracion_seg for c in calls),
                primera_llamada=fechas[0] if fechas else "",
                ultima_llamada=fechas[-1] if fechas else "",
            ))

        # Detect patterns
        patterns = self._detect_patterns(records, node_calls, contacts)

        # Date range
        all_dates = [r.fecha for r in records if r.fecha]
        rango = {}
        if all_dates:
            rango = {"inicio": min(all_dates), "fin": max(all_dates)}

        return CDRAnalysisResponse(
            nodos=nodes, enlaces=edges, patrones=patterns,
            total_registros=len(records), rango_fechas=rango,
            numero_central=central,
        )

    def timeline(self, req: CDRTimelineRequest) -> CDRTimelineResponse:
        by_date: Dict[str, Dict] = defaultdict(lambda: {
            "entrantes": 0, "salientes": 0, "duracion": 0, "contactos": set()
        })
        all_contacts_seen: Set[str] = set()

        for r in req.registros:
            date_key = r.fecha[:10] if r.fecha else "unknown"
            if r.numero_origen == req.numero:
                by_date[date_key]["salientes"] += 1
                other = r.numero_destino
            else:
                by_date[date_key]["entrantes"] += 1
                other = r.numero_origen
            by_date[date_key]["duracion"] += r.duracion_seg
            by_date[date_key]["contactos"].add(other)

        entries: List[CDRTimelineEntry] = []
        for date in sorted(by_date.keys()):
            data = by_date[date]
            new_contacts = len(data["contactos"] - all_contacts_seen)
            all_contacts_seen.update(data["contactos"])
            entries.append(CDRTimelineEntry(
                fecha=date,
                llamadas_entrantes=data["entrantes"],
                llamadas_salientes=data["salientes"],
                duracion_total=data["duracion"],
                contactos_nuevos=new_contacts,
            ))

        return CDRTimelineResponse(
            numero=req.numero,
            timeline=entries,
            total_dias=len(entries),
        )

    def _detect_patterns(self, records: List[CallRecord],
                         node_calls: Dict, contacts: Dict) -> List[CDRPattern]:
        patterns: List[CDRPattern] = []

        # Burst pattern: >10 calls in short window to same number
        pair_times: Dict[Tuple[str, str], List[str]] = defaultdict(list)
        for r in records:
            pair_times[(r.numero_origen, r.numero_destino)].append(r.fecha)

        for (a, b), times in pair_times.items():
            if len(times) >= 10:
                sorted_t = sorted(times)
                patterns.append(CDRPattern(
                    tipo="burst",
                    descripcion=f"Ráfaga de {len(times)} llamadas entre {a} y {b}",
                    numeros_involucrados=[a, b],
                    severidad=min(len(times) / 20, 1.0),
                    fecha_inicio=sorted_t[0],
                    fecha_fin=sorted_t[-1],
                ))

        # Nocturnal pattern: calls between 00:00-06:00
        nocturnal: Dict[str, int] = defaultdict(int)
        for r in records:
            try:
                hour = int(r.fecha[11:13]) if len(r.fecha) > 12 else -1
                if 0 <= hour < 6:
                    nocturnal[r.numero_origen] += 1
            except (ValueError, IndexError):
                pass

        for num, count in nocturnal.items():
            if count >= 5:
                patterns.append(CDRPattern(
                    tipo="nocturno",
                    descripcion=f"{num} realizó {count} llamadas en horario nocturno (00-06h)",
                    numeros_involucrados=[num],
                    severidad=min(count / 15, 1.0),
                    fecha_inicio=min(r.fecha for r in records if r.numero_origen == num),
                    fecha_fin=max(r.fecha for r in records if r.numero_origen == num),
                ))

        # Triangular: A↔B, B↔C, A↔C
        nums = list(contacts.keys())
        for i in range(min(len(nums), 50)):
            for j in range(i+1, min(len(nums), 50)):
                for k in range(j+1, min(len(nums), 50)):
                    a, b, c = nums[i], nums[j], nums[k]
                    if b in contacts[a] and c in contacts[b] and c in contacts[a]:
                        patterns.append(CDRPattern(
                            tipo="triangular",
                            descripcion=f"Comunicación triangular entre {a}, {b}, {c}",
                            numeros_involucrados=[a, b, c],
                            severidad=0.6,
                            fecha_inicio=min(r.fecha for r in records),
                            fecha_fin=max(r.fecha for r in records),
                        ))

        return patterns[:20]  # Limit patterns


cdr_analytics_service = CDRAnalyticsService()
