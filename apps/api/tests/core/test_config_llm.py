"""AI/agent settings (specs/travel-agent Task 0.2).

The agent layer must run zero-config: every LLM/agent setting has a safe default
and no API key is required, so local dev and CI (which inject a fake client)
never touch the network. These tests pin that contract.
"""

import pytest
from app.core.config import Settings
from pydantic import ValidationError


def test_llm_defaults_require_no_key():
    s = Settings()
    # Provider-agnostic default is OpenAI.
    assert s.llm_provider == "openai"
    assert s.llm_model == "gpt-5"
    assert s.fast_llm_model == "gpt-5-mini"
    assert s.embedding_model == "text-embedding-3-small"
    # No key is mandatory — the suite runs without secrets.
    assert s.openai_api_key is None
    assert s.anthropic_api_key is None
    assert s.google_api_key is None


def test_langfuse_disabled_by_default():
    s = Settings()
    assert s.langfuse_enabled is False
    assert s.langfuse_public_key is None
    assert s.langfuse_secret_key is None
    assert s.langfuse_host == "https://cloud.langfuse.com"


def test_agent_runtime_defaults():
    s = Settings()
    assert s.agent_recursion_limit == 25
    assert s.summarize_threshold == 20


def test_provider_rejects_unknown():
    with pytest.raises(ValidationError):
        Settings(llm_provider="bedrock")


@pytest.mark.parametrize(
    "provider", ["openai", "anthropic", "google_genai", "clinepass", "claude"]
)
def test_provider_accepts_known_profiles(provider):
    # Both raw SDK names and gateway profiles are valid provider values.
    assert Settings(llm_provider=provider).llm_provider == provider


def test_gateway_api_key_fields_default_to_none():
    s = Settings()
    assert s.clinepass_api_key is None
    assert s.claude_api_key is None
