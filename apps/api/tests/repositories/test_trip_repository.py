"""_row_to_trip sorts on (day, sort_order, created_at, id) so same-day items with a tied sort_order read back in a stable order across concurrent commits."""

from app.db.models import Trip, TripItem
from app.repositories.trip import _row_to_trip


def _item(day, sort_order, created_at, id_):
    return TripItem(
        id=id_,
        trip_id="trip-1",
        day=day,
        sort_order=sort_order,
        kind="activity",
        title=f"item-{id_}",
        status="pending",
        created_at=created_at,
    )


def _trip_row():
    return Trip(
        id="trip-1",
        user_id="u1",
        title="Trip",
        travelers=1,
        created_at="2026-01-01T00:00:00Z",
    )


def test_row_to_trip_orders_tied_sort_order_by_created_at_deterministically():
    # All sort_order=0, created_at out of insertion order so ties resolve by created_at.
    row_b = _item(day=1, sort_order=0, created_at="2026-01-01T00:00:02Z", id_="b")
    row_c = _item(day=1, sort_order=0, created_at="2026-01-01T00:00:00Z", id_="c")
    row_a = _item(day=1, sort_order=0, created_at="2026-01-01T00:00:01Z", id_="a")
    item_rows = [row_b, row_c, row_a]  # insertion/DB-return order, not sorted

    trip = _row_to_trip(_trip_row(), item_rows)
    assert [i.id for i in trip.items] == ["c", "a", "b"]

    # Shuffled input must yield the identical result — order is a function of the data, not DB return order.
    shuffled = [row_a, row_b, row_c]
    trip_again = _row_to_trip(_trip_row(), shuffled)
    assert [i.id for i in trip_again.items] == ["c", "a", "b"]
