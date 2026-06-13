# Folder-curiosity producer: numbered-candidate-index gap schema

**Status:** designed, not built (2026-06-13). The last gap to an organic
folder-deep-scan request on lxw.

## Problem

The folder producer now retrieves the right candidate files (coverage+recency
ranking, verified rank-0 on lxw) and the local model engages (2 gaps, 13 KB
prompt, no timeout). But llama3.1:8b fills `file_path` with placeholders
(`/path/to/file.pdf`) instead of copying a real candidate path — the
"copy verbatim from a backticked entry" instruction is not reliably honored by
an 8B model under schema. The anchor rejects them → 0 kept.

## Fix (mirror the email pass's proven mechanism)

The EMAIL curiosity pass avoids exactly this by giving a NUMBERED folder list
and taking back `folder_index` (int), mapping index→path in Python. Do the same
for the folder pass:

1. `_load_folder_digests` (over-budget path) already produces the per-root
   candidate lines. Number them globally: `[1] <path> · dates`, `[2] …`.
2. Build an index→(root_id, file_path) map alongside the rendered block.
3. Schema: replace `root_id` + `file_path` strings with
   `candidate_index: {type: integer, minimum: 1, maximum: N}`.
4. After parse: map `candidate_index` → (root_id, file_path); the file-exists
   anchor becomes "index in range" (still sound — the map is built from the
   complete index).
5. Prompt `compile_curiosity_folder.md`: "pick the NUMBER of the candidate
   file that answers the gap" instead of "copy the path verbatim".

Under-budget (full-inject) path: either also number, or keep the verbatim path
there (small vaults, the model has the whole tree) — decide during build.

## Open question

Even with valid file_paths, will llama3.1:8b rate `file_confidence` ≥ the
operator's threshold (lxw pins 4; engine default 3) on metadata-only judgment?
If it stays conservative, consider: a dedicated lower folder threshold, or a
stronger curiosity model for the folder pass only. Observe after the index fix.

## Verified-good foundation (do not redo)

- candidate retrieval architecture (small prompt, model judges short list)
- coverage+recency ranking (`_rank_candidate_lines`) — surfaces the target
  file at rank 0 on the real lxw vault
- commits 9046a4f (retrieval), 1672e6b (coverage+recency)
