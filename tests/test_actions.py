"""core.actions — the engine's operator-facing vocabulary for every runnable action.

The catalogue is what `wiki menu --json` / `wiki doctor --json` consumers (desktop app, agents)
render verbatim, so these tests pin the contract: ids are stable keys, titles pluralize on the
count, verbs fall back by command, and every argv targets a real `wiki` subcommand.
"""

from __future__ import annotations

import pytest

from core import actions
from core.actions import CATALOGUE, SCHEMA, ActionSpec, get, tools, verb_for


def test_schema_version_is_two():
    assert SCHEMA == 2


def test_titles_pluralize_on_count():
    spec = get("process-inbox")
    assert spec.title(1) == "1 new capture to sort"
    assert spec.title(3) == "3 new captures to sort"


def test_countless_titles_ignore_the_count():
    spec = get("flush")
    assert spec.title(None) == "Save today's session to your wiki"
    assert spec.title(5) == "Save today's session to your wiki"


def test_ids_are_unique_and_equal_their_keys():
    assert all(spec.id == key for key, spec in CATALOGUE.items())
    assert len({spec.id for spec in CATALOGUE.values()}) == len(CATALOGUE)


def test_every_argv_starts_with_a_known_wiki_subcommand():
    import cli

    known = set(cli.BY_NAME) | actions.BASH_OWNED_COMMANDS
    for spec in CATALOGUE.values():
        assert spec.argv[0] in known, f"{spec.id}: {spec.argv[0]!r} is not a wiki subcommand"


def test_verb_for_matches_exact_argv_before_falling_back_by_command():
    assert verb_for(["dream", "--all-entities"]) == "Refresh"
    assert verb_for(["links", "--fix", "--yes"]) == "Fix"
    assert verb_for(["gmail-auth", "gmail-personal"]) == "Sign in"
    assert verb_for(["setup"]) == "Set up"
    assert verb_for(["reindex"]) == "Rebuild"


def test_verb_for_unknown_command_is_run():
    assert verb_for(["frobnicate"]) == "Run"
    assert verb_for([]) == "Run"


def test_tools_are_the_tool_flagged_entries_without_counts():
    listed = tools()
    assert {t["id"] for t in listed} == {"lint", "dream-sweep", "links-fix", "dedup", "review-wiki"}
    for t in listed:
        assert t["group"] == "tools"
        assert "{n}" not in t["title"]
        assert isinstance(t["argv"], list) and t["argv"]
        assert t["verb"]


def test_to_json_shape():
    payload = get("dream-sweep").to_json(12)
    assert payload == {
        "id": "dream-sweep",
        "title": "12 pages need refreshing",
        "verb": "Refresh",
        "group": "auto",
        "argv": ["dream", "--all-entities"],
    }


def test_get_unknown_id_raises():
    with pytest.raises(KeyError):
        get("no-such-action")


def test_specs_are_immutable():
    spec = get("compile")
    assert isinstance(spec, ActionSpec)
    with pytest.raises(AttributeError):
        spec.verb = "Nope"  # type: ignore[misc]
