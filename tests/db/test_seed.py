"""Idempotency + correctness tests for the seeder (``app.db.seed.seed_all``).

The seeder must be runnable repeatedly (lifespan + ``make seed`` both call it
on every startup) with identical results — ``session.merge()`` for natural-PK
entities and a natural-key upsert for ``City`` (whose PK is autoincrement int)
guarantee that.
"""

from app.db import models
from app.db.base import Base
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
    assert any(i.startswith("tip_country_") for i in ids)
    # The well-known first Vietnam country tip must be stable.
    assert "tip_country_vietnam_00" in ids


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
        fx_meta = s.get(models.FxMeta, 1)
    assert airlines == 7
    assert fx_meta is not None and fx_meta.last_updated
