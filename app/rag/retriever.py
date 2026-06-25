"""Hybrid retrieval (specs/travel-agent Task 4.2).

Combines semantic similarity with lexical (keyword) overlap via Reciprocal Rank
Fusion, then applies metadata filtering — the combination travel queries need
("cheap hostel near Shinjuku" carries both semantic and keyword signal). Runs
identically on the in-memory store (tests) and pgvector; a Postgres deployment
can push the lexical leg down to a ``tsvector`` index, but the fusion contract
here is engine-agnostic.
"""

from __future__ import annotations

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore

_RRF_K = 60  # standard RRF damping constant


def _lexical_score(query: str, doc: Document) -> int:
    q = set(query.lower().split())
    d = set(doc.page_content.lower().split())
    return len(q & d)


def hybrid_search(
    store: VectorStore,
    query: str,
    *,
    filters: dict | None = None,
    k: int = 5,
    fetch_k: int | None = None,
) -> list[Document]:
    """Return up to k documents ranked by RRF(semantic, lexical), metadata-filtered."""
    fetch_k = fetch_k or k * 4
    candidates = store.similarity_search(query, k=fetch_k)
    if not candidates:
        return []

    lexical = sorted(candidates, key=lambda d: _lexical_score(query, d), reverse=True)

    scores: dict[int, float] = {}
    for rank, doc in enumerate(candidates):  # semantic order
        scores[id(doc)] = scores.get(id(doc), 0.0) + 1.0 / (_RRF_K + rank)
    for rank, doc in enumerate(lexical):  # lexical order
        scores[id(doc)] = scores.get(id(doc), 0.0) + 1.0 / (_RRF_K + rank)

    ranked = sorted(candidates, key=lambda d: scores[id(d)], reverse=True)
    if filters:
        ranked = [
            d
            for d in ranked
            if all(d.metadata.get(key) == val for key, val in filters.items())
        ]
    return ranked[:k]
