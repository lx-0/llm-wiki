"""M005-S05-T02: tests for the open-commitments dashboard stat helpers.

`_open_action_items_in_entities()` counts `- [ ]` lines under `## Action Items`
in `knowledge/people/` + `knowledge/projects/`, returning (open_total,
entities_with_at_least_one_open).
"""
from __future__ import annotations

from pathlib import Path

from dashboard.dashboard_stats import _open_action_items_in_entities


def _make_entity(folder: Path, name: str, action_items_block: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    body = (
        "---\n"
        f"title: \"{name}\"\n"
        f"type: {'person' if folder.name == 'people' else 'project'}\n"
        "---\n\n"
        f"# {name}\n\n"
        "## Action Items\n"
        f"{action_items_block}\n"
        "\n## Open Threads\n- placeholder\n"
    )
    file = folder / f"{name.lower().replace(' ', '-')}.md"
    file.write_text(body, encoding="utf-8")
    return file


def test_empty_knowledge_returns_zero(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    open_total, entities_with = _open_action_items_in_entities(knowledge)
    assert (open_total, entities_with) == (0, 0)


def test_single_person_three_open_items(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    _make_entity(
        knowledge / "people", "Jane Doe",
        "- [ ] Send the Q3 deck 📅 2026-04-22\n"
        "- [ ] Follow up on Bob intro\n"
        "- [ ] Schedule onboarding 📅 2026-05-01",
    )
    open_total, entities_with = _open_action_items_in_entities(knowledge)
    assert (open_total, entities_with) == (3, 1)


def test_mix_open_and_checked_counts_only_open(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    _make_entity(
        knowledge / "people", "Bob Smith",
        "- [x] Sign the contract\n"
        "- [X] Pay invoice\n"
        "- [ ] Schedule onboarding call 📅 2026-04-15",
    )
    open_total, entities_with = _open_action_items_in_entities(knowledge)
    assert (open_total, entities_with) == (1, 1)


def test_entities_with_no_open_items_dont_count(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    _make_entity(knowledge / "people", "Closed Bob", "- [x] Pay invoice")
    _make_entity(knowledge / "people", "Open Jane", "- [ ] Send deck")
    open_total, entities_with = _open_action_items_in_entities(knowledge)
    assert (open_total, entities_with) == (1, 1)


def test_people_and_projects_both_counted(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    _make_entity(knowledge / "people", "Jane Doe", "- [ ] Item A")
    _make_entity(knowledge / "projects", "Yesterday Platform", "- [ ] Item B\n- [ ] Item C")
    open_total, entities_with = _open_action_items_in_entities(knowledge)
    assert (open_total, entities_with) == (3, 2)
