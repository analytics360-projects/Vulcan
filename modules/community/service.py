"""Community detection — Louvain algorithm (pure Python) + graph metrics."""
import hashlib
import json
import math
import random
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import List, Dict, Set, Tuple

from config import logger
from modules.community.models import (
    DetectCommunitiesRequest, DetectCommunitiesResponse,
    CommunityResult, NodeMetrics, GraphNode, GraphEdge,
    IntelligenceReportRequest, IntelligenceReportResponse,
)

# Relation type weights
PESOS_RELACION = {
    "llamada_telefonica": 3.0,
    "aparicion_conjunta_cctv": 5.0,
    "misma_direccion": 4.0,
    "red_social": 2.0,
    "familiar": 6.0,
    "vehiculo_compartido": 4.0,
    "transaccion_financiera": 5.0,
    "co_ocurrencia": 3.0,
    "comunicacion": 3.0,
    "default": 1.0,
}

# Vis-network colors per community
COMMUNITY_COLORS = [
    "#3B82F6", "#EF4444", "#10B981", "#F59E0B", "#8B5CF6",
    "#EC4899", "#06B6D4", "#F97316", "#84CC16", "#6366F1",
]

NODE_SHAPES = {
    "PERSONA": "dot", "VEHICULO": "square", "LUGAR": "triangle",
    "ORGANIZACIÓN": "diamond", "TELEFONO": "star", "EVENTO": "triangleDown",
}


def _custody_hash(user: str, modulo: str, accion: str, params: dict) -> str:
    payload = f"{user}|{modulo}|{accion}|{json.dumps(params, sort_keys=True)}|{datetime.now(timezone.utc).isoformat()}"
    return hashlib.sha256(payload.encode()).hexdigest()


class LouvainCommunity:
    """Pure Python Louvain community detection."""

    def __init__(self, resolution: float = 1.0):
        self.resolution = resolution

    def detect(self, nodes: List[str], edges: List[Tuple[str, str, float]]) -> Tuple[Dict[str, int], float]:
        if not nodes or not edges:
            return {n: 0 for n in nodes}, 0.0

        adj: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for u, v, w in edges:
            adj[u][v] += w
            adj[v][u] += w

        m = sum(w for _, _, w in edges)
        if m == 0:
            return {n: i for i, n in enumerate(nodes)}, 0.0

        degree: Dict[str, float] = defaultdict(float)
        for u, v, w in edges:
            degree[u] += w
            degree[v] += w

        node2comm = {n: i for i, n in enumerate(nodes)}
        comm_nodes: Dict[int, Set[str]] = {i: {n} for i, n in enumerate(nodes)}

        improved = True
        iteration = 0
        while improved and iteration < 50:
            improved = False
            iteration += 1
            node_list = list(nodes)
            random.shuffle(node_list)

            for node in node_list:
                current_comm = node2comm[node]
                neighbor_comms: Dict[int, float] = defaultdict(float)
                for neighbor, w in adj[node].items():
                    neighbor_comms[node2comm[neighbor]] += w

                comm_nodes[current_comm].discard(node)
                k_i = degree[node]
                sigma_tot_current = sum(degree[n] for n in comm_nodes[current_comm])
                k_i_in_current = neighbor_comms.get(current_comm, 0.0)
                remove_gain = -k_i_in_current / m + self.resolution * sigma_tot_current * k_i / (2 * m * m)

                best_comm, best_gain = current_comm, 0.0
                for comm_id, k_i_in in neighbor_comms.items():
                    if comm_id == current_comm:
                        continue
                    sigma_tot = sum(degree[n] for n in comm_nodes[comm_id])
                    add_gain = k_i_in / m - self.resolution * sigma_tot * k_i / (2 * m * m)
                    total_gain = remove_gain + add_gain
                    if total_gain > best_gain:
                        best_gain = total_gain
                        best_comm = comm_id

                node2comm[node] = best_comm
                comm_nodes[best_comm].add(node)
                if best_comm != current_comm:
                    improved = True
                if not comm_nodes[current_comm]:
                    del comm_nodes[current_comm]

        unique_comms = sorted(set(node2comm.values()))
        remap = {old: new for new, old in enumerate(unique_comms)}
        result = {n: remap[c] for n, c in node2comm.items()}
        modularity = self._modularity(result, adj, degree, m)
        return result, modularity

    def _modularity(self, node2comm, adj, degree, m):
        if m == 0:
            return 0.0
        q = 0.0
        for u in node2comm:
            for v, w in adj[u].items():
                if node2comm[u] == node2comm[v]:
                    q += w - degree[u] * degree[v] / (2 * m)
        return q / (2 * m)


