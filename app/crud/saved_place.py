"""Data-access layer for saved places — SQLite persistence, nothing else.

The ``crud`` tier reads/writes ``saved_places`` rows; business rules (ID
generation, existence checks, 404/409s, dedup policy) live in
``services/saved_place_service.py``. Mirrors ``crud/trip.py``: a fresh
connection per call (threadpool-safe for sync endpoints), idempotent
``init_db``, soft-delete filtered from reads. The ``links`` column is stored
as JSON text (like ``crud/booking.py`` stores ``details``).
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.geo import haversine_km
from app.schemas.saved_place import SavedPlace

_SCHEMA = """
CREATE TABLE IF NOT EXISTS saved_places (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    city         TEXT,
    country      TEXT,
    category     TEXT,
    address      TEXT,
    latitude     REAL,
    longitude    REAL,
    price_level  INTEGER,
    notes        TEXT,
    favorite     INTEGER NOT NULL DEFAULT 0,
    visited      INTEGER NOT NULL DEFAULT 0,
    links        TEXT,
    duration     INTEGER,
    created_at   TEXT NOT NULL,
    deleted_at   TEXT
)
"""

_COLUMNS = (
    "id",
    "name",
    "city",
    "country",
    "category",
    "address",
    "latitude",
    "longitude",
    "price_level",
    "notes",
    "favorite",
    "visited",
    "links",
    "duration",
    "created_at",
)

_SET_FLAG_FIELDS = {"favorite", "visited"}


def _row_to_saved_place(row: sqlite3.Row) -> SavedPlace:
    links_raw = row["links"]
    return SavedPlace(
        id=row["id"],
        name=row["name"],
        city=row["city"],
        country=row["country"],
        category=row["category"],
        address=row["address"],
        latitude=row["latitude"],
        longitude=row["longitude"],
        price_level=row["price_level"],
        notes=row["notes"],
        favorite=bool(row["favorite"]),
        visited=bool(row["visited"]),
        links=json.loads(links_raw) if links_raw else None,
        duration=row["duration"],
        created_at=row["created_at"],
    )


def _values(sp: SavedPlace) -> tuple:
    return (
        sp.id,
        sp.name,
        sp.city,
        sp.country,
        sp.category,
        sp.address,
        sp.latitude,
        sp.longitude,
        sp.price_level,
        sp.notes,
        int(sp.favorite),
        int(sp.visited),
        json.dumps(sp.links) if sp.links is not None else None,
        sp.duration,
        sp.created_at,
    )


class SavedPlaceRepository:
    """SQLite-backed store of saved_places rows."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        """Create the saved_places table if absent (idempotent)."""
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def add(self, sp: SavedPlace) -> SavedPlace:
        placeholders = ", ".join("?" for _ in _COLUMNS)
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO saved_places ({', '.join(_COLUMNS)}) "
                f"VALUES ({placeholders})",
                _values(sp),
            )
        return sp

    def get(self, id_: str) -> SavedPlace | None:
        """Fetch a live saved place by raw UUID or SPL- short code.

        The short code is derived (not stored), so a code lookup scans the
        live rows and matches on the computed ``short_code`` in Python.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM saved_places WHERE id = ? AND deleted_at IS NULL",
                (id_,),
            ).fetchone()
            if row is not None:
                return _row_to_saved_place(row)
            rows = conn.execute(
                "SELECT * FROM saved_places WHERE deleted_at IS NULL"
            ).fetchall()
        wanted = id_.upper()
        for r in rows:
            sp = _row_to_saved_place(r)
            if sp.short_code.upper() == wanted:
                return sp
        return None

    def list(
        self,
        *,
        city: str | None = None,
        category: str | None = None,
        favorite: bool | None = None,
        visited: bool | None = None,
    ) -> list[SavedPlace]:
        clauses = ["deleted_at IS NULL"]
        params: list = []
        if city is not None:
            clauses.append("LOWER(city) = LOWER(?)")
            params.append(city)
        if category is not None:
            clauses.append("LOWER(category) = LOWER(?)")
            params.append(category)
        if favorite is not None:
            clauses.append("favorite = ?")
            params.append(int(favorite))
        if visited is not None:
            clauses.append("visited = ?")
            params.append(int(visited))
        where = " AND ".join(clauses)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM saved_places WHERE {where} "
                "ORDER BY created_at DESC, id DESC",
                params,
            ).fetchall()
        return [_row_to_saved_place(r) for r in rows]

    def soft_delete(self, id_: str, *, when: str) -> bool:
        """Stamp deleted_at; True if a live row existed and was tombstoned."""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE saved_places SET deleted_at = ? "
                "WHERE id = ? AND deleted_at IS NULL",
                (when, id_),
            )
            return cursor.rowcount > 0

    def set_flag(self, id_: str, field: str, value: bool) -> bool:
        """SET favorite/visited on a live row. True if a row changed."""
        if field not in _SET_FLAG_FIELDS:
            raise ValueError(f"Unsupported flag field: {field!r}")
        with self._connect() as conn:
            cursor = conn.execute(
                f"UPDATE saved_places SET {field} = ? "
                "WHERE id = ? AND deleted_at IS NULL",
                (int(value), id_),
            )
            return cursor.rowcount > 0

    def find_duplicate(
        self,
        *,
        name: str,
        city: str | None,
        lat: float | None,
        lng: float | None,
        radius_km: float,
    ) -> SavedPlace | None:
        """Return a non-deleted same-name duplicate, or None.

        Same case-insensitive name AND either: both records have coordinates
        and are within ``radius_km`` (haversine), or coordinates are missing
        on either side and ``city`` matches. ``haversine_km`` is never called
        with a NULL coordinate (guarded below).
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM saved_places "
                "WHERE deleted_at IS NULL AND LOWER(name) = LOWER(?)",
                (name,),
            ).fetchall()
        for r in rows:
            cand = _row_to_saved_place(r)
            both_have_coords = (
                lat is not None
                and lng is not None
                and cand.latitude is not None
                and cand.longitude is not None
            )
            if both_have_coords:
                if haversine_km(lat, lng, cand.latitude, cand.longitude) <= radius_km:
                    return cand
            elif cand.city == city:
                return cand
        return None
