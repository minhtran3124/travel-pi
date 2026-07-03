"""_build_chat_model disables SDK-level retry so the graph is the single owner."""

from app.clients import llm as llm_mod


def test_build_chat_model_sets_max_retries_zero(monkeypatch):
    captured = {}

    def fake_init(model, **kwargs):
        captured.update(kwargs)
        captured["model"] = model
        return object()

    monkeypatch.setattr(llm_mod, "init_chat_model", fake_init)
    llm_mod._build_chat_model("openai", "gpt-4o")
    assert captured["max_retries"] == 0
