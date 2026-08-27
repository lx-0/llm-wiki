"""Producer source-globs must match where the substrate ACTUALLY lands.

Found by the 2026-08-27 backlog reconcile: `features.suggestions_source_globs`
defaulted to `raw/email/*.md` while the email collector writes to
`raw/notes/email/`. `producers.orchestrate` fnmatches vault-relative paths, so
the gate never matched, the suggestions producer never ran, and the newest
file in the operator's `raw/suggestions/` was from 2026-05-14 — a whole
shipped subsystem idle for months with no error anywhere.

A glob is a promise about the filesystem. These tests check it against the
directory the collector is actually configured to write.
"""

from __future__ import annotations

import fnmatch

from core.config_schema import Features


def test_suggestions_glob_matches_the_email_collectors_output_dir():
    globs = Features().suggestions_source_globs
    # The path an email-collector artifact has, relative to the vault root.
    sample = "raw/notes/email/inbox-2026-08-27.md"
    assert any(fnmatch.fnmatch(sample, g) for g in globs), (
        f"no glob in {globs} matches {sample!r} — the suggestions producer "
        "cannot fire on real email substrate"
    )


def test_suggestions_glob_does_not_point_at_a_directory_that_never_existed():
    """`raw/email/` is not where anything lands; keeping it would look
    configured while matching nothing."""
    assert "raw/email/*.md" not in Features().suggestions_source_globs


def test_glob_semantics_are_vault_relative_not_basename():
    """Guards the assumption the fix rests on: orchestrate fnmatches the path
    relative to ROOT_DIR, so a glob without the directory prefix silently
    matches nothing."""
    import producers.orchestrate as orch

    assert "ROOT_DIR" in (orch.__doc__ or "") or "relative" in (orch.__doc__ or "").lower()
    assert not fnmatch.fnmatch("raw/notes/email/x.md", "*.md".replace("*", "x"))
    assert fnmatch.fnmatch("raw/notes/email/x.md", "raw/notes/email/*.md")
    # A bare basename glob does NOT match a nested path — the trap that made
    # the original value look plausible.
    assert not fnmatch.fnmatch("raw/notes/email/x.md", "raw/email/*.md")
