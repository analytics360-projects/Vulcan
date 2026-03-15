"""Social Graph service — builds relationship graphs from SANS results"""
import re
import hashlib
from collections import defaultdict
from typing import List, Dict, Set, Tuple

from config import logger
from modules.social_graph.models import (
    SocialGraphNode,
    SocialGraphEdge,
    ProfileInput,
    BuildGraphResponse,
)


# Platform colors (informational, stored in metadata for frontend)
PLATFORM_COLORS = {
    "facebook": "#1877F2",
    "instagram": "#E1306C",
    "twitter": "#1DA1F2",
    "tiktok": "#00f2ea",
    "telegram": "#0088cc",
    "marketplace": "#ff9800",
    "forum": "#FF4500",
    "web": "#00e5ff",
}


def _node_id(name: str, platform: str) -> str:
    """Deterministic node ID from name + platform."""
    raw = f"{name.lower().strip()}|{platform.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _extract_mentions(text: str) -> List[str]:
    """Extract @mentions from text."""
    if not text:
        return []
    return re.findall(r"@([\w.]+)", text)


def _extract_keywords(text: str, min_len: int = 4) -> Set[str]:
    """Extract significant words from text for co-occurrence analysis."""
    if not text:
        return set()
    words = re.findall(r"\b[a-záéíóúñü]+\b", text.lower())
    # Filter stopwords and short words
    stopwords = {
        "para", "como", "esta", "este", "esto", "esos", "esas", "pero", "porque",
        "cuando", "donde", "quien", "cual", "entre", "desde", "sobre", "hasta",
        "tiene", "hacer", "sido", "puede", "todos", "todas", "otro", "otra",
        "también", "después", "antes", "mismo", "cada", "mucho", "poco",
        "algo", "nada", "todo", "bien", "solo", "aquí", "allí", "ahora",
        "the", "and", "for", "are", "but", "not", "you", "all", "can",
        "with", "this", "that", "from", "have", "been", "they", "will",
        "more", "just", "some", "than", "what", "when", "who", "how",
    }
    return {w for w in words if len(w) >= min_len and w not in stopwords}


class SocialGraphService:
    """Builds social relationship graphs from discovered profiles."""

    def build_from_sans_results(self, profiles: List[ProfileInput]) -> BuildGraphResponse:
        """
        Build a social graph from SANS-discovered profiles.

        Strategy:
        1. Create a node for each profile
        2. Create edges based on:
           - Co-comments: profiles that comment on same topics / share keywords
           - Mentions: @mentions linking profiles
           - Shared content: overlapping significant keywords in posts
        3. Detect communities via connected components
        """
        nodes: List[SocialGraphNode] = []
        edges: List[SocialGraphEdge] = []
        node_ids: Dict[str, SocialGraphNode] = {}

        # 1. Create profile nodes
        for profile in profiles:
            nid = _node_id(profile.name, profile.platform)
            if nid in node_ids:
                continue

            platform_lower = profile.platform.lower()
            node = SocialGraphNode(
                id=nid,
                label=profile.name,
                type="profile",
                platform=profile.platform,
                url=profile.url,
                metadata={
                    "post_count": len(profile.posts),
                    "total_reactions": sum(p.reactions for p in profile.posts),
                    "total_comments": sum(p.comments for p in profile.posts),
                    "color": PLATFORM_COLORS.get(platform_lower, "#00e5ff"),
                },
            )
            nodes.append(node)
            node_ids[nid] = node

        # 2. Build keyword index per profile for co-occurrence
        profile_keywords: Dict[str, Set[str]] = {}
        profile_mentions: Dict[str, Set[str]] = {}

        for profile in profiles:
            nid = _node_id(profile.name, profile.platform)
            all_keywords: Set[str] = set()
            all_mentions: Set[str] = set()

            for post in profile.posts:
                all_keywords.update(_extract_keywords(post.text))
                all_mentions.update(_extract_mentions(post.text))

                # If post has an author different from profile, create an interaction edge
                if post.author and post.author.lower().strip() != profile.name.lower().strip():
                    author_nid = _node_id(post.author, profile.platform)
                    if author_nid not in node_ids:
                        author_node = SocialGraphNode(
                            id=author_nid,
                            label=post.author,
                            type="profile",
                            platform=profile.platform,
                            metadata={"color": PLATFORM_COLORS.get(profile.platform.lower(), "#00e5ff")},
                        )
                        nodes.append(author_node)
                        node_ids[author_nid] = author_node

                    edges.append(SocialGraphEdge(
                        source=author_nid,
                        target=nid,
                        relation="interacts",
                        weight=1.0,
                    ))

            profile_keywords[nid] = all_keywords
            profile_mentions[nid] = all_mentions

        # 3. Mention-based edges
        name_to_nid: Dict[str, str] = {}
        for profile in profiles:
            nid = _node_id(profile.name, profile.platform)
            name_to_nid[profile.name.lower().strip()] = nid
            # Also index without spaces
            name_to_nid[profile.name.lower().replace(" ", "")] = nid

        for nid, mentions in profile_mentions.items():
            for mention in mentions:
                mention_lower = mention.lower()
                target_nid = name_to_nid.get(mention_lower)
                if target_nid and target_nid != nid:
                    edges.append(SocialGraphEdge(
                        source=nid,
                        target=target_nid,
                        relation="mentioned",
                        weight=1.5,
                    ))

        # 4. Keyword co-occurrence edges (shared content)
        nids = list(profile_keywords.keys())
        for i in range(len(nids)):
            for j in range(i + 1, len(nids)):
                common = profile_keywords[nids[i]] & profile_keywords[nids[j]]
                if len(common) >= 3:
                    weight = min(len(common) / 5.0, 3.0)
                    edges.append(SocialGraphEdge(
                        source=nids[i],
                        target=nids[j],
                        relation="interacts",
                        weight=round(weight, 2),
                    ))

        # 5. Deduplicate edges (keep highest weight)
        edge_map: Dict[Tuple[str, str, str], SocialGraphEdge] = {}
        for edge in edges:
            key = (min(edge.source, edge.target), max(edge.source, edge.target), edge.relation)
            if key not in edge_map or edge.weight > edge_map[key].weight:
                edge_map[key] = edge
        edges = list(edge_map.values())

        # 6. Community detection via connected components (union-find)
        parent: Dict[str, str] = {n.id: n.id for n in nodes}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for edge in edges:
            if edge.source in parent and edge.target in parent:
                union(edge.source, edge.target)

        communities = len(set(find(nid) for nid in parent))

        logger.info(f"Social graph built: {len(nodes)} nodes, {len(edges)} edges, {communities} communities")

        return BuildGraphResponse(
            nodes=nodes,
            edges=edges,
            communities=communities,
        )


# Singleton
social_graph_service = SocialGraphService()