class CommunityService:
    """Community detection and graph metrics."""

    def detect(self, req: DetectCommunitiesRequest) -> DetectCommunitiesResponse:
        start = time.perf_counter()
        node_map = {n.id: n for n in req.nodes}
        node_ids = [n.id for n in req.nodes]

        edges = []
        for e in req.edges:
            if e.source in node_map and e.target in node_map:
                w = PESOS_RELACION.get(e.tipo_relacion, PESOS_RELACION["default"]) * e.peso
                edges.append((e.source, e.target, w))

        louvain = LouvainCommunity(resolution=req.resolution)
        node2comm, modularity = louvain.detect(node_ids, edges)

        # Adjacency for metrics
        adj: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        adj_simple: Dict[str, Set[str]] = defaultdict(set)
        for u, v, w in edges:
            adj[u][v] += w
            adj[v][u] += w
            adj_simple[u].add(v)
            adj_simple[v].add(u)

        # Centrality
        centrality = self._betweenness_centrality(node_ids, adj_simple)
        closeness = self._closeness_centrality(node_ids, adj_simple)

        # Build communities
        comm_members: Dict[int, List[str]] = defaultdict(list)
        for nid, cid in node2comm.items():
            comm_members[cid].append(nid)

        communities = []
        for cid, members in sorted(comm_members.items()):
            if len(members) < req.min_community_size:
                continue
            member_set = set(members)
            internal_edges = sum(1 for u in members for v in adj_simple[u] if v in member_set and u < v)
            max_edges = len(members) * (len(members) - 1) / 2
            density = internal_edges / max_edges if max_edges > 0 else 0.0
            communities.append(CommunityResult(
                community_id=cid, nodos=members,
                tamano=len(members), densidad_interna=round(density, 4),
            ))

        # Node metrics + roles
        all_betweenness = [centrality.get(n, 0) for n in node_ids]
        all_betweenness_sorted = sorted(all_betweenness)
        p90 = all_betweenness_sorted[int(len(all_betweenness_sorted) * 0.9)] if all_betweenness_sorted else 0
        p75 = all_betweenness_sorted[int(len(all_betweenness_sorted) * 0.75)] if all_betweenness_sorted else 0

        all_degrees = [len(adj_simple[n]) for n in node_ids]
        all_degrees_sorted = sorted(all_degrees)
        p50_degree = all_degrees_sorted[int(len(all_degrees_sorted) * 0.5)] if all_degrees_sorted else 0

        node_metrics = []
        for nid in node_ids:
            node = node_map[nid]
            bt = centrality.get(nid, 0)
            deg = len(adj_simple[nid])
            cl = closeness.get(nid, 0)

            # Check if bridges communities
            neighbor_comms = set(node2comm.get(nb, -1) for nb in adj_simple[nid])
            bridges = len(neighbor_comms) > 1

            if bt > p90 and bridges:
                rol = "BROKER"
            elif bt > p75:
                rol = "LIDER"
            elif deg > p50_degree:
                rol = "MIEMBRO"
            else:
                rol = "PERIFERICO"

            node_metrics.append(NodeMetrics(
                node_id=nid, label=node.label, tipo=node.tipo,
                degree=deg, betweenness=round(bt, 6), closeness=round(cl, 6),
                rol=rol, community_id=node2comm.get(nid, 0),
                prioridad_investigativa={"BROKER": 1, "LIDER": 2, "MIEMBRO": 3, "PERIFERICO": 4}[rol],
            ))

        node_metrics.sort(key=lambda m: m.prioridad_investigativa)
        top_actors = node_metrics[:5]

        vis = self._build_vis_network(req.nodes, req.edges, node2comm)

        elapsed = (time.perf_counter() - start) * 1000
        h = _custody_hash(req.user, "GRAPH", "DetectCommunities", {
            "total_nodes": len(node_ids), "communities": len(communities),
        })

        return DetectCommunitiesResponse(
            communities=communities, node_metrics=node_metrics,
            top_actors=top_actors, vis_network_data=vis, hash_custodia=h,
        )

    def detect_from_payload(self, payload: dict) -> dict:
        """Queue-compatible wrapper."""
        nodes = [GraphNode(**n) for n in payload.get("nodes", [])]
        edges = [GraphEdge(**e) for e in payload.get("edges", [])]
        req = DetectCommunitiesRequest(
            nodes=nodes, edges=edges,
            carpeta_id=payload.get("carpeta_id"),
        )
        return self.detect(req).model_dump()

    async def intelligence_report(self, req: IntelligenceReportRequest) -> IntelligenceReportResponse:
        """Generate intelligence report for graph."""
        from clients.ollama_client import ollama_chat, MODEL_MEDIUM

        detect_req = DetectCommunitiesRequest(
            nodes=req.nodes, edges=req.edges, carpeta_id=req.carpeta_id,
        )
        detection = self.detect(detect_req)

        context = (
            f"Comunidades detectadas: {len(detection.communities)}\n"
            f"Actores clave: {', '.join(a.label for a in detection.top_actors)}\n"
            f"Total nodos: {len(req.nodes)}, Total aristas: {len(req.edges)}\n"
        )
        for comm in detection.communities:
            context += f"\nComunidad {comm.community_id}: {comm.tamano} miembros, densidad {comm.densidad_interna}\n"

        messages = [
            {"role": "system", "content": "Eres un analista de inteligencia criminal. Genera un reporte breve de la red analizada."},
            {"role": "user", "content": f"Análisis de red para carpeta {req.carpeta_id}:\n{context}\nGenera un reporte de inteligencia."},
        ]

        try:
            result = await ollama_chat(model=MODEL_MEDIUM, messages=messages, temperature=0.1)
            reporte = result.get("text", "Reporte no disponible.")
        except Exception as e:
            reporte = f"Error generando reporte: {e}"

        h = _custody_hash(req.user, "GRAPH", "IntelligenceReport", {"carpeta_id": req.carpeta_id})
        return IntelligenceReportResponse(
            reporte=reporte, comunidades_detectadas=len(detection.communities),
            actores_clave=[a.label for a in detection.top_actors],
            hash_custodia=h,
        )

    def _betweenness_centrality(self, nodes, adj) -> Dict[str, float]:
        centrality = {n: 0.0 for n in nodes}
        sample = nodes if len(nodes) <= 100 else random.sample(nodes, 100)
        for s in sample:
            stack, pred = [], {n: [] for n in nodes}
            sigma = {n: 0.0 for n in nodes}
            sigma[s] = 1.0
            dist = {n: -1 for n in nodes}
            dist[s] = 0
            queue, qi = [s], 0
            while qi < len(queue):
                v = queue[qi]; qi += 1; stack.append(v)
                for w in adj[v]:
                    if dist[w] < 0:
                        queue.append(w); dist[w] = dist[v] + 1
                    if dist[w] == dist[v] + 1:
                        sigma[w] += sigma[v]; pred[w].append(v)
            delta = {n: 0.0 for n in nodes}
            while stack:
                w = stack.pop()
                for v in pred[w]:
                    if sigma[w] > 0:
                        delta[v] += (sigma[v] / sigma[w]) * (1 + delta[w])
                if w != s:
                    centrality[w] += delta[w]
        n = len(nodes)
        scale = 1.0 / ((n - 1) * (n - 2)) if n > 2 else 1.0
        if len(nodes) > 100:
            scale *= len(nodes) / 100
        for nid in centrality:
            centrality[nid] *= scale
        return centrality

    def _closeness_centrality(self, nodes, adj) -> Dict[str, float]:
        closeness = {}
        for s in nodes:
            dist = {s: 0}
            queue, qi = [s], 0
            while qi < len(queue):
                v = queue[qi]; qi += 1
                for w in adj[v]:
                    if w not in dist:
                        dist[w] = dist[v] + 1
                        queue.append(w)
            reachable = len(dist) - 1
            closeness[s] = reachable / sum(dist.values()) if sum(dist.values()) > 0 else 0.0
        return closeness

    def _build_vis_network(self, nodes, edges, node2comm) -> Dict:
        vis_nodes = []
        for node in nodes:
            cid = node2comm.get(node.id, 0)
            vis_nodes.append({
                "id": node.id, "label": node.label, "group": cid,
                "color": COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)],
                "shape": NODE_SHAPES.get(node.tipo, "dot"),
                "title": f"{node.label} ({node.tipo}) — Comunidad {cid + 1}",
            })
        vis_edges = []
        for edge in edges:
            vis_edges.append({
                "from": edge.source, "to": edge.target,
                "width": edge.peso, "title": edge.tipo_relacion,
            })
        return {"nodes": vis_nodes, "edges": vis_edges}


community_service = CommunityService()
