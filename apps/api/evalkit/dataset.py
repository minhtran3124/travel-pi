"""Validated JSON dataset store (agent-eval-pipeline task 2.4).

`JsonDatasetStore` implements the `DatasetStore` port (`evalkit/ports.py`): it
loads every ``*.json`` file in a directory (one file per capability, e.g.
``flight_search.json``), validates each case against `evalkit.types.Golden`
plus a project-supplied `evalkit.registry.Taxonomy`, and asserts every
``id`` is globally unique across the *whole* directory (not just within one
file). A validation failure names the offending file and case id/index —
"unknown" is never silent. Framework-free: no `app.*`/fastapi/sqlalchemy/
langgraph/langchain import (the evalkit portability boundary, enforced by
`tests/eval/test_boundary.py`).

## Dataset file shape

Each ``<capability>.json`` file is a JSON list of Golden-shaped dicts (fields
per `evalkit.types.Golden`)::

    [
      {
        "id": "flight_search-happy-vi-01",
        "capability": "flight_search",
        "scenario": "happy",
        "language": "vi",
        "suite": "smoke",
        "input": "Tìm chuyến bay từ TP.HCM đi Đà Nẵng ngày 20/8/2026",
        "expected_flow": "concierge",
        "expected_tools": ["search_flights"],
        "oracle_checks": [
          {
            "kind": "flight_offers",
            "params": {"origin": "SGN", "destination": "DAD", "departure_date": "2026-08-20"}
          }
        ],
        "metrics": ["flow_match", "tools_expected", "reply_language"],
        "notes": "optional free text"
      }
    ]

Exactly one of ``input`` (single-turn) or ``turns`` (multi-turn, replayed on
one thread) is required — enforced by `Golden` itself.

``oracle_checks`` is a list of opaque ``{"kind": ..., "params": {...}}``
dicts consumed by `evalkit.metrics.oracle.OracleFactCheck` (task 3.2, DB-as-
Oracle fact-checking): ``kind`` names the oracle lookup (e.g.
``"flight_offers"``, ``"hotel_availability"``, ``"trip_budget"``, ``"fx_rate"``)
and ``params`` is whatever that lookup needs. This store only validates the
outer shape (`Golden.oracle_checks: list[dict] | None`) — it never
interprets ``kind``/``params``; that is entirely the oracle metric's concern.

## Uniqueness and validation

``id`` must be unique across every file in the dataset directory. A
duplicate, an unknown ``capability``/``scenario`` (per the supplied
`Taxonomy`), or a case that fails `Golden`'s own validation (e.g. neither/
both of ``input``/``turns`` set) all raise `ValueError` naming the file and
case id (or its index, when the id itself is missing/malformed).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evalkit.registry import Taxonomy
from evalkit.types import Golden

_SUPPORTED_FILTERS = {"suite", "capability", "scenario", "language"}


class JsonDatasetStore:
    """`DatasetStore` port impl: one JSON file per capability under a directory.

    Validation happens eagerly at construction — a store you can hold is a
    store that already loaded clean; there is no lazy/partial state to trip
    over later.
    """

    def __init__(self, directory: str | Path, taxonomy: Taxonomy) -> None:
        self.directory = Path(directory)
        self.taxonomy = taxonomy
        self._goldens: list[Golden] = self._load_all()

    def _load_all(self) -> list[Golden]:
        goldens: list[Golden] = []
        seen_ids: dict[str, str] = {}  # golden id -> defining filename

        for path in sorted(self.directory.glob("*.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raise ValueError(f"{path.name}: expected a JSON list of goldens")

            for index, case in enumerate(raw):
                if not isinstance(case, dict):
                    raise ValueError(f"{path.name}[{index}]: expected a JSON object")
                case_ref = case.get("id", f"index {index}")

                try:
                    golden = Golden.model_validate(case)
                except Exception as exc:  # pydantic ValidationError
                    raise ValueError(
                        f"{path.name}: invalid golden {case_ref!r}: {exc}"
                    ) from exc

                try:
                    self.taxonomy.validate_golden(golden)
                except ValueError as exc:
                    raise ValueError(f"{path.name}: {exc}") from exc

                if golden.id in seen_ids:
                    raise ValueError(
                        f"duplicate golden id {golden.id!r} in {path.name} "
                        f"(already defined in {seen_ids[golden.id]})"
                    )
                seen_ids[golden.id] = path.name
                goldens.append(golden)

        return goldens

    def load(self, **filters: Any) -> list[Golden]:
        """Return goldens matching every supplied filter (AND across keys).

        Supported keys: ``suite``, ``capability``, ``scenario``, ``language``.
        An unsupported filter key raises ``ValueError`` rather than being
        silently ignored (a typo'd filter that matched everything would be a
        confusing way to fail).
        """
        unknown = set(filters) - _SUPPORTED_FILTERS
        if unknown:
            raise ValueError(
                f"unsupported filter(s): {sorted(unknown)}; "
                f"known: {sorted(_SUPPORTED_FILTERS)}"
            )

        result = self._goldens
        for key, value in filters.items():
            if value is None:
                continue
            result = [g for g in result if getattr(g, key) == value]
        return list(result)

    def save(self, goldens: list[Golden]) -> None:
        """Write *goldens* to ``<capability>.json``, grouped by capability.

        For the phase-2.5 golden-generation agent — not exercised by the
        smoke/full suites, which only read via `load`.
        """
        by_capability: dict[str, list[Golden]] = {}
        for golden in goldens:
            by_capability.setdefault(golden.capability, []).append(golden)

        for capability, group in by_capability.items():
            path = self.directory / f"{capability}.json"
            payload = [g.model_dump(mode="json", exclude_none=True) for g in group]
            path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
