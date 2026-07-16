from app.agents.context import AgentContext, resolve_agent_context


def test_context_timezone_defaults_none():
    assert AgentContext().timezone is None


def test_resolve_agent_context_threads_timezone():
    ctx = resolve_agent_context(tier="free", timezone="Asia/Ho_Chi_Minh")
    assert ctx.timezone == "Asia/Ho_Chi_Minh"


def test_resolve_agent_context_timezone_optional():
    assert resolve_agent_context(tier="free").timezone is None
