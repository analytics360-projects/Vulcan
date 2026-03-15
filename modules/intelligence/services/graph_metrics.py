"""
IC5 — Network Criminal Metrics via Neo4j GDS
PageRank, Betweenness Centrality, Community Detection (Louvain)
Graceful fallback when GDS plugin is not installed.
"""
from typing import Any, Dict, List, Optional

from config import logger, settings


class GraphMetricsService:
    """Calculates criminal-network metrics on CarpetaNodo subgraphs."""

    def __init__(self):
        from neo4j import GraphDatabase

        self._driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        self._driver.verify_connectivity()
        self._gds_available: Optional[bool] = None
        logger.info("GraphMetricsService: Neo4j connection verified")

    # ── helpers ──────────────────────────────────────────────────────────

    def _check_gds(self) -> bool:
        """Detect whether the GDS library is installed (cached)."""
        if self._gds_available is not None:
            return self._gds_available
        try:
            with self._driver.session() as s:
                s.run("RETURN gds.version() AS v").single()
            self._gds_available = True
            logger.info("GraphMetricsService: GDS plugin detected")
        except Exception:
            self._gds_available = False
            logger.info("GraphMetricsService: GDS not available — using fallbacks")
        return self._gds_available

    def _graph_name(self, carpeta_id: int) -> str:
        return f"carpeta_{carpeta_id}_graph"

    def _project_graph(self, session, carpeta_id: int) -> bool:
        """Create an in-memory projected graph for the carpeta.  Returns True on success."""
        graph_name = self._graph_name(carpeta_id)
        # Drop if already exists
        try:
            session.run("CALL gds.graph.drop($name, false)", name=graph_name)
        except Exception:
            pass

        result = session.run(
            """
            CALL gds.graph.project.cypher(
                $name,
                'MATCH (n:CarpetaNodo) WHERE n.carpetaId = $carpetaId RETURN id(n) AS id',
                'MATCH (a:CarpetaNodo)-[r:RELACIONADO_CON]-(b:CarpetaNodo)
                 WHERE a.carpetaId = $carpetaId AND b.carpetaId = $carpetaId
                 RETURN id(a) AS source, id(b) AS target',
                {parameters: {carpetaId: $carpetaId}}
            )
            YIELD graphName, nodeCount, relationshipCount
            RETURN nodeCount, relationshipCount
            """,
            name=graph_name,
            carpetaId=carpeta_id,
        )
        rec = result.single()
        if rec is None or rec["nodeCount"] == 0:
            return False
        return True

    def _drop_graph(self, session, carpeta_id: int):
        try:
            session.run(
                "CALL gds.graph.drop($name, false)",
                name=self._graph_name(carpeta_id),
            )
        except Exception:
            pass

    def _nodes_for_carpeta(self, session, carpeta_id: int) -> List[Dict[str, Any]]:
        """Fetch raw nodes for fallback algorithms."""
        result = session.run(
            """
            MATCH (n:CarpetaNodo)
            WHERE n.carpetaId = $carpetaId
            RETURN n.nodoId AS nodoId, n.nombre AS nombre, n.tipo AS tipo, id(n) AS _neoId
            """,
            carpetaId=carpeta_id,
        )
        return [dict(r) for r in result]

    def _adjacency_for_carpeta(
        self, session, carpeta_id: int
    ) -> Dict[int, List[int]]:
        """Build adjacency list (neo4j internal ids) for fallback algorithms."""
        result = session.run(
            """
            MATCH (a:CarpetaNodo)-[r:RELACIONADO_CON]-(b:CarpetaNodo)
            WHERE a.carpetaId = $carpetaId AND b.carpetaId = $carpetaId
            RETURN id(a) AS src, id(b) AS dst
            """,
            carpetaId=carpeta_id,
        )
        adj: Dict[int, List[int]] = {}
        for rec in result:
            adj.setdefault(rec["src"], []).append(rec["dst"])
            adj.setdefault(rec["dst"], []).append(rec["src"])
        return adj

    # ── PageRank ─────────────────────────────────────────────────────────

    def calculate_pagerank(self, carpeta_id: int) -> List[Dict[str, Any]]:
        """PageRank via GDS; falls back to degree centrality."""
        if self._check_gds():
            return self._pagerank_gds(carpeta_id)
        return self._pagerank_fallback(carpeta_id)

    def _pagerank_gds(self, carpeta_id: int) -> List[Dict[str, Any]]:
        with self._driver.session() as s:
            if not self._project_graph(s, carpeta_id):
                return []
            try:
                result = s.run(
                    """
                    CALL gds.pageRank.stream($name)
                    YIELD nodeId, score
                    WITH gds.util.asNode(nodeId) AS n, score
                    RETURN n.nodoId AS nodo_id, n.nombre AS nombre, n.tipo AS tipo, score
                    ORDER BY score DESC
                    """,
                    name=self._graph_name(carpeta_id),
                )
                return [dict(r) for r in result]
            finally:
                self._drop_graph(s, carpeta_id)

    def _pagerank_fallback(self, carpeta_id: int) -> List[Dict[str, Any]]:
        """Degree centrality as proxy for PageRank when GDS is absent."""
        with self._driver.session() as s:
            nodes = self._nodes_for_carpeta(s, carpeta_id)
            adj = self._adjacency_for_carpeta(s, carpeta_id)
        if not nodes:
            return []
        max_degree = max((len(adj.get(n["_neoId"], [])) for n in nodes), default=1) or 1
        results = []
        for n in nodes:
            degree = len(adj.get(n["_neoId"], []))
            results.append(
                {
                    "nodo_id": n["nodoId"],
                    "nombre": n["nombre"],
                    "tipo": n["tipo"],
                    "score": round(degree / max_degree, 6),
                }
            )
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    # ── Betweenness ──────────────────────────────────────────────────────

    def calculate_betweenness(self, carpeta_id: int) -> List[Dict[str, Any]]:
        if self._check_gds():
            return self._betweenness_gds(carpeta_id)
        return self._betweenness_fallback(carpeta_id)

    def _betweenness_gds(self, carpeta_id: int) -> List[Dict[str, Any]]:
        with self._driver.session() as s:
            if not self._project_graph(s, carpeta_id):
                return []
            try:
                result = s.run(
                    """
                    CALL gds.betweenness.stream($name)
                    YIELD nodeId, score
                    WITH gds.util.asNode(nodeId) AS n, score
                    RETURN n.nodoId AS nodo_id, n.nombre AS nombre, n.tipo AS tipo, score
                    ORDER BY score DESC
                    """,
                    name=self._graph_name(carpeta_id),
                )
                return [dict(r) for r in result]
            finally:
                self._drop_graph(s, carpeta_id)

    def _betweenness_fallback(self, carpeta_id: int) -> List[Dict[str, Any]]:
        """Brute-force betweenness on small graphs (BFS-based)."""
        with self._driver.session() as s:
            nodes = self._nodes_for_carpeta(s, carpeta_id)
            adj = self._adjacency_for_carpeta(s, carpeta_id)
        if not nodes:
            return []
        from collections import deque

        neo_ids = [n["_neoId"] for n in nodes]
        id_set = set(neo_ids)
        betweenness: Dict[int, float] = {nid: 0.0 for nid in neo_ids}

        for src in neo_ids:
            # BFS from src
            stack: List[int] = []
            predecessors: Dict[int, List[int]] = {nid: [] for nid in neo_ids}
            sigma: Dict[int, int] = {nid: 0 for nid in neo_ids}
            sigma[src] = 1
            dist: Dict[int, int] = {nid: -1 for nid in neo_ids}
            dist[src] = 0
            queue = deque([src])
            while queue:
                v = queue.popleft()
                stack.append(v)
                for w in adj.get(v, []):
                    if w not in id_set:
                        continue
                    if dist[w] < 0:
                        dist[w] = dist[v] + 1
                        queue.append(w)
                    if dist[w] == dist[v] + 1:
                        sigma[w] += sigma[v]
                        predecessors[w].append(v)
            delta: Dict[int, float] = {nid: 0.0 for nid in neo_ids}
            while stack:
                w = stack.pop()
                for v in predecessors[w]:
                    delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w]) if sigma[w] else 0
                if w != src:
                    betweenness[w] += delta[w]

        # Normalize
        max_b = max(betweenness.values()) if betweenness else 1.0
        max_b = max_b or 1.0
        neo_map = {n["_neoId"]: n for n in nodes}
        results = []
        for nid, score in betweenness.items():
            n = neo_map[nid]
            results.append(
                {
                    "nodo_id": n["nodoId"],
                    "nombre": n["nombre"],
                    "tipo": n["tipo"],
                    "score": round(score / max_b, 6),
                }
            )
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    # ── Community Detection ──────────────────────────────────────────────

    def detect_communities(self, carpeta_id: int) -> List[Dict[str, Any]]:
        if self._check_gds():
            return self._communities_gds(carpeta_id)
        return self._communities_fallback(carpeta_id)

    def _communities_gds(self, carpeta_id: int) -> List[Dict[str, Any]]:
        with self._driver.session() as s:
            if not self._project_graph(s, carpeta_id):
                return []
            try:
                result = s.run(
                    """
                    CALL gds.louvain.stream($name)
                    YIELD nodeId, communityId
                    WITH gds.util.asNode(nodeId) AS n, communityId
                    RETURN communityId AS community_id,
                           collect({nodo_id: n.nodoId, nombre: n.nombre, tipo: n.tipo}) AS nodos
                    ORDER BY community_id
                    """,
                    name=self._graph_name(carpeta_id),
                )
                return [dict(r) for r in result]
            finally:
                self._drop_graph(s, carpeta_id)

    def _communities_fallback(self, carpeta_id: int) -> List[Dict[str, Any]]:
        """Connected components as community proxy when Louvain is unavailable."""
        with self._driver.session() as s:
            nodes = self._nodes_for_carpeta(s, carpeta_id)
            adj = self._adjacency_for_carpeta(s, carpeta_id)
        if not nodes:
            return []
        from collections import deque

        neo_map = {n["_neoId"]: n for n in nodes}
        visited: set = set()
        communities: List[Dict[str, Any]] = []
        community_id = 0

        for node in nodes:
            nid = node["_neoId"]
            if nid in visited:
                continue
            # BFS for connected component
            component: List[Dict[str, Any]] = []
            queue = deque([nid])
            visited.add(nid)
            while queue:
                v = queue.popleft()
                n = neo_map.get(v)
                if n:
                    component.append(
                        {"nodo_id": n["nodoId"], "nombre": n["nombre"], "tipo": n["tipo"]}
                    )
                for w in adj.get(v, []):
                    if w not in visited and w in neo_map:
                        visited.add(w)
                        queue.append(w)
            communities.append({"community_id": community_id, "nodos": component})
            community_id += 1

        return communities

    # ── Combined ─────────────────────────────────────────────────────────

    def get_all_metrics(self, carpeta_id: int) -> Dict[str, Any]:
        """Return pagerank + betweenness + communities in a single call."""
        return {
            "carpeta_id": carpeta_id,
            "gds_available": self._check_gds(),
            "pagerank": self.calculate_pagerank(carpeta_id),
            "betweenness": self.calculate_betweenness(carpeta_id),
            "communities": self.detect_communities(carpeta_id),
        }

    def close(self):
        try:
            self._driver.close()
        except Exception:
            pass
