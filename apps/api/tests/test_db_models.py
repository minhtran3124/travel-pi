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
    }


def test_booking_columns():
    cols = {c.name for c in Base.metadata.tables["bookings"].columns}
    assert cols == {
        "id",
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
    }


def test_partial_unique_index_on_idempotency():
    idx = {i.name for i in Base.metadata.tables["bookings"].indexes}
    assert "ix_bookings_idempotency_key" in idx
