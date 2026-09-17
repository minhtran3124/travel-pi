"""Project-wide Pydantic base model."""

from pydantic import BaseModel, ConfigDict


class AppBaseModel(BaseModel):
    """Common base for all schemas in the app."""

    model_config = ConfigDict(from_attributes=True)
