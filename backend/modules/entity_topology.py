"""
Entity topology — co-occurrence graph extraction.
Called from ingestion._heavy_work() after entity extraction.

Co-occurrence definition:
  Two entities "co-occur" if they appear in the same chunk.
  Weight = number of chunks where both entities appear together.
  Min weight = 2 (single co-occurrence is noise).

Output: list of (entity_a_text, entity_b_text, weight) tuples.
Stored in EntityRelationDB, queried via /vaults/{id}/graph.

Complexity: O(k²) per chunk where k = entities per chunk (typically 2-8).
For typical documents: O(chunks × avg_k²) ≈ O(n × 16) — linear in practice.
"""
import logging
from collections import defaultdict
from itertools import combinations

logger = logging.getLogger(__name__)

# Minimum co-occurrence count to persist a relationship
MIN_EDGE_WEIGHT = 2


def build_cooccurrence_graph(
    chunks: list[dict],
    entities: list[dict],
) -> list[tuple[str, str, int]]:
    """
    Build entity co-occurrence graph from chunks and extracted entities.

    Args:
        chunks: list of chunk dicts with 'content' key
        entities: list of entity dicts with 'text' and 'type' keys

    Returns:
        list of (entity_a, entity_b, weight) tuples, weight >= MIN_EDGE_WEIGHT
    """
    if not chunks or not entities:
        return []

    entity_texts = [e["text"].lower() for e in entities]
    if len(entity_texts) < 2:
        return []

    # Count co-occurrences: (a, b) → count
    # Canonical form: always (smaller, larger) alphabetically
    edge_counts: dict[tuple[str, str], int] = defaultdict(int)

    for chunk in chunks:
        content_lower = chunk["content"].lower()

        # Which entities appear in this chunk?
        present = [
            e_text for e_text in entity_texts
            if e_text in content_lower
        ]

        if len(present) < 2:
            continue

        # All pairs in this chunk
        for a, b in combinations(sorted(set(present)), 2):
            edge_counts[(a, b)] += 1

    # Filter weak edges
    strong_edges = [
        (a, b, w)
        for (a, b), w in edge_counts.items()
        if w >= MIN_EDGE_WEIGHT
    ]

    strong_edges.sort(key=lambda x: -x[2])

    if strong_edges:
        logger.debug(f"Entity graph: {len(strong_edges)} edges from {len(entities)} entities")

    return strong_edges[:200]  # cap to prevent DB bloat on large docs
