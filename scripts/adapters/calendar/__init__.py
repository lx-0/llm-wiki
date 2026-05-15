"""Calendar adapters — substrate-shaped readers for calendar APIs.

Today: `google.py` (Google Calendar v3 via the shared `core/google_oauth.py`
installed-app OAuth flow). Future kinds (Apple EventKit, Microsoft Graph,
CalDAV) land alongside it. `collectors/calendar.py` dispatches on the
per-account `kind:` discriminator under `personal.accounts.<id>.calendar`.
"""
