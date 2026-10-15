"""M033-S05-T03 — the schema-2 JSON contracts, typed once.

`core/contracts.py` defines the `wiki menu --json` and `wiki doctor --json` payloads as
TypedDicts and generates `docs/contracts/{menu,doctor}.schema.json` from them. These tests
pin three things: the committed schemas are current (regenerate with
`PYTHONPATH=scripts uv run python -m core.contracts --write`); the oracle's golden payloads —
the engine's real output on the fixture vault — validate; and the schemas reject what drift
looks like (an unknown key, a wrong type, a missing key).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from core import actions, contracts

REPO = Path(__file__).resolve().parent.parent
GOLDEN = REPO / "tests" / "golden" / "oracle"
PAYLOADS = {"menu": GOLDEN / "menu.json", "doctor": GOLDEN / "doctor-quick.json"}


def _schema(name: str) -> dict:
    return json.loads((REPO / "docs" / "contracts" / f"{name}.schema.json").read_text("utf-8"))


def _validator(name: str) -> Draft202012Validator:
    schema = _schema(name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _golden(name: str) -> dict:
    return json.loads(PAYLOADS[name].read_text(encoding="utf-8"))


def test_committed_schemas_are_current() -> None:
    assert contracts.stale() == [], (
        "docs/contracts/ is stale relative to core/contracts.py — run "
        "`PYTHONPATH=scripts uv run python -m core.contracts --write` and commit the result"
    )


@pytest.mark.parametrize("name", sorted(PAYLOADS))
def test_golden_payload_validates(name: str) -> None:
    errors = sorted(_validator(name).iter_errors(_golden(name)), key=str)
    assert errors == [], "\n".join(f"{list(e.absolute_path)}: {e.message}" for e in errors)


@pytest.mark.parametrize("name", sorted(PAYLOADS))
def test_schema_version_is_the_engines(name: str) -> None:
    assert _schema(name)["properties"]["schema"] == {"const": actions.SCHEMA}


def test_an_unknown_key_is_rejected() -> None:
    payload = _golden("menu")
    payload["suggestions"][0]["surprise"] = 1
    assert not _validator("menu").is_valid(payload)


def test_a_wrong_type_is_rejected() -> None:
    payload = _golden("doctor")
    payload["checks"][0]["severity"] = 3
    assert not _validator("doctor").is_valid(payload)


def test_a_missing_key_is_rejected() -> None:
    payload = _golden("doctor")
    del payload["checks"][0]["verb"]
    assert not _validator("doctor").is_valid(payload)


def test_status_keys_are_optional() -> None:
    # Every status probe can fail on its own and drop its key (menu_context.build_status).
    payload = _golden("menu")
    payload["status"] = {}
    assert _validator("menu").is_valid(payload)


def test_a_new_severity_is_caught_by_the_summary_contract() -> None:
    # health_summary counts whatever severity a check reports; the contract names four.
    payload = _golden("doctor")
    payload["summary"]["fatal"] = 1
    assert not _validator("doctor").is_valid(payload)
