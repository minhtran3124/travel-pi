"""``POST /agent/feedback`` contract — specs/user-feedback-v1 Task 3.2 (SC-6).

Statuses per DESIGN §5.2: 201 new event, 200 replay / retract no-op, 401, 404
(one non-enumerating body), 409 (key reuse with another payload, invalid
transition), 422 (schema, Idempotency-Key mismatch). Seeds rows through the
repositories, mirrors the ``test_claim.py`` harness (no real JWT; the optional
auth dependency is overridden).
"""

from __future__ import annotations

import uuid

import pytest
from app.core.auth import AuthUser, get_current_user_optional
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.session import get_session
from app.main import create_app
from app.repositories.agent_run import AgentRunRepository
from app.repositories.conversation import ConversationRepository
from app.repositories.feedback import FeedbackRepository
from app.routers.agent import get_travel_graph
from app.services import feedback_service
from fastapi.testclient import TestClient

OWNER = "feedback-owner-uid"
STRANGER = "feedback-stranger-uid"
ANON = "anon-local-feedback-uuid"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def make_app(tmp_path, *, auth_user_id: str | None):
    """App over an isolated SQLite file; ``auth_user_id=None`` → anonymous caller."""
    url = f"sqlite:///{tmp_path / 'feedback.db'}"
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    app = create_app()

    def _override_session():
        s = get_session_factory(url)()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_travel_graph] = lambda: None
    user = (
        AuthUser(id=auth_user_id, email=None, role=None, claims={})
        if auth_user_id
        else None
    )
    app.dependency_overrides[get_current_user_optional] = lambda: user
    return app, get_session_factory(url)


def seed_message(
    sf, *, owner: str, role: str = "assistant", run_status: str | None = "completed"
):
    """Seed conversation + (optionally linked, optionally finished) run + message.

    :return: The message id.
    """
    conv = ConversationRepository(sf).create_conversation(user_id=owner)
    run_id: str | None = None
    if run_status is not None:
        run_id = str(uuid.uuid4())
        runs = AgentRunRepository(sf)
        runs.start(
            run_id,
            user_id=owner,
            conversation_id=conv.id,
            thread_id=f"thread-{conv.id}",
            trip_id=None,
            channel="chat",
            kind="turn",
            started_at="2026-09-12T00:00:00+00:00",
        )
        if run_status != "running":
            runs.finish(
                run_id,
                status=run_status,
                current_flow=None,
                finished_at="2026-09-12T00:00:01+00:00",
                metrics={},
            )
    msg = ConversationRepository(sf).append_message(
        conversation_id=conv.id, role=role, content="reply", agent_run_id=run_id
    )
    return msg.id


def body(message_id: str, action: str = "set_rating", **fields) -> dict:
    payload = {
        "client_event_id": str(uuid.uuid4()),
        "assistant_message_id": message_id,
        "action": action,
    }
    if action == "set_rating" and "rating" not in fields:
        payload["rating"] = "helpful"
    payload.update(fields)
    return payload


@pytest.fixture(params=["authenticated", "anonymous"])
def actor(request, tmp_path):
    """Both identity paths: JWT sub, or ``anonymous_user_id`` in the body."""
    if request.param == "authenticated":
        app, sf = make_app(tmp_path, auth_user_id=OWNER)
        extra: dict = {}
    else:
        app, sf = make_app(tmp_path, auth_user_id=None)
        extra = {"anonymous_user_id": ANON}
    owner = OWNER if request.param == "authenticated" else ANON
    with TestClient(app) as client:
        yield client, sf, owner, extra


def post(client, payload: dict, headers: dict | None = None):
    return client.post("/agent/feedback", json=payload, headers=headers or {})


# ---------------------------------------------------------------------------
# Happy path — full lifecycle on one message, both identity paths
# ---------------------------------------------------------------------------


