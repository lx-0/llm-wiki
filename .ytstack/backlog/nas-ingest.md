---
status: seed
---

# NAS Ingest

## Goal

A scanner that connects to a local NAS, walks selected shares, and writes file metadata into `raw/notes/nas/` so the compiler can index "what's on the NAS" without reading bodies.

## Connection protocol

**SMB > WebDAV > SSH** for this use case.

| Protocol | Pro | Con |
|---|---|---|
| **SMB** | persistent connection, native FS semantics, random access; QTS / Synology / TrueNAS shared-folder permissions are enforced | requires the NAS to expose SMB |
| **WebDAV** | works over HTTPS; firewall-friendly | per-file HTTP overhead — terrible for many small files |
| **SSH** | full filesystem access | bypasses share-level permissions (POSIX root); security regression |

Use SMB. Python client: `smbprotocol` — pure-Python, no `smbclient` CLI dependency.

## Three-stage scan (mirrors email pattern)

1. **Stage 1 — share enumeration**: list shares, walk top-level directories, count files by type and size. Output one summary per share.
2. **Stage 2 — selective deep-listing**: for shares the human has marked relevant, walk recursively. Output filename + size + mtime + first-N-bytes hash.
3. **Stage 3 — body ingest** (rare): for documents flagged worth indexing (PDFs, manuals, project files), pull bytes into `raw/papers/` or `raw/articles/` for the compiler to summarise.

Most of the value is at stages 1–2. Stage 3 is opt-in per file.

## Implementation outline

```python
# .wiki/scripts/scan-nas.py
import smbprotocol
from smbprotocol.connection import Connection
from smbprotocol.session import Session
from smbprotocol.tree import TreeConnect

# Credentials in .wiki/.env: NAS_HOST, NAS_USER, NAS_PASS
# Walk shares, write per-share metadata into raw/notes/nas/<share>-<date>.md
```

## Open questions

- Which shares are relevant? Per-user choice; configure via `config.yaml` (e.g. `collectors.nas.shares: [Multimedia, Documents]`).
- Privacy — exclude personal/family shares by default; opt-in only.
- Frequency — weekly piggyback; scans rarely change.
- Large file handling — skip files >100 MB at metadata stage; require manual opt-in for stage 3.

## Status

Seed. Concept agreed; implementation pending. Belongs in [collectors.md](collectors.md) family.
