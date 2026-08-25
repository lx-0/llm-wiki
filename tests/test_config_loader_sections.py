"""Every WikiConfig section must be merged by core.config.load().

Guards the hand-maintained merge list in load() (M030-S02 incident,
2026-08-25): `publish:` existed in the schema, the example yaml, the
migration AND the generated docs — and the loader silently ignored it, so
`publish.enabled: true` in an operator vault read back as False. This test
derives the section list from the WikiConfig dataclass itself, so a future
new section fails loudly instead of silently running on defaults.
"""
from __future__ import annotations

from dataclasses import fields, is_dataclass
from pathlib import Path

import yaml

from core import config as config_mod
from core.config_schema import WikiConfig


def test_every_section_override_survives_load(tmp_path: Path, monkeypatch) -> None:
    overrides: dict[str, dict[str, object]] = {}
    expected: dict[tuple[str, str], object] = {}

    for section_field in fields(WikiConfig):
        default_section = getattr(WikiConfig(), section_field.name)
        if not is_dataclass(default_section):
            continue  # piggybacks: dict[str, PiggybackTask] — own merge + tests
        for scalar in fields(type(default_section)):
            value = getattr(default_section, scalar.name)
            if isinstance(value, bool):
                new = not value
            elif isinstance(value, str):
                new = (value + "-override") if value else "override"
            elif isinstance(value, int):
                new = value + 1
            else:
                continue
            overrides.setdefault(section_field.name, {})[scalar.name] = new
            expected[(section_field.name, scalar.name)] = new
            break
        else:
            raise AssertionError(
                f"section {section_field.name}: no scalar field to probe"
            )

    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.safe_dump(overrides), encoding="utf-8")
    monkeypatch.setattr(config_mod, "CONFIG_FILE", cfg_file)

    loaded = config_mod.load()
    for (section, key), want in expected.items():
        got = getattr(getattr(loaded, section), key)
        assert got == want, (
            f"{section}.{key}: yaml override {want!r} ignored by load() — "
            f"section missing from the merge list?"
        )
