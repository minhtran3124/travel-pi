"""Hybrid retrieval combining semantic and lexical overlap via Reciprocal Rank Fusion.

The metadata filter is pushed into ``similarity_search`` so the candidate pool is filtered before RRF
fusion, avoiding result starvation when matching documents are sparse in the semantic top-N.
"""

from __future__ import annotations

import re

from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore, VectorStore

_RRF_K = 60  # standard RRF damping constant
_WORD_RE = re.compile(r"\w+")


def _tokenize(text: str) -> set[str]:
    """Lowercase word tokens split on ``\\w+`` so punctuated forms ("Vietnam?") still tokenize and the
    lexical leg fires on natural questions."""
    return set(_WORD_RE.findall(text.lower()))


def _store_filter_kwargs(store: VectorStore, filters: dict | None) -> dict:
    """Return the ``filter=`` kwargs for the store: ``InMemoryVectorStore`` expects a callable predicate,
    ``PGVector`` a metadata dict; no filter returns an empty dict for a uniform call site."""
    if not filters:
        return {}
    if isinstance(store, InMemoryVectorStore):
        return {
            "filter": lambda d: all(d.metadata.get(k) == v for k, v in filters.items())
        }
    return {"filter": filters}


def _lexical_score(query: str, doc: Document) -> int:
    """Token-overlap count between *query* and the document (case-insensitive)."""
    return len(_tokenize(query) & _tokenize(doc.page_content))


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
