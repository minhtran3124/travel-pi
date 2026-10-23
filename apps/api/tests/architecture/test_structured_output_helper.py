"""Guard: structured output goes through ``app.clients.llm.with_structured`` so the
provider-specific method (Anthropic rejects forced ``tool_choice``) lives in one place."""

from pathlib import Path

_APP = Path(__file__).resolve().parents[2] / "app"
_ALLOWED = _APP / "clients" / "llm.py"


def test_no_direct_with_structured_output_calls_outside_llm_client() -> None:
    offenders = [
        str(p.relative_to(_APP))
        for p in _APP.rglob("*.py")
        if p != _ALLOWED and ".with_structured_output(" in p.read_text()
    ]
    assert not offenders, (
        f"Direct .with_structured_output( calls found in: {offenders}. "
        "Use app.clients.llm.with_structured instead."
    )
