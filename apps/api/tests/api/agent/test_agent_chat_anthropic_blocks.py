"""/agent/chat must return the text of a Claude block-list reply, not the raw list (#254)."""

from fastapi.testclient import TestClient
from tests.api.agent.test_agent_chat import _make_app
from tests.fixtures.anthropic_llm import anthropic_message


def test_chat_reply_is_text_for_anthropic_content_blocks(tmp_path):
    app = _make_app(
        tmp_path,
        "concierge",
        "unused",
        responses=[anthropic_message("Hello")] * 6,
    )
    with TestClient(app) as c:
        resp = c.post(
            "/agent/chat", json={"message": "hi", "conversation_id": "7d0f2f5e-3b0a-4c1e-9a43-0f6a5e1c9b11"}
        )
    assert resp.status_code == 200, resp.text
    reply = resp.json()["reply"]
    assert reply == "Hello"
    assert "thinking" not in reply
