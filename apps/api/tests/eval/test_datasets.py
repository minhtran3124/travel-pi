import pytest
from eval.loader import load_all
from eval.metrics_geval import GEVAL_METRICS


def test_all_datasets_load_and_validate():
    all_ds = load_all()
    assert set(all_ds) == {
        "intent.json",
        "language.json",
        "tools.json",
        "format.json",
        "memory.json",
        "suggestions.json",
    }


def test_total_case_count_at_least_15():
    assert sum(len(v) for v in load_all().values()) >= 15


def test_every_case_has_string_input_or_turns():
    # MIN-65 D9: a case is either the original single-turn shape (string
    # `input`) or the multi-turn shape (non-empty list of string `turns`).
    for cases in load_all().values():
        for c in cases:
            if "turns" in c:
                assert isinstance(c["turns"], list) and c["turns"]
                assert all(isinstance(t, str) for t in c["turns"])
            else:
                assert isinstance(c["input"], str) and c["input"]


def test_declared_metrics_reference_known_geval_keys():
    for cases in load_all().values():
        for c in cases:
            for m in c.get("metrics", []):
                assert m in GEVAL_METRICS


def test_load_rejects_missing_input(tmp_path, monkeypatch):
    import eval.loader as loader

    bad = tmp_path / "bad.json"
    bad.write_text('[{"nope": 1}]', encoding="utf-8")
    monkeypatch.setattr(loader, "_DATASETS", tmp_path)
    with pytest.raises(ValueError):
        loader.load("bad.json")


def test_load_rejects_non_dict_elements(tmp_path, monkeypatch):
    import eval.loader as loader

    bad = tmp_path / "bad.json"
    # Non-dict elements (e.g. bare ints) must raise ValueError, not TypeError.
    bad.write_text("[1, 2]", encoding="utf-8")
    monkeypatch.setattr(loader, "_DATASETS", tmp_path)
    with pytest.raises(ValueError):
        loader.load("bad.json")
