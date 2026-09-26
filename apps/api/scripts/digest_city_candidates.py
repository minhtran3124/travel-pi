#!/usr/bin/env python3
"""Write a compact, numbered digest of a candidates file for curation.

    python -m scripts.digest_city_candidates            # all cities

Each digest lists hotel and place candidates (qid, label, types, image yes/no) with
their Wikipedia extract split into numbered sentences (``wp:<n>``), and the
Wikivoyage text split into numbered sentences (``wv:<n>``). A selection cites a
sentence by that id; ``build_city_sources`` resolves it back to the exact text.
"""

from __future__ import annotations

import json
import sys

from scripts.build_city_sources import CITIES, SPEC, sentences


def digest(city: str) -> str:
    cand = json.loads((SPEC / "candidates" / f"{city}.json").read_text())
    wiki = cand.get("wikipedia", {})
    lines = [f"# {city} — candidate digest", ""]
    for key in ("hotels", "places", "restaurants"):
        lines.append(f"## {key}")
        for c in cand[key]:
            types = ", ".join(c.get("instance_of") or []) or "-"
            image = "image" if c.get("image_url") else "NO image"
            lines.append(
                f"- {c['qid']} | {c['label']} | types: {types} | {image} | address: {c.get('address') or '-'} | sitelinks {c.get('sitelinks', 0)}"
            )
            extract = (wiki.get(c["qid"]) or {}).get("extract")
            for i, sent in enumerate(sentences(extract or "")[:6]):
                lines.append(f"    wp:{i} {sent}")
        lines.append("")
    lines.append("## wikivoyage sentences")
    text = "\n".join(v for v in cand.get("wikivoyage", {}).values() if v)
    for i, sent in enumerate(sentences(text)):
        lines.append(f"wv:{i} {sent}")
    return "\n".join(lines) + "\n"


def main() -> int:
    out_dir = SPEC / "digests"
    out_dir.mkdir(exist_ok=True)
    for city in CITIES:
        (out_dir / f"{city}.md").write_text(digest(city))
        print(city)
    return 0


if __name__ == "__main__":
    sys.exit(main())
