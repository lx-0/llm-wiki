# `intents-seen.json` onto the state store (M034 candidate, surfaced in M033-S03-T05)

**Status:** candidate; the producer's decision. Recorded 2026-10-15 (M033-S03-T05).

**Today:** `producers/intents.py` keeps the seen-set of intent sources as a JSON **list**
(`_load_seen` / `_mark_seen`: read, `set()`, add, `write_text(json.dumps(sorted(seen)))`).
It is the one runtime state file under `.wiki/state/` that still writes by hand — the T05
guard `test_state_files_are_written_through_the_seam` allow-lists it by reason, because
`core.state_store.StateStore` holds a JSON **object** at the top level and folding the
file would change its on-disk shape.

**Why it matters:** the hand-rolled write is neither locked nor atomic — a kill mid-write
leaves a torn file that `_load_seen` reads as "nothing seen", and every previously seen
source re-emits one intent record into `workspace/inbox/` (duplicates the operator has to
dismiss). The compile loop that runs the producer is single-process today, so the race
side is theoretical; the torn-write side is not.

**Proposal:** `{"seen": [...]}` through `store_for(_SEEN_STATE)` with a one-time
tolerance for the legacy list (`isinstance(data, list)` → migrate on first read, as
`email_collector._migrate_legacy` does for `email-state.json`), then drop the allow-list
entry. Needs the migration written in the same commit (CLAUDE.md config/state rule) and a
test that a legacy list file reads as the same seen-set.