def test_lifecycle_set_replay_change_detail_retract(actor):
    client, sf, owner, extra = actor
    mid = seed_message(sf, owner=owner)

    # set helpful → 201
    first = body(mid, **extra)
    r = post(client, first)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["replayed"] is False
    assert data["assistant_message_id"] == mid
    assert data["effective_feedback"]["rating"] == "helpful"
    assert data["effective_feedback"]["rating_event_id"] == data["feedback_event_id"]
    assert data["effective_feedback"]["comment_present"] is False

    # replay same key + same body → 200 replayed, log unchanged
    r2 = post(client, first)
    assert r2.status_code == 200
    assert r2.json()["replayed"] is True
    assert r2.json()["feedback_event_id"] == data["feedback_event_id"]

    # change to not_helpful → 201, supersedes the helpful event
    r3 = post(client, body(mid, rating="not_helpful", **extra))
    assert r3.status_code == 201
    assert r3.json()["effective_feedback"]["rating"] == "not_helpful"

    # add_detail with reason → 201, folded into the negative rating
    r4 = post(
        client,
        body(
            mid,
            action="add_detail",
            reason_code="incorrect",
            comment="  The museum is closed on Tuesdays.  ",
            **extra,
        ),
    )
    assert r4.status_code == 201
    eff = r4.json()["effective_feedback"]
    assert eff["rating"] == "not_helpful"
    assert eff["reason_code"] == "incorrect"
    assert eff["comment_present"] is True
    assert eff["rating_event_id"] == r3.json()["feedback_event_id"]
    assert "comment" not in eff  # body never echoed

    # retract → 201, effective feedback cleared
    r5 = post(client, body(mid, action="retract_rating", **extra))
    assert r5.status_code == 201
    assert r5.json()["effective_feedback"] is None

    # second retract → 200 documented no-op
    r6 = post(client, body(mid, action="retract_rating", **extra))
    assert r6.status_code == 200
    assert r6.json()["effective_feedback"] is None
    assert r6.json()["replayed"] is False

    # the log is append-only: one row per accepted request, none for the replay
    with sf() as s:
        from app.db import models

        rows = (
            s.query(models.FeedbackEvent)
            .order_by(models.FeedbackEvent.created_at)
            .all()
        )
    assert [row.action for row in rows] == [
        "set_rating",
        "set_rating",
        "add_detail",
        "retract_rating",
        "retract_rating",
    ]
    assert rows[1].supersedes_event_id == rows[0].id
    assert all(row.user_id == owner for row in rows)
    assert FeedbackRepository(sf).effective_for([mid])[mid] is None


def test_anonymous_id_ignored_when_authenticated(tmp_path):
    app, sf = make_app(tmp_path, auth_user_id=OWNER)
    mid = seed_message(sf, owner=OWNER)
    with TestClient(app) as client:
        r = post(client, body(mid, anonymous_user_id=STRANGER))
    assert r.status_code == 201
    with sf() as s:
        from app.db import models

        assert s.query(models.FeedbackEvent).one().user_id == OWNER


# ---------------------------------------------------------------------------
# 401 / 404 / 409 / 422
# ---------------------------------------------------------------------------


def test_no_principal_is_401(tmp_path):
    app, sf = make_app(tmp_path, auth_user_id=None)
    mid = seed_message(sf, owner=ANON)
    with TestClient(app) as client:
        r = post(client, body(mid))
    assert r.status_code == 401
    assert r.json()["error"] == "AuthError"


