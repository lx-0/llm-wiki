"""Adapters — concrete backends that satisfy domain-level Protocols.

Layout:

    adapters/
    ├── mailbox/
    │   ├── base.py         ← MailboxReader + MailboxFilter Protocols
    │   ├── thunderbird.py  ← S02
    │   ├── allinkl.py      ← S02
    │   └── gmail.py        ← S03
    └── (future substrates: calendar/, browser/, …)

Adapters import from `domain/`; the reverse is forbidden.
Adapters import from `wiki_config` only to read their own config block.
"""
