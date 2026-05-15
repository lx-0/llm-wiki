# DMs collector — direct messages across WhatsApp/Telegram/Signal/iMessage/Discord/Slack-DMs

**Priority:** P3 — high signal per message (operator's personal conversations are the most unfiltered prose they write) but **highest implementation cost in the backlog**: N protocols, each with distinct auth + access + privacy semantics. Defer until cheaper substrates land first.

**Origin:** 2026-05-15 substrate-landscape conversation. Operator explicitly named DMs as a target ("dms (whatsapp, telegram, signal etc)") in the opening question.

## The gap it fills

DMs are where the operator actually thinks out loud with humans — birthday-trip planning, technical debates with friends, casual relationship maintenance, half-thoughts they'd never write in a public channel or daily/. The wiki currently has none of this context. Person-pages have meeting transcripts but no chat history; project-pages have GitHub PRs but no "I told Sam about this on WhatsApp" context.

## Source landscape

Each protocol is a distinct adapter. None share auth or schema.

| Protocol | Source | Format | Access notes |
|---|---|---|---|
| iMessage | `~/Library/Messages/chat.db` (SQLite) | Live, local | macOS only. Needs **Full Disk Access** (TCC). DB contains all iMessage + SMS history. Schema is undocumented but stable across releases. |
| WhatsApp | WhatsApp Desktop encrypted DB OR chat export | Encrypted-locally (key in keychain) OR manual ZIP export per chat | No official API for personal accounts. Decryption is reverse-engineered, fragile. Manual export per chat is the only stable path. |
| Telegram | Bot API + MTProto OR Telegram Desktop JSON export | API-live OR manual JSON export | Has an official API (Telethon / Pyrogram via personal API ID). Can read own chats. **Best protocol of the bunch.** |
| Signal | Signal Desktop SQLite + libsignal-protocol-decrypt | Encrypted-locally | Reverse-engineered, fragile, no official API. Defer or skip. |
| Discord DMs | Discord API (user token) | Live | Personal user tokens are TOS-discouraged. Manual export via `DiscordChatExporter` is the safer path. |
| Slack DMs | Slack API (user OAuth) | Live | Workspace-bound. Operator has multiple workspaces (Yesterday, customer workspaces). One adapter, multi-account. |

## Substrate boundary

Lands in `raw/transcripts/dms/<protocol>/<conversation-id>/<date>.md` — daily file per conversation per protocol. Frontmatter: `protocol`, `conversation_id`, `participants`, `message_count`, `date`. Body: chronological messages with sender + timestamp.

Substrate class = communication (similar to email, but conversational not threaded). Person-page entity-page is the natural consumer (cross-link conversation files into "recent DMs with <person>" section).

## Phasing — by protocol cost, not by yield

**Phase 1 — Telegram only.** Official API (Telethon), operator already has account. Bootstrap CLI `wiki telegram-auth` → API ID + hash + session file. Daily pull, watermark on `message.id`. Lift: 1.5 days.

**Phase 2 — Slack DMs.** Multi-workspace, OAuth-shaped. Reuse Slack API client if any. Lift: 1 day per workspace + 0.5 day for multi-tenant loop.

**Phase 3 — iMessage.** macOS SQLite read. Schema reverse-engineer task (well-trodden online — multiple OSS projects do this). TCC permission step is the friction. Lift: 1.5 days.

**Phase 4 — Discord** via DiscordChatExporter drop-folder. Operator runs export quarterly, drops to inbox, collector parses. Lift: 0.5 day.

**Phase 5 — WhatsApp + Signal.** Defer indefinitely. Reverse-engineered decryption is fragile and TOS-grey. If operator wants WhatsApp coverage, the realistic path is per-chat manual JSON export (WhatsApp's built-in "Export chat" feature) into drop-folder. Lift: unclear, depends on operator-export-frequency.

## Anti-slop heuristics

DMs are noisy. Most "ok 👍" / "lol" messages aren't substrate. Filters:

- Skip messages shorter than N characters (configurable, ~10).
- Skip messages that are pure reactions/stickers/single-emoji.
- Collapse runs of <30-second messages from the same sender into one "burst" entry — preserves conversation flow without per-line noise.
- Per-conversation allowlist OR blocklist: operator probably doesn't want every group-chat in the wiki; pin which conversations matter.
- Date-range filter at compile-time, not collector-time: ingest everything, let compile/query filter to relevant windows.

## Multi-tenant shape

`personal.accounts.<id>.dms` with nested `kind: telegram-api|slack-oauth|imessage-sqlite|discord-export` sub-configs. Each protocol-adapter ships separately; collector orchestrates whichever are enabled.

## Open questions

- **Privacy / consent.** DMs involve other humans who didn't consent to wiki ingestion. Default: redact other-party content past 30 days? Anonymize on compile? Operator decides per-conversation allowlist. AGENTS.md gets an explicit "DMs include third-party content" callout.
- **Group chats vs 1:1.** Different substrate shapes? Probably one file per group-chat-per-date with `participants: [...]` covering all members; per-person 1:1s use the same shape with `participants: [me, other]`.
- **Threading.** Slack/Discord have threads; Telegram has replies. Preserve `reply_to: <msg-id>` frontmatter on each message, or render visually with indent?
- **Reactions / emojis.** Probably drop entirely. Operator doesn't think in emoji-reaction signal.
- **Attachments.** Images/videos/links — store URL/path reference, don't blob into the wiki.

## Touchpoints

- `scripts/collectors/dms.py` — orchestrator, enumerates enabled protocols per account.
- `scripts/adapters/dms/telegram.py` — Telethon wrapper, session-file-managed.
- `scripts/adapters/dms/slack.py` — Slack Web API wrapper.
- `scripts/adapters/dms/imessage.py` — SQLite reader, schema-pinned.
- `scripts/adapters/dms/discord_export.py` — JSON-export drop-folder parser.
- `state/dms-state.json` — per-protocol per-conversation `last_message_id`.

## Lift estimate

- Phase 1 (Telegram): **1.5 days**
- Phase 2 (Slack, multi-workspace): **2 days**
- Phase 3 (iMessage): **1.5 days**
- Phase 4 (Discord drop-folder): **0.5 day**

**~5-6 days for Phases 1-4.** WhatsApp/Signal indefinite. Highest-cost substrate in this backlog batch.

## Risks

1. **Auth fragility.** Telegram session-files expire; Slack tokens refresh; iMessage TCC permission can revoke. Each adapter needs a clear "broken auth" loud-fail mode.
2. **Privacy explosion.** Group chats include people who never opted into wiki ingestion. Per-conversation allowlist default-deny is the only safe shape.
3. **Volume.** Operator probably has 10000+ messages across all protocols. Daily file structure handles it, but compile.py needs aggressive filtering — most messages aren't worth distilling.
4. **iMessage schema drift.** macOS updates have changed the chat.db schema before. Pin parser to known shape, fail-soft.
5. **TOS grey areas.** WhatsApp/Signal/Discord-user-tokens are explicitly discouraged. Stick to official APIs + manual exports.

## Ripens when

- Person-pages exist and feel hollow without DM context.
- OR operator notices "I told Sam about this on Telegram" and the wiki has no idea.
- OR meeting-substrate (jamie/gmeet/calendar) feels saturated and the next substrate is genuinely the bottleneck.

## Status

Backlog, defer. The hardest substrate in the second wave: N protocols, fragile auth, third-party privacy concerns. Recommend Phase 1 (Telegram) only as a wedge — defer the rest until person-pages prove they want DM context.
