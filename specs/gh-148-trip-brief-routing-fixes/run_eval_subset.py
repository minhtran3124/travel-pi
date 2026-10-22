"""Run the real eval wiring (eval.__main__) on an explicit golden-id subset.

evalkit's CLI filters only by suite/capability/language, so running the
capabilities touched by gh-148 would pull ~47 goldens. This swaps the dataset
store for one that keeps only GOLDEN_IDS, then delegates to eval.__main__.main()
unchanged (DB agent config, premium context, judge, oracle).

Run from apps/api (container: -w /app, this dir mounted at /spec):
    python /spec/run_eval_subset.py --suite full --repeat 3 --out eval/reports/gh-148.json
"""

from __future__ import annotations

import os
import sys

# Run by path, so the script's dir (not cwd=apps/api) is on sys.path.
sys.path.insert(0, os.getcwd())

import eval.__main__ as eval_main  # noqa: E402
from evalkit.dataset import JsonDatasetStore  # noqa: E402

GOLDEN_IDS = frozenset(
    {
        "language-ambiguous-en-01",  # #148
        "language-multi_turn-vi-01",  # #148
        "routing-multi-en-01",  # #149
        "journal-multi_turn-vi-01",  # #150
        "budget-ambiguous-en-03",  # #151
        "memory-multi_turn-vi-04",  # #152
        "budget-ambiguous-en-02",  # watch item (#146), not gated
        "dates-ambiguous-en-02",  # gh-191 regression guard (E001-A)
        "dates-ambiguous-vi-02",  # gh-191 regression guard (E001-A)
        "dates-ambiguous-en-03",  # gh-191 regression guard (E001-A)
    }
)


class SubsetDatasetStore(JsonDatasetStore):
    def load(self, **filters):
        # Ids are explicit, so ignore the CLI's suite filter: the gh-191 guards
        # dates-ambiguous-{en,vi}-02 are smoke-suite goldens.
        filters.pop("suite", None)
        return [g for g in super().load(**filters) if g.id in GOLDEN_IDS]


eval_main.JsonDatasetStore = SubsetDatasetStore

if __name__ == "__main__":
    sys.exit(eval_main.main())
