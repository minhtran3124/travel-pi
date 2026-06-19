"""SQLAlchemy declarative base — the registry every ORM model attaches to.

Importing this module has no DB side effects (no engine, no connection); it
only defines the metadata that Alembic autogenerate and create_all read.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models in app.db.models."""
