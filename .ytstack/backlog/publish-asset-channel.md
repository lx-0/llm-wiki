# Backlog: publish — non-markdown assets + secret-gate leftovers

Parked 2026-08-25 at M030 close. Two independent threads.

## 1. Binary/JSON asset channel (upstream ask)

The producer contract is markdown-only ("one markdown file per article"), so
3860 vault files have no channel: 2473 png + ~150 jpg/jpeg (pictures,
screenshot thumbs), 904 json (curiosity requests etc.), 44 txt, yaml, audio.
The dry-run counts them loudly on every run.

If the operator wants them remote, this is a context-mcp FEATURE ASK (asset
channel / binary files on knowledge packages), not a producer workaround —
REGEL #2: message to the meinkontext agent via the operator, same pattern as
the producer-contract request. Note: quota math changes materially with
images (~100 MB org quota today).

## 2. Secret-gate-skipped articles (operator content decision)

Four files are permanently skipped by the server's secret scan (correct
behavior; listed in every publish report):

- `daily/2026-06-26/sessions.md` — sk-prefix key-shaped value
- `daily/2026-07-02/sessions.md` — sk-prefix key-shaped value
- `knowledge/concepts/accept-multiple-paste-formats.md` — private-key-block shape
- `knowledge/concepts/ssh-pubkey-pure-js-derivation.md` — private-key-block shape

Options per file: sanitize locally (mask the key-shaped span → publishes on
the next piggyback fire) or accept local-only. The knowledge/ two likely
contain EXAMPLE key material — sanitizing loses little.

## 3. Reach-anywhere caveat (verification debt, cheap)

M030-S03-T03 closed passed-with-caveats: other-device client + claude.ai
custom connector untested (operator had no second machine at hand). Confirm
opportunistically: next time on another device, `claude mcp add --transport
http meinkontext https://dev.meinkontext.de/mcp` → /mcp authenticate → ask a
wiki question with the Mac asleep. One success closes the caveat.
