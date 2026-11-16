"""Unit tests for the canonical event-name slug.

The dashboard resolves a race directory from ``reports/<season>/calendar.json``.
The report writers derive the same directory from the FastF1 event name. These
tests pin the two together: an accented name that produces a different slug on
each side makes the CSVs unreachable and the page 404.
"""

from __future__ import annotations

import pytest

from f1_predictions.utils.event_slug import event_slug


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Canadian Grand Prix", "Canadian_Grand_Prix"),
        ("United States Grand Prix", "United_States_Grand_Prix"),
        ("Mexico City Grand Prix", "Mexico_City_Grand_Prix"),
        # Regression: FastF1 spells it "São Paulo"; calendar.json stores
        # "Sao_Paulo_Grand_Prix". A naive replace(" ", "_") keeps the accent
        # and the dashboard cannot find the race.
        ("São Paulo Grand Prix", "Sao_Paulo_Grand_Prix"),
        ("São Paulo Grand Prix".replace("ã", "a"), "Sao_Paulo_Grand_Prix"),
    ],
)
def test_matches_calendar_convention(name: str, expected: str) -> None:
    assert event_slug(name) == expected


def test_strips_accents_generically() -> None:
    """Decomposition handles diacritics that a hand-written map would miss."""
    assert event_slug("Crème Brûlée Grand Prix") == "Creme_Brulee_Grand_Prix"
    assert event_slug("Ñandú Grand Prix") == "Nandu_Grand_Prix"


def test_collapses_separators() -> None:
    assert event_slug("  Miami   Grand Prix  ") == "Miami_Grand_Prix"
    assert event_slug("São  Paulo Grand Prix") == "Sao_Paulo_Grand_Prix"


def test_already_slugged_name_is_stable() -> None:
    assert event_slug("Sao_Paulo_Grand_Prix") == "Sao_Paulo_Grand_Prix"
