"""_row_to_trip item ordering: deterministic across repeated reads.

``add_itinerary_item`` never sets ``sort_order`` (schema default 0), and when
the planner batches several calls in one turn, LangGraph's ToolNode runs them
concurrently — each commits its own transaction independently, so the DB
query behind ``item_rows`` returns them in no guaranteed order. Sorting on
(day, sort_order) alone leaves every same-day item tied, so the old code fell
back to whatever order the DB handed back — different on every read. Sorting
the ORM rows on (day, sort_order, created_at, id) before conversion makes
repeated reads of the same DB state return the same order.
"""

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
    # All sort_order=0 (the common case), created_at deliberately out of
    # insertion order — item "b" should sort last despite being inserted first.
    row_b = _item(day=1, sort_order=0, created_at="2026-01-01T00:00:02Z", id_="b")
    row_c = _item(day=1, sort_order=0, created_at="2026-01-01T00:00:00Z", id_="c")
    row_a = _item(day=1, sort_order=0, created_at="2026-01-01T00:00:01Z", id_="a")
    item_rows = [row_b, row_c, row_a]  # insertion/DB-return order, not sorted

    trip = _row_to_trip(_trip_row(), item_rows)
    assert [i.id for i in trip.items] == ["c", "a", "b"]

    # A second read with the rows shuffled into a different order must return
    # the identical result — proof the order is a function of the data, not
    # of whatever order the DB query happened to return.
    shuffled = [row_a, row_b, row_c]
    trip_again = _row_to_trip(_trip_row(), shuffled)
    assert [i.id for i in trip_again.items] == ["c", "a", "b"]
