# Dev-checkout `ROOT_DIR` inference — the residue after the test fence

**Status:** open, low urgency. Filed 2026-07-25 alongside commit `6548069`.
**Related:** `.ytstack/AD-HOC-test-vault-write-isolation-SUMMARY.md`, DECISIONS 2026-07-25, KNOWLEDGE "The test suite wrote real vault files next to the checkout".

## The part that is fixed

`tests/conftest.py` + `tests/_vault_isolation.py` fence the **test process**: `core.daily_capture.DAILY_DIR` is repointed at a tmp sink, and any write landing under `ROOT_DIR` but outside `WIKI_DIR` raises `VaultWriteEscape`. A forgotten redirect in a new collector test is now a red test.

## The part that is not

1. **Only `DAILY_DIR` is proactively repointed.** `RAW_DIR`, `KNOWLEDGE_DIR`, `INBOX_DIR`, `WORKSPACE_DIR` and the `_dashboard-*.md` targets rely on the guard catching them at the moment of the write. That is a correct safety net but a worse developer experience: the test fails with "escaped the checkout" instead of quietly working against tmp. Consider a fixture that repoints the whole vault-content surface at one tmp vault root, so writes just land somewhere harmless.

   Tension to resolve first: the constants are copied by value into ~20 modules at import time (`from core.paths import RAW_DIR`), so patching `core.paths` alone does not reach them. Either the modules stop copying (read `paths.RAW_DIR` at call time), or the fixture walks `sys.modules` and patches every copy — the second is magic and will rot. The first is the honest fix and is a real refactor.

2. **Non-test entry points still write outside the checkout.** Running `wiki flush`, dashboard regeneration, or any engine script from the repo creates `<repo>/../_dashboard-*.md`, `<repo>/../daily/...` etc. This is exactly how `_dashboard-{lint,stats}.md` ended up in `projects/lx-0/` on 2026-05-17. The guard is a pytest fixture and does not apply here.

   Options sketched, none chosen:
   - **Explicit vault override.** A `WIKI_VAULT` env var consulted by `core/paths.py` before falling back to `WIKI_DIR.parent`. Small, but it adds a second source of truth for the vault root, and every consumer that already reads `ROOT_DIR` inherits it for free.
   - **Refuse to run from a checkout.** Detect "`WIKI_DIR` is a git repo whose parent is not a vault" (no `AGENTS.md`, no `knowledge/`) and hard-error on write commands with a pointer at `--project <vault>/.wiki`. Loudest, most annoying, zero silent damage.
   - **Leave it.** Development runs against a real vault are the norm; the 2026-05-17 incident produced two junk files in two months. Cheapest, and the cost is bounded now that we know the signature.

## Trigger to pick this up

Another stray artifact appears next to a checkout, OR someone hits the guard and finds "repoint the constant" is not actually possible because the write site reads a copied-by-value import from a module the test never touches. Either event turns option 1's refactor from tidy-up into a blocker.
