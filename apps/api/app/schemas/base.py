"""Project-wide Pydantic base model.

Every request/response schema inherits :class:`AppBaseModel` so shared
behaviour lives in one place. Today that is ``from_attributes`` (lets a
schema be built straight from an object with matching attributes); future
cross-cutting concerns (datetime serialisation, aliases) go here too.
"""

from pydantic import BaseModel, ConfigDict


class AppBaseModel(BaseModel):
    """Common base for all schemas in the app."""

    model_config = ConfigDict(from_attributes=True)
