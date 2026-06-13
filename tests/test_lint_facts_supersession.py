"""M028-S04-T02: a superseded article is not a fact-violation forever."""

from __future__ import annotations


def test_superseded_by_fact_matches_slug() -> None:
    import lint
    assert lint._superseded_by_fact({"status": "superseded", "superseded_by": "facts/adn"}, "adn") is True
    # bare slug form also accepted
    assert lint._superseded_by_fact({"status": "superseded", "superseded_by": "adn"}, "adn") is True


def test_superseded_by_other_fact_still_violates() -> None:
    import lint
    assert lint._superseded_by_fact({"status": "superseded", "superseded_by": "facts/other"}, "adn") is False


def test_non_superseded_article_not_skipped() -> None:
    import lint
    assert lint._superseded_by_fact({}, "adn") is False
    assert lint._superseded_by_fact({"status": "active"}, "adn") is False
