"""Entry module for `wiki ingest-html` — the logic lives in `preprocessors.html_ingest`.

Why a separate module: `preprocessors/__init__.py` imports `html_ingest` to register it,
so running the package module itself with `python -m preprocessors.html_ingest` executes
it twice (once on package import, once as `__main__` — Python's runpy warns about exactly
that). A top-level entry module outside the package has one execution and no warning.
"""

from preprocessors.html_ingest import main

if __name__ == "__main__":
    main()
