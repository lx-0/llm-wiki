# shellcheck shell=bash
# config.sh — wraps the Python core/config.py CLI for the bash callers M034 has not ported
# yet: lib/skills.sh reads config_get and `wiki skills` writes config_set (S03). `wiki config`
# and the setup wizard are Python since S02-T02 / T03 (scripts/config_cli.py, setup_cli.py);
# this file is deleted with its last caller at the end of M034-S03 (reassessment after S01).

[[ -n "${__WIKI_CONFIG_LOADED:-}" ]] && return 0
__WIKI_CONFIG_LOADED=1

# Run the python config CLI quietly. --project pins uv to .wiki/pyproject.toml
# so it works regardless of the user's CWD when they invoke `wiki`. Run as a
# module with scripts/ on PYTHONPATH (core.entry's shape) — core/config.py has
# no sys.path bootstrap of its own any more (M033-S02).
_wiki_config_py() {
  PYTHONPATH="$SCRIPTS_DIR" uv run --quiet --project "$WIKI_DIR" python -m core.config "$@" \
    2> >(grep -v '^warning:.*VIRTUAL_ENV' >&2)
}

config_get()  { _wiki_config_py get  "$1"; }
config_set()  { _wiki_config_py set  "$1" "$2"; }