def test_non_rateable_targets_share_one_404_body(tmp_path):
    app, sf = make_app(tmp_path, auth_user_id=OWNER)
    targets = {
        "foreign": seed_message(sf, owner=STRANGER),
        "user_role": seed_message(sf, owner=OWNER, role="user"),
        "unknown": str(uuid.uuid4()),
        "failed_run": seed_message(sf, owner=OWNER, run_status="failed"),
        "running_run": seed_message(sf, owner=OWNER, run_status="running"),
        "unlinked": seed_message(sf, owner=OWNER, run_status=None),
    }
    bodies: dict[str, bytes] = {}
    with TestClient(app) as client:
        for name, mid in targets.items():
            # Pin the request id so the envelopes are byte-comparable.
            r = post(client, body(mid), headers={"X-Request-ID": "fixed-rid"})
            assert r.status_code == 404, (name, r.text)
            bodies[name] = r.content
    assert len(set(bodies.values())) == 1, bodies
    assert b"not rateable" in bodies["foreign"]
    # Nothing was written for any rejected request.
    with sf() as s:
        from app.db import models

        assert s.query(models.FeedbackEvent).count() == 0


def test_same_key_different_body_is_409(actor):
    client, sf, owner, extra = actor
    mid = seed_message(sf, owner=owner)
    first = body(mid, **extra)
    assert post(client, first).status_code == 201
    changed = {**first, "rating": "not_helpful"}
    r = post(client, changed)
    assert r.status_code == 409
    assert r.json()["error"] == "ConflictError"
    # Conflict happens before the target lookup and changes nothing.
    assert FeedbackRepository(sf).effective_for([mid])[mid].rating == "helpful"


def test_add_detail_without_negative_rating_is_409(actor):
    client, sf, owner, extra = actor
    mid = seed_message(sf, owner=owner)
    # No rating yet.
    r = post(client, body(mid, action="add_detail", reason_code="other", **extra))
    assert r.status_code == 409
    # Helpful rating active.
    assert post(client, body(mid, **extra)).status_code == 201
    r = post(client, body(mid, action="add_detail", reason_code="other", **extra))
    assert r.status_code == 409
    assert r.json()["error"] == "ConflictError"


@pytest.mark.parametrize(
    "fields",
    [
        {"action": "add_detail"},  # neither reason nor comment
        {"action": "set_rating", "rating": None},  # missing rating
        {"action": "set_rating", "rating": "helpful", "comment": "x"},
        {"action": "retract_rating", "rating": "helpful"},
        {"action": "add_detail", "reason_code": "bogus"},
        {"action": "add_detail", "comment": "x" * 501},
        {"action": "set_rating", "rating": "meh"},
    ],
)
def test_schema_violations_are_422(tmp_path, fields):
    app, sf = make_app(tmp_path, auth_user_id=OWNER)
    mid = seed_message(sf, owner=OWNER)
    payload = {"client_event_id": str(uuid.uuid4()), "assistant_message_id": mid}
    payload.update(fields)
    with TestClient(app) as client:
        r = post(client, payload)
    assert r.status_code == 422, r.text
    assert r.json()["status_code"] == 422


def test_comment_at_limit_is_accepted(tmp_path):
    app, sf = make_app(tmp_path, auth_user_id=OWNER)
    mid = seed_message(sf, owner=OWNER)
    with TestClient(app) as client:
        assert post(client, body(mid, rating="not_helpful")).status_code == 201
        r = post(client, body(mid, action="add_detail", comment="y" * 500))
    assert r.status_code == 201
    assert r.json()["effective_feedback"]["comment_present"] is True


def test_idempotency_key_header_mismatch_is_422(tmp_path):
    app, sf = make_app(tmp_path, auth_user_id=OWNER)
    mid = seed_message(sf, owner=OWNER)
    payload = body(mid)
    with TestClient(app) as client:
        bad = post(client, payload, headers={"Idempotency-Key": str(uuid.uuid4())})
        assert bad.status_code == 422
        assert bad.json()["error"] == "DomainValidationError"
        good = post(
            client, payload, headers={"Idempotency-Key": payload["client_event_id"]}
        )
        assert good.status_code == 201


