"""Adapters — concrete backends that satisfy domain-level Protocols.

Layout:

    adapters/
    ├── calendar/google.py  ← Google Calendar v3 client (collectors/calendar_collector.py)
    ├── drive/google.py     ← Google Drive v3 client (collectors/gmeet.py)
    ├── health/             ← Oura REST client, Apple Health Export.xml parser
    └── mailbox/            ← MailboxReader / MailboxFilter Protocols (base.py) + the
                              gmail, thunderbird, imap and allinkl backends

Adapters import from `domain/`; the reverse is forbidden.
Adapters import from `core.config` only to read their own config block.
"""
