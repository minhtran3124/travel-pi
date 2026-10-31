from app.db import models  # noqa: F401  (registers models on Base)
from app.db.base import Base


def test_all_tables_registered():
    assert set(Base.metadata.tables) == {
        "bookings",
        "expenses",
        "trips",
        "trip_items",
        "trip_place_link",
        "saved_places",
        "flight_index",
        "countries",
        "airlines",
        "airports",
        "cities",
        "hotels",
        "places",
        "tips",
        "country_summaries",
        "visa",
        "fx_rates",
        "country_currency",
        "fx_meta",
        "conversations",
        "messages",
        "jobs",
        "users",
        "agent_config",
        "rate_limit_counters",
        "agent_runs",
        "agent_run_steps",
        "content_translations",
        "feedback_events",
        "bot_heartbeats",
    }


def test_agent_runs_columns():
    cols = {c.name for c in Base.metadata.tables["agent_runs"].columns}
    assert cols == {
        "id",
        "created_at",
        "updated_at",
        "user_id",
        "conversation_id",
        "thread_id",
        "instance_id",
        "trip_id",
        "channel",
        "kind",
        "status",
        "current_flow",
        "started_at",
        "finished_at",
        "latency_ms",
        "llm_calls",
        "llm_errors",
        "input_tokens",
        "output_tokens",
        "cached_tokens",
        "cost_usd",
        "by_model",
        "by_node",
        "background_llm_calls",
        "background_tokens",
        "background_ms",
        "prompt_versions",
    }


def test_agent_run_steps_columns():
    cols = {c.name for c in Base.metadata.tables["agent_run_steps"].columns}
    assert cols == {
        "id",
        "created_at",
        "updated_at",
        "run_id",
        "seq",
        "kind",
        "node",
        "ns",
        "model",
        "prompts",
        "input_tokens",
        "output_tokens",
        "cached_tokens",
        "cost_usd",
        "offset_ms",
        "ms",
        "status",
        "error_type",
        "tool_name",
        "meta",
    }


def test_booking_columns():
    cols = {c.name for c in Base.metadata.tables["bookings"].columns}
    assert cols == {
        "id",
        "user_id",
        "type",
        "reference_id",
        "customer_name",
        "customer_email",
        "total_price",
        "currency",
        "status",
        "created_at",
        "updated_at",
        "details",
        "notes",
        "idempotency_key",
        "confirmation_code",
        "trip_id",
    }


def test_partial_unique_index_on_idempotency():
    idx = {i.name for i in Base.metadata.tables["bookings"].indexes}
    assert "ix_bookings_idempotency_key" in idx


def test_messages_columns():
    cols = {c.name for c in Base.metadata.tables["messages"].columns}
    assert cols == {
        "id",
        "created_at",
        "updated_at",
        "conversation_id",
        "role",
        "content",
        "tool_calls",
        "agent_run_id",
    }


def test_feedback_events_columns():
    table = Base.metadata.tables["feedback_events"]
    cols = {c.name for c in table.columns}
    assert cols == {
        "id",
        "created_at",
        "updated_at",
        "schema_version",
        "user_id",
        "conversation_id",
        "assistant_message_id",
        "agent_run_id",
        "action",
        "rating",
        "reason_code",
        "comment",
        "source",
        "locale",
        "client_event_id",
        "request_fingerprint",
        "supersedes_event_id",
    }
    assert {i.name for i in table.indexes} == {
        "ix_feedback_events_user_id",
        "ix_feedback_events_conversation_id",
        "ix_feedback_events_assistant_message_id",
        "ix_feedback_events_agent_run_id",
        "ix_feedback_events_assistant_message_id_created_at_id",
        "ix_feedback_events_user_id_created_at",
        "ix_feedback_events_rating_created_at",
    }
    constraint_names = {c.name for c in table.constraints}
    assert {"uq_feedback_events_user_client_event", "ck_feedback_events_rating"} <= (
        constraint_names
    )
