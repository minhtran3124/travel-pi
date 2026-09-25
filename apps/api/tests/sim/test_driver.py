"""Driver-loop tests (offline: fake claude_cli, fake bus, httpx.MockTransport)."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from sim import claude_cli, driver
from sim.personas import Persona

BASE_URL = "http://sim"


def _persona(**over) -> Persona:
    base = {
        "id": "p1",
        "name": "Trav",
        "language": "en",
        "budget": {"amount": 1000, "currency": "USD"},
        "trip_goal": {"destination": "Tokyo", "party_size": 2},
        "style": "terse",
        "will_book": True,
        "max_turns": 5,
    }
    base.update(over)
    return Persona.model_validate(base)


class _FakeBus:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def publish(self, event: dict) -> None:
        self.events.append(dict(event))

    def types(self) -> list[str]:
        return [e["type"] for e in self.events]


class _FakeKeys:
    def token_for(self, persona_id: str) -> str:
        return f"tok-{persona_id}"


def _sse(events: list[tuple[str, dict]]) -> bytes:
    chunks = []
    for name, data in events:
        chunks.append(f"event: {name}\ndata: {json.dumps(data)}\n\n")
    return "".join(chunks).encode()


def _fake_claude(scripts: dict[str, list[dict]], default: dict | None = None):
    calls = {"n": 0}

    async def run(system_prompt, user_prompt, schema, model=None, timeout=120):
        calls["n"] += 1
        # The persona id is embedded by the system prompt via the persona card;
        # tests key scripts on a marker the prompt carries.
        for pid, script in scripts.items():
            if f"marker:{pid}" in system_prompt:
                if script:
                    return script.pop(0)
                return {"message": "", "intent_done": True}
        if default is not None:
            return dict(default)
        return {"message": "", "intent_done": True}

    return run, calls


def _patch(monkeypatch, run, quota=None):
    if quota is None:
        quota = claude_cli.Quota(0.1, 0.1, None)
    monkeypatch.setattr(claude_cli, "run", run)
    monkeypatch.setattr(claude_cli, "last_quota", quota)


def _run(coro):
    return asyncio.run(coro)


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# The traveller system prompt embeds the persona name; tests tag personas with a
# marker in the name so the fake claude can select the right script.
def _tagged(pid, **over):
    over.setdefault("name", f"marker:{pid}")
    return _persona(id=pid, **over)


def test_a_session_stops_on_intent_done(monkeypatch):
    run, calls = _fake_claude(
        {
            "a1": [
                {"message": "hi", "intent_done": False},
                {"message": "", "intent_done": True},
            ]
        }
    )
    _patch(monkeypatch, run)

    def handler(request):
        return httpx.Response(
            200,
            content=_sse(
                [
                    ("start", {"conversation_id": "conv-1"}),
                    ("token", {"content": "Hello "}),
                    ("token", {"content": "there"}),
                    ("done", {"usage": {"total_tokens": 10}}),
                ]
            ),
        )

    async def go():
        async with _client(handler) as client:
            return await driver.run_batch(
                [_tagged("a1")], 1, BASE_URL, _FakeKeys(), _FakeBus(), client, None
            )

    result = _run(go())
    session = result.sessions[0]
    assert session.status == "done"
    assert session.conversation_id == "conv-1"
    assert session.turns == [
        {"role": "user", "text": "hi"},
        {"role": "bot", "text": "Hello there"},
    ]
    assert session.usage == {"total_tokens": 10}
    assert result.status == "ok"
    assert calls["n"] == 2


def test_b_session_stops_at_max_turns(monkeypatch):
    run, _ = _fake_claude({}, default={"message": "more", "intent_done": False})
    _patch(monkeypatch, run)

    def handler(request):
        return httpx.Response(
            200,
            content=_sse(
                [
                    ("start", {"conversation_id": "c"}),
                    ("token", {"content": "ok"}),
                    ("done", {}),
                ]
            ),
        )

    async def go():
        async with _client(handler) as client:
            return await driver.run_batch(
                [_tagged("b1", max_turns=4)],
                1,
                BASE_URL,
                _FakeKeys(),
                _FakeBus(),
                client,
                None,
            )

    result = _run(go())
    session = result.sessions[0]
    assert session.status == "max_turns"
    assert len([t for t in session.turns if t["role"] == "user"]) == 4


def test_c_plan_approval_resume_uses_will_book_and_conversation_id(monkeypatch):
    run, _ = _fake_claude(
        {
            "c1": [
                {"message": "book it", "intent_done": False},
                {"message": "", "intent_done": True},
            ]
        }
    )
    _patch(monkeypatch, run)
    seen: list[dict] = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        if "resume" in body:
            return httpx.Response(
                200, content=_sse([("token", {"content": "Booked"}), ("done", {})])
            )
        return httpx.Response(
            200,
            content=_sse(
                [
                    ("start", {"conversation_id": "conv-9"}),
                    ("interrupt", {"payload": {"type": "plan_approval", "draft": "x"}}),
                    ("done", {}),
                ]
            ),
        )

    async def go():
        async with _client(handler) as client:
            return await driver.run_batch(
                [_tagged("c1", will_book=True)],
                1,
                BASE_URL,
                _FakeKeys(),
                _FakeBus(),
                client,
                None,
            )

    result = _run(go())
    resume_bodies = [b for b in seen if "resume" in b]
    assert len(resume_bodies) == 1
    assert resume_bodies[0]["resume"]["approved"] is True
    assert resume_bodies[0]["conversation_id"] == "conv-9"
    assert {"role": "user", "text": "[resume approved=True]"} in result.sessions[
        0
    ].turns


def test_d_peak_in_flight_never_exceeds_parallel(monkeypatch):
    state = {"cur": 0, "max": 0}

    async def run(system_prompt, user_prompt, schema, model=None, timeout=120):
        state["cur"] += 1
        state["max"] = max(state["max"], state["cur"])
        await asyncio.sleep(0.02)
        state["cur"] -= 1
        return {"message": "hi", "intent_done": user_prompt.count("user:") >= 1}

    _patch(monkeypatch, run)

    def handler(request):
        return httpx.Response(
            200, content=_sse([("start", {"conversation_id": "c"}), ("done", {})])
        )

    personas = [_tagged(f"d{i}") for i in range(5)]

    async def go():
        async with _client(handler) as client:
            return await driver.run_batch(
                personas, 2, BASE_URL, _FakeKeys(), _FakeBus(), client, None
            )

    result = _run(go())
    assert state["max"] == 2
    assert all(s.status == "done" for s in result.sessions)


def test_e_quota_ceiling_blocks_all_admission(monkeypatch):
    run, calls = _fake_claude({}, default={"message": "hi", "intent_done": False})
    _patch(monkeypatch, run, quota=claude_cli.Quota(0.9, 0.2, None))

    def handler(request):  # pragma: no cover - never reached
        raise AssertionError("no request should be sent when over ceiling")

    personas = [_tagged(f"e{i}") for i in range(3)]

    async def go():
        async with _client(handler) as client:
            return await driver.run_batch(
                personas, 2, BASE_URL, _FakeKeys(), _FakeBus(), client, None
            )

    result = _run(go())
    assert result.status == "quota"
    assert result.claude_calls == 0
    assert calls["n"] == 0
    assert all(s.status == "quota" for s in result.sessions)


def test_f_401_aborts_batch_as_auth_misconfigured(monkeypatch):
    run, _ = _fake_claude({}, default={"message": "hi", "intent_done": False})
    _patch(monkeypatch, run)

    def handler(request):
        return httpx.Response(401, json={"detail": "no"})

    personas = [_tagged("f1"), _tagged("f2")]

    async def go():
        async with _client(handler) as client:
            return await driver.run_batch(
                personas, 2, BASE_URL, _FakeKeys(), _FakeBus(), client, None
            )

    result = _run(go())
    assert result.status == "auth_misconfigured"


def test_g_429_aborts_batch_as_tier_misconfigured(monkeypatch):
    run, _ = _fake_claude({}, default={"message": "hi", "intent_done": False})
    _patch(monkeypatch, run)

    def handler(request):
        return httpx.Response(429, json={"detail": "slow down"})

    personas = [_tagged("g1"), _tagged("g2")]

    async def go():
        async with _client(handler) as client:
            return await driver.run_batch(
                personas, 2, BASE_URL, _FakeKeys(), _FakeBus(), client, None
            )

    result = _run(go())
    assert result.status == "tier_misconfigured"


def test_h_500_marks_one_session_bot_error_others_finish(monkeypatch):
    run, _ = _fake_claude(
        {
            "good": [
                {"message": "hi", "intent_done": False},
                {"message": "", "intent_done": True},
            ],
            "bad": [{"message": "hi", "intent_done": False}],
        }
    )
    _patch(monkeypatch, run)

    def handler(request):
        if "bad" in request.headers.get("Authorization", ""):
            return httpx.Response(500, json={"detail": "boom"})
        return httpx.Response(
            200,
            content=_sse(
                [
                    ("start", {"conversation_id": "c"}),
                    ("token", {"content": "ok"}),
                    ("done", {}),
                ]
            ),
        )

    personas = [_tagged("good"), _tagged("bad")]

    async def go():
        async with _client(handler) as client:
            return await driver.run_batch(
                personas, 2, BASE_URL, _FakeKeys(), _FakeBus(), client, None
            )

    result = _run(go())
    by_id = {s.persona.id: s for s in result.sessions}
    assert by_id["bad"].status == "bot_error"
    assert by_id["bad"].error["code"] == "http_500"
    assert by_id["good"].status == "done"
    assert result.status == "ok"


@pytest.fixture(autouse=True)
def _reset_quota():
    original = claude_cli.last_quota
    yield
    claude_cli.last_quota = original
