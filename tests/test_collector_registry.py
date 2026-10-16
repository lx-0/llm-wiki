"""The collector registry is a name → module table, registered lazily (M034-S06-T03).

Importing the `collectors` package registers nothing: `get_collector(name)` imports that
collector's module alone (its `@register` runs then), and `all_collectors()` imports them all
in the table's order — the order `wiki collect --list` and piggyback discovery report. The
package used to import every collector so the decorators ran, which made each collector verb
pay for all of them and kept `python -m collectors.<x>` from running (runpy's double import).

The import checks run in a child interpreter: this test process has loaded every collector
long before (the other collector tests import them).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import collectors

SCRIPTS = Path(collectors.__file__).resolve().parent.parent
PACKAGE = SCRIPTS / "collectors"


def _collector_modules_after(code: str) -> list[str]:
    """The `collectors.*` modules (besides the package and its base) loaded by ``code``."""
    probe = (
        f"{code}\n"
        "import json, sys\n"
        "print(json.dumps(sorted(m for m in sys.modules if m.startswith('collectors.'))))\n"
    )
    run = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=SCRIPTS,
        env={"PYTHONPATH": str(SCRIPTS), "PATH": "/usr/bin:/bin", "HOME": str(SCRIPTS)},
        capture_output=True,
        text=True,
        check=True,
    )
    loaded = json.loads(run.stdout.strip().splitlines()[-1])
    return [m for m in loaded if m != "collectors.base"]


def test_importing_the_package_imports_no_collector():
    assert _collector_modules_after("import collectors") == []


def test_one_collector_imports_only_its_module():
    loaded = _collector_modules_after(
        "from collectors import get_collector\nassert get_collector('tabs') is not None"
    )
    assert loaded == ["collectors.scan_tabs"]


def test_an_unknown_name_is_none_and_imports_nothing():
    assert (
        _collector_modules_after(
            "from collectors import get_collector\nassert get_collector('nope') is None"
        )
        == []
    )


def test_every_registering_module_is_in_the_table():
    """A module with an `@register` that the table does not name would never be found."""
    registering = sorted(
        f"collectors.{path.stem}"
        for path in PACKAGE.glob("*.py")
        if re.search(r"^@register\b", path.read_text(encoding="utf-8"), re.MULTILINE)
    )
    assert sorted(collectors.MODULES.values()) == registering


def test_all_collectors_keep_the_table_order():
    assert [c.SPEC.name for c in collectors.all_collectors()] == list(collectors.MODULES)
