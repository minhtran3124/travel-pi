"""Project-wide Pydantic base models.

Every schema inherits :class:`AppBaseModel` so shared behaviour lives in one
place. Today that is ``from_attributes`` (lets a schema be built straight from
an object with matching attributes); future cross-cutting concerns (datetime
serialisation, aliases) go here too.

Request *bodies* additionally inherit :class:`RequestModel`, which forbids
unknown fields — see its docstring for why responses deliberately don't.
"""

from pydantic import BaseModel, ConfigDict


class AppBaseModel(BaseModel):
    """Common base for all schemas in the app."""

    model_config = ConfigDict(from_attributes=True)


class RequestModel(AppBaseModel):
    """Base for request *body* schemas — rejects unknown fields.

    ``extra="forbid"`` makes a misspelled or stale request field a loud 422
    instead of a silently-dropped no-op: a client (or agent) that sends, say,
    ``guests`` when the field is ``adults`` — or a ``price`` the server is
    meant to compute — finds out immediately rather than having the value
    quietly ignored and a default used.

    This lives on a request-only base, *not* on ``AppBaseModel``, on purpose.
    Response models are built server-side and several legitimately re-spread a
    dumped model into a wider one (``Wider(**obj.model_dump(), extra=...)``,
    e.g. ``NearbyPlace`` / ``HotelAvailability``); ``model_dump()`` includes
    computed fields like ``short_code``, so forbidding extras there would
    break that idiomatic pattern for no real benefit. Pydantic v2 merges
    ``model_config`` down the inheritance chain, so subclasses that set their
    own ``model_config`` (e.g. for ``json_schema_extra``) still inherit this.
    """

    model_config = ConfigDict(extra="forbid")
