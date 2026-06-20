"""Idempotency + correctness tests for the seeder (``app.db.seed.seed_all``).

The seeder must be runnable repeatedly (lifespan + ``make seed`` both call it
on every startup) with identical results — ``session.merge()`` keyed on a
deterministic UUID5 id for reference entities and a natural-key upsert for
``City`` guarantee that.
"""

from app.db import models
from app.db.base import Base, deterministic_uuid
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from sqlalchemy import func, select


def _fresh(tmp_path):
    url = f"sqlite:///{tmp_path / 'seed.db'}"
    Base.metadata.create_all(get_engine(url))
    return get_session_factory(url)


def _count(sf, model):
    with sf() as s:
        return s.scalar(select(func.count()).select_from(model))


def test_seed_is_idempotent(tmp_path):
    sf = _fresh(tmp_path)
    seed_all(sf)
    models_to_count = (
        models.Country,
        models.Airline,
        models.Airport,
        models.City,
        models.Hotel,
        models.Place,
        models.Tip,
        models.Visa,
        models.FxRate,
    )
    counts1 = {m: _count(sf, m) for m in models_to_count}
    seed_all(sf)  # re-run
    counts2 = {m: _count(sf, m) for m in models_to_count}
    assert counts1 == counts2 and all(v > 0 for v in counts1.values())


def test_seed_cities_no_duplicate(tmp_path):
    """City has an int autoincrement PK — guard the natural-key upsert path.

    A naive ``merge()`` would insert a brand-new row each run (no PK match);
    the seeder must upsert by ``(name, country)`` so the count stays stable.
    """
    sf = _fresh(tmp_path)
    seed_all(sf)
    first = _count(sf, models.City)
    seed_all(sf)
    second = _count(sf, models.City)
    assert first == second and first > 0


def test_seed_preserves_tip_ids(tmp_path):
    sf = _fresh(tmp_path)
    seed_all(sf)
    with sf() as s:
        ids = s.scalars(
            select(models.Tip.id).where(models.Tip.scope == "country")
        ).all()
    # Tip ids are deterministic UUID5 over (scope, key, position) — stable
    # across re-seeds. The well-known first Vietnam country tip must be present.
    assert deterministic_uuid("tip", "country", "Vietnam", "0") in ids


def test_seed_fills_hotel_country(tmp_path):
    sf = _fresh(tmp_path)
    seed_all(sf)
    with sf() as s:
        assert all(c for c in s.scalars(select(models.Hotel.country)).all())


def test_seed_known_counts(tmp_path):
    sf = _fresh(tmp_path)
    seed_all(sf)
    with sf() as s:
        airlines = s.scalar(select(func.count()).select_from(models.Airline))
        fx_meta = s.scalars(select(models.FxMeta)).first()
    assert airlines == 7
    assert fx_meta is not None and fx_meta.last_updated
