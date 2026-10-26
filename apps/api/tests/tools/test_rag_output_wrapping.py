"""Retrieved documents arrive escaped through the real pipeline
(specs/rag-tool-output-wrapping, Task 3.1, SC-9).

``rag_tools.py`` is deliberately unchanged (design D2): the RAG tool does *not*
escape its own output. The proof that retrieved text is nonetheless covered is
that it flows through the wrapping ``"tools"``-node callable (Task 2.1) like any
other tool result — the seam escapes the whole serialized payload, ``content``
and ``metadata`` alike.

So this drives a **compiled** subagent graph (a bare ``ToolNode`` outside a graph
raises ``Missing required config key``) with ``FakeLLM`` and the vector store
faked, and asserts that a document whose ``page_content`` carries angle brackets
reaches the resulting ``ToolMessage`` escaped (``&lt;``/``&gt;``), while the JSON
structure ``rag_tools`` returns — ``results[i].content`` / ``results[i].metadata.source``
— survives wrapping intact: two results stay separate JSON objects, each still
naming its own source. Structure is checked by parsing the unwrapped payload back
to JSON, not by substring alone. No network, no real LLM, no embeddings.
"""

from __future__ import annotations

import json

from app.agents.subagents._base import build_subagent
from app.agents.tool_output import TAG_NAME, strip_wrappers
from app.clients.llm import FakeLLM
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, ToolMessage

_OPEN_PREFIX = f"<{TAG_NAME} "

# Angle brackets built inside the test file (never in a shell command). These are
# the payload a hostile document would use to forge a wrapper delimiter; after the
# seam they must survive only as character entities.
_DOC_ONE = "Visa: stay <45 days>, then <exit-before-overstay>."
_DOC_TWO = "Tip: hail a <grab> and avoid <unmetered-taxi>."


def _fake_docs() -> list[Document]:
    """Two retrieved documents with angle brackets in ``page_content`` and a
    distinct ``metadata.source`` each — the shape ``hybrid_search`` returns."""
    return [
        Document(
            page_content=_DOC_ONE,
            metadata={"source": "visa", "country": "Vietnam"},
        ),
        Document(
            page_content=_DOC_TWO,
            metadata={"source": "tip", "city": "Hanoi"},
        ),
    ]


def _fake_store(monkeypatch) -> None:
    """Fake the vector store so no embeddings are needed.

    ``rag_tools`` calls ``get_vector_store()`` then ``hybrid_search(store, …)`` at
    module scope; patching both by their names in ``app.tools.rag_tools`` means the
    tool never touches pgvector or OpenAI. ``get_vector_store`` returns a sentinel
    (only ``hybrid_search`` reads it, and that is faked too).
    """
    import app.tools.rag_tools as rt

    monkeypatch.setattr(rt, "get_vector_store", lambda: object())
    monkeypatch.setattr(
        rt, "hybrid_search", lambda store, query, filters=None, k=5: _fake_docs()
    )


def _tool_call(name: str, call_id: str, **args) -> dict:
    return {
        "content": "",
        "tool_calls": [
            {"name": name, "args": args, "id": call_id, "type": "tool_call"}
        ],
    }


def _tool_messages(result) -> list[ToolMessage]:
    return [m for m in result["messages"] if isinstance(m, ToolMessage)]


def _run_rag_agent(monkeypatch) -> ToolMessage:
    """Drive one compiled concierge-style subagent turn that calls the real
    ``search_travel_knowledge`` tool (with a faked store) and return its
    resulting ``ToolMessage``."""
    _fake_store(monkeypatch)
    from app.tools.rag_tools import search_travel_knowledge

    llm = FakeLLM(
        responses=[
            _tool_call("search_travel_knowledge", "c1", query="visa for Vietnam"),
            "done",
        ]
    )
    agent = build_subagent(
        "concierge", [search_travel_knowledge], lambda _=None: llm, "p"
    )
    out = agent.invoke({"messages": [HumanMessage("do I need a visa?")]})
    tms = _tool_messages(out)
    assert len(tms) == 1, "exactly one ToolMessage per tool call (upsert-by-id)"
    return tms[0]


def test_retrieved_document_angle_brackets_arrive_escaped(monkeypatch):
    """A retrieved document's angle brackets reach the model escaped, and the
    payload cannot forge a wrapper delimiter."""
    tm = _run_rag_agent(monkeypatch)

    assert tm.content.startswith(_OPEN_PREFIX)
    # Escaped, not deleted — every angle bracket from both documents.
    assert "&lt;45 days&gt;" in tm.content
    assert "&lt;exit-before-overstay&gt;" in tm.content
    assert "&lt;grab&gt;" in tm.content
    assert "&lt;unmetered-taxi&gt;" in tm.content
    # The document's own literal angle brackets are gone; only the wrapper's own
    # tags may carry a raw '<'/'>'. Check the document substrings specifically so
    # the assertion is not confused by the wrapper delimiters themselves.
    assert "<45 days>" not in tm.content
    assert "<exit-before-overstay>" not in tm.content
    assert "<grab>" not in tm.content
    assert "<unmetered-taxi>" not in tm.content


def test_two_results_stay_separate_json_objects_each_with_its_source(monkeypatch):
    """Escaping the whole serialized payload does not corrupt or merge the JSON
    ``rag_tools`` returns: two results remain separate objects, each keeping its
    own ``metadata.source`` and its escaped ``content``.

    Parsed back from JSON (structure), not matched as a substring — the document
    boundary is the JSON object per result, and it must survive the wrap."""
    tm = _run_rag_agent(monkeypatch)

    # strip_wrappers removes the wrapper tags but does NOT unescape, so the escaped
    # payload is still valid JSON (only '<'/'>' were entity-encoded, never the
    # structural quotes/braces json.dumps produced).
    payload = strip_wrappers(tm.content)
    parsed = json.loads(payload)

    assert parsed["count"] == 2
    assert isinstance(parsed["results"], list)
    assert len(parsed["results"]) == 2

    # Each result is its own object still carrying content + metadata.source.
    for r in parsed["results"]:
        assert set(r) == {"content", "metadata"}
        assert "source" in r["metadata"]

    # The two sources stayed distinct and correctly paired with their document.
    by_source = {r["metadata"]["source"]: r for r in parsed["results"]}
    assert set(by_source) == {"visa", "tip"}
    assert by_source["visa"]["metadata"]["country"] == "Vietnam"
    assert by_source["tip"]["metadata"]["city"] == "Hanoi"
    # Escaping reached the content inside each separate object, not just the
    # payload as a whole.
    assert "&lt;45 days&gt;" in by_source["visa"]["content"]
    assert "&lt;grab&gt;" in by_source["tip"]["content"]
    assert "<" not in by_source["visa"]["content"]
    assert "<" not in by_source["tip"]["content"]