def test_locale_is_allowlisted(tmp_path):
    """DESIGN §3.2: ``locale`` is advisory but must be a supported language."""
    app, sf = make_app(tmp_path, auth_user_id=OWNER)
    mid = seed_message(sf, owner=OWNER)
    with TestClient(app) as client:
        bad = post(client, body(mid, locale="xx"))
        assert bad.status_code == 422, bad.text
        assert bad.json()["error"] == "DomainValidationError"
        good = post(client, body(mid, locale="vi"))
        assert good.status_code == 201, good.text
        omitted = post(client, body(mid, locale=None))
        assert omitted.status_code == 201, omitted.text
    with sf() as s:
        from app.db import models

        locales = {row.locale for row in s.query(models.FeedbackEvent).all()}
    assert locales == {"vi", None}  # nothing written for the rejected request


def test_missing_body_is_shared_422_envelope(tmp_path):
    app, _ = make_app(tmp_path, auth_user_id=OWNER)
    with TestClient(app) as client:
        r = client.post("/agent/feedback")
    assert r.status_code == 422
    assert r.json()["error"] == "ValidationError"


def test_openapi_lists_route_with_429(tmp_path):
    app, _ = make_app(tmp_path, auth_user_id=OWNER)
    op = app.openapi()["paths"]["/agent/feedback"]["post"]
    assert {"201", "200", "401", "404", "409", "422", "429"} <= set(op["responses"])


# ---------------------------------------------------------------------------
# Race, export seam, observability isolation
# ---------------------------------------------------------------------------


def test_same_key_race_recovers_via_repository(tmp_path, monkeypatch):
    """Lookup misses, insert collides: the winner is replayed or conflicted."""
    exported: list = []
    monkeypatch.setattr(feedback_service, "export_hook", exported.append)
    app, sf = make_app(tmp_path, auth_user_id=OWNER)
    mid = seed_message(sf, owner=OWNER)
    payload = body(mid)
    with TestClient(app) as client:
        first = post(client, payload)
        assert first.status_code == 201
        first_id = first.json()["feedback_event_id"]
        # Simulate the concurrent writer landing between lookup and insert: the
        # first lookup misses, the insert collides, the repository recovers the
        # winner and the service compares fingerprints.
        real_find = FeedbackRepository.find_by_client_event
        calls = {"n": 0}

        def flaky_find(self, **kw):
            calls["n"] += 1
            return None if calls["n"] == 1 else real_find(self, **kw)

        monkeypatch.setattr(FeedbackRepository, "find_by_client_event", flaky_find)
        # Identical payload: the repository reports the race loss, so the
        # service answers it as a replay (200, replayed:true), the log still
        # holds exactly one row for the key and the export hook does not fire
        # a second time for the winner's event.
        assert [e.id for e in exported] == [first_id]
        r = post(client, payload)
        assert r.status_code == 200
        assert r.json()["replayed"] is True
        assert r.json()["feedback_event_id"] == first_id
        assert r.json()["effective_feedback"]["rating"] == "helpful"
        assert [e.id for e in exported] == [first_id]
        with sf() as s:
            from app.db import models

            assert s.query(models.FeedbackEvent).count() == 1

        calls["n"] = 0
        r = post(client, {**payload, "rating": "not_helpful"})
        assert r.status_code == 409


def test_export_hook_runs_after_response_with_the_event(tmp_path, monkeypatch):
    seen: list = []
    monkeypatch.setattr(feedback_service, "export_hook", seen.append)
    app, sf = make_app(tmp_path, auth_user_id=OWNER)
    mid = seed_message(sf, owner=OWNER)
    with TestClient(app) as client:
        r = post(client, body(mid))
    assert r.status_code == 201
    assert [e.id for e in seen] == [r.json()["feedback_event_id"]]


def test_service_imports_no_observability_or_memory():
    """Tracing on/off is irrelevant: the write path never imports those modules."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(feedback_service))
    imported = {
        node.module if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else [None])
    }
    for forbidden in ("langfuse", "observability", "app.memory"):
        assert not any(forbidden in (m or "") for m in imported), imported
