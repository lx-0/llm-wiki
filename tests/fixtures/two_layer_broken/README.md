# Two-layer broken fixtures

Introduced in M005-S02-T03. Each `*.md` here deliberately violates one
M005-S01 schema rule. Used by `tests/test_two_layer_lint.py` to assert
that `check_two_layer_pages` and `check_action_item_syntax` surface the
right issue codes.

**Contract:** every file here MUST surface exactly the issue code its
filename advertises (plus optionally adjacent codes if violations cascade).
If a fixture starts passing the lint, either the lint regressed or the
fixture drifted -- fix one of them, not both.

These do NOT obey the "lint passes here" contract of `tests/fixtures/two_layer/`.
