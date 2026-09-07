"""No inline language-code literals outside ``app/core/languages.py``.

The modules below used to spell ``"en"`` / ``"vi"`` inline; every code now comes
from ``app.core.languages`` so the supported list has one owner.
"""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
MODULES = [
    APP / "agents" / "supervisor.py",
    APP / "agents" / "state.py",
    APP / "streaming" / "events.py",
    APP / "streaming" / "mapper.py",
    APP / "streaming" / "panel_localizer.py",
]
LITERAL = re.compile(r"""["'](en|vi)["']""")


def test_no_language_code_literals():
    offenders = {
        str(path.relative_to(APP.parent)): [
            line.strip()
            for line in path.read_text().splitlines()
            if LITERAL.search(line)
        ]
        for path in MODULES
    }
    offenders = {k: v for k, v in offenders.items() if v}
    assert not offenders, offenders
