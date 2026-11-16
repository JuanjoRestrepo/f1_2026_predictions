"""Canonical event-name slug used for report directories and the dashboard.

The dashboard resolves a race's directory from ``reports/<season>/calendar.json``
(``RaceInfo.dirName``), while the report writers pick a directory from the
FastF1 event name. If those two disagree, the CSVs exist but the dashboard
cannot find them: ``/race/<round>`` silently 404s.

That is exactly what happens when the writers use a naive
``name.replace(" ", "_")``: FastF1 reports ``"São Paulo Grand Prix"`` and the
calendar stores ``"Sao_Paulo_Grand_Prix"``. One accent is enough to break the
page.

Keep this the single implementation. Both the calendar generator and the
report writers must import it so the two sides cannot drift.
"""

from __future__ import annotations

import re
import unicodedata


def event_slug(name: str) -> str:
    """Convert an event name to a filesystem-safe underscore slug.

    Accents are stripped by decomposition rather than a hand-maintained
    character map, so new names (or new diacritics) cannot fall through.

    Example:
        "Canadian Grand Prix" -> "Canadian_Grand_Prix"
        "São Paulo Grand Prix" -> "Sao_Paulo_Grand_Prix"
        "Mexico City Grand Prix" -> "Mexico_City_Grand_Prix"

    Args:
        name: The human-readable GP name from FastF1.

    Returns:
        A filesystem-safe slug string.
    """
    # NFKD splits "ã" into "a" + combining tilde; drop the combining marks.
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))

    # Replace non-alphanumeric characters (except underscores) with
    # underscores, then collapse any multiple consecutive underscores.
    result = re.sub(r"[^\w]", "_", stripped)
    return re.sub(r"_+", "_", result).strip("_")
