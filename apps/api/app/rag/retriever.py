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
from langchain_core.vectorstores import InMemoryVectorStore, VectorStore

_RRF_K = 60  # standard RRF damping constant


def _store_filter_kwargs(store: VectorStore, filters: dict | None) -> dict:
    """Return the ``filter=`` kwargs appropriate for the given store implementation.

    - ``InMemoryVectorStore`` expects a callable predicate.
    - ``PGVector`` (and other stores) expect a metadata dict.
    Passing no filter returns an empty dict so the call site can always do
    ``store.similarity_search(query, k=n, **kwargs)`` uniformly.

    :param store: The vector store the filter will be passed to.
    :param filters: Metadata filters to apply, or ``None``.
    :return: The ``filter=`` kwargs for ``similarity_search``.
    """
    if not filters:
        return {}
    if isinstance(store, InMemoryVectorStore):
        return {
            "filter": lambda d: all(d.metadata.get(k) == v for k, v in filters.items())
        }
    return {"filter": filters}


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
    """Return up to k documents ranked by RRF(semantic, lexical), metadata-filtered.

    The metadata filter is pushed into ``similarity_search`` so the candidate pool
    is already filtered before RRF fusion.  This avoids result starvation when
    matching documents are sparse in the semantic top-N.

    :param store: The vector store to search.
    :param query: The search query.
    :param filters: Metadata filters to apply.
    :param k: Number of ranked documents to return.
    :param fetch_k: Number of candidates to fetch before fusion; defaults to ``k * 4``.
    :return: Up to ``k`` documents ranked by RRF score.
    """
    fetch_k = fetch_k or k * 4
    filter_kwargs = _store_filter_kwargs(store, filters)
    candidates = store.similarity_search(query, k=fetch_k, **filter_kwargs)
    if not candidates:
        return []

    lexical = sorted(candidates, key=lambda d: _lexical_score(query, d), reverse=True)

    scores: dict[int, float] = {}
    for rank, doc in enumerate(candidates):  # semantic order
        scores[id(doc)] = scores.get(id(doc), 0.0) + 1.0 / (_RRF_K + rank)
    for rank, doc in enumerate(lexical):  # lexical order
        scores[id(doc)] = scores.get(id(doc), 0.0) + 1.0 / (_RRF_K + rank)

    ranked = sorted(candidates, key=lambda d: scores[id(d)], reverse=True)
    return ranked[:k]
