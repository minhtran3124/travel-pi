"""Retrieval-augmented generation over visa + local-tips seed content.

Re-introduced by ``specs/travel-knowledge-rag`` (the old places-based RAG was
removed by ``specs/remove-rag-feature``). This package owns the corpus rendering
(``ingest``), hybrid retrieval (``retriever``) and the vector-store selection
(``embeddings``); the concierge-facing tool lives in ``app/tools/rag_tools.py``.
"""
