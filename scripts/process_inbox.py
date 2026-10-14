"""Entry module for `wiki process-inbox` — the logic lives in `preprocessors.inbox`.

Why a separate module: `preprocessors/__init__.py` imports `inbox` to register it, so
running the package module itself with `python -m preprocessors.inbox` executes it twice
(once on package import, once as `__main__` — Python's runpy warns about exactly that).
A top-level entry module outside the package has one execution and no warning.
"""

from preprocessors.inbox import main

if __name__ == "__main__":
    main()
