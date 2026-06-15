---
name: comms-whatsapp
description: "Read and send WhatsApp messages from the command line via wacli (steipete/wacli, whatsmeow-based). Use when the user asks to search WhatsApp messages, send a WhatsApp message, list chats/groups/contacts, look up a thread, or download WhatsApp media. Triggers on 'WhatsApp', 'wacli', 'send a wa message', 'find that WhatsApp thread', 'WA chats', 'who said X on WhatsApp'."
---

# wacli — WhatsApp from the CLI

`wacli` is a Go CLI built on the [whatsmeow](https://github.com/tulir/whatsmeow) library. It pairs to the user's WhatsApp account as a multi-device companion (like WhatsApp Web), syncs messages to a **local SQLite DB** at `~/.wacli/wacli.db`, and exposes commands to read, search, and send.

Repo: https://github.com/steipete/wacli · install: `brew install steipete/tap/wacli`.

## Mental model — sync vs. read

Two distinct phases:

1. **Sync** (`wacli sync` / `wacli auth --follow`) connects to WhatsApp servers and writes new messages to the local DB. Runs as a long-lived process. New messages only land in the DB while sync is running.
2. **Read** (`wacli messages list/search/show`, `wacli chats list`) queries the local DB. Fast, offline, no network. Always reads what sync has already written.

So when the user asks "what did Alice send yesterday?" — the answer comes from the local DB. If the DB is stale, the user needs to run sync first. Use `wacli doctor` to check state.

## Critical gotchas

- **Single-writer lock.** The store is locked while `wacli sync` (or any connecting command) holds it. Trying to send while sync is running fails with a lock error. Tell the user to stop sync (`pkill -f 'wacli sync'`) before sending, or run `wacli send ...` in a window where sync isn't running. `wacli doctor` shows lock state.
- **History is shallow by default.** Initial sync only pulls recent messages from the user's primary device. Older history requires `wacli history backfill --chat <jid> --requests N`. Best-effort, may not return.
- **JIDs, not phone numbers.** Most read commands take `--chat <jid>` (e.g. `61400000000@s.whatsapp.net` for DMs, `<id>@g.us` for groups). `wacli send text` accepts `--to` as either phone or JID. To find a JID: `wacli chats list --json` or `wacli contacts search "name" --json`.
- **FTS5 may not be available.** `wacli doctor` shows `FTS5 false` on stock macOS SQLite — search falls back to LIKE, which is slower and less precise. Still usable for typical agent queries.
- **Do not commit `~/.wacli/`.** It contains the session keypair and message DB.

## Setup (once)

```sh
brew install steipete/tap/wacli
wacli auth                # shows QR; pair from phone → WhatsApp → Linked Devices
```

After pairing, kick off an initial sync that exits when idle:

```sh
wacli sync --once --idle-exit 30s
```

Or leave a follower running in the background to keep the local DB hot:

```sh
wacli sync --follow >/tmp/wacli-sync.log 2>&1 &
```

## Always pass `--json` when an agent is consuming output

Default output is human-formatted (columns, truncation, **senders shown as bare `@lid` numbers**). `--json` produces structured rows that pipe straight into `jq`. Use it everywhere the result feeds back to Claude — and **never attribute a quote from the human output** (see "Attribution" below).

Every `--json` response is an envelope: `{"success":bool, "data":…, "error":…}`. The payload is under `.data`:

- `messages list/search` → `.data.messages[]`, each with PascalCase keys: `ChatJID`, `ChatName`, `SenderJID`, `Timestamp`, `FromMe`, `Text`, `DisplayText`, `MediaType`, `Snippet`.
- `chats list` → `.data[]` with `JID`, `Kind`, `Name`, `LastMessageTS`.
- `contacts search` → `.data[]` with `JID`, `Phone`, `Name`, `Alias`, `Tags`.

```sh
wacli messages search "magic tags" --limit 20 --json \
  | jq '.data.messages[] | {ChatName, FromMe, Timestamp, Text}'
```

## Attribution — who sent each message (read before quoting anyone)

Getting "who said X" wrong is the most common and most damaging wacli mistake. Two traps cause it; both are avoided by the same two rules.

1. **`FromMe` is the only reliable speaker signal — never infer the sender from the JID or the human output.** In a DM both sides come back. Only the account owner is reliably identifiable, via the boolean `FromMe`. The other party's `SenderJID` is a raw `@lid` (e.g. `191624378347690@lid`), not a name, and the same person appears under device variants (`…@lid`, `…:19@lid`). The human output prints your messages as `me` and theirs as the bare `@lid`. **Rule: attribute every quote from `FromMe` — `true` = the account owner (you), `false` = the other party.** Resolve a `@lid` to a name with `wacli contacts search`/`show` only for labelling, never for deciding direction.

2. **`Text` is the message's own words; `DisplayText`/`Snippet` bundle quoted-reply context — so a search can pin a phrase on the wrong author.** When B replies to A, B's `DisplayText`/`Snippet` contains A's quoted line, so a substring search matches *both* A's original *and* B's reply — making it look like B said A's words. **Rule: when deciding who said a phrase, match the `Text` field only — never `DisplayText` or `Snippet`.**

Correct attribution recipe — a clean transcript labelled by `FromMe`, using each message's own `Text`:

```sh
wacli messages list --chat <jid> --limit 200 --json \
  | jq -r '.data.messages[] | select(.Text != "")
           | (if .FromMe then "ME  " else "THEM" end) + " | " + .Timestamp + " | " + .Text'
```

Build any "who said what" answer from this — not from the human output, not from `DisplayText`. If a phrase isn't in anyone's own `Text` (only in quoted replies), it means nobody in the window said it as their own message — don't attribute it, and `history backfill` if it predates the sync window.

## Read recipes

### Find the chat / contact JID

```sh
# Browse chats sorted by recent activity
wacli chats list --limit 30 --json

# Substring match on a contact name
wacli contacts search "Alice" --json

# Show full contact record (aliases, tags, JID, push name)
wacli contacts show --jid <jid> --json
```

### Search messages

```sh
# Global search across all chats
wacli messages search "<query>" --limit 50 --json

# Constrain to a chat
wacli messages search "<query>" --chat <jid> --json

# Constrain by sender (DMs include both sides; --from filters senders)
wacli messages search "<query>" --from <jid> --json

# Time window (RFC3339 or YYYY-MM-DD; --before is exclusive)
wacli messages search "<query>" --after 2026-04-01 --before 2026-04-28 --json

# Only media of a specific type
wacli messages search "" --chat <jid> --type image --json
```

### List a chat's recent messages

```sh
wacli messages list --chat <jid> --limit 100 --json
wacli messages list --chat <jid> --after 2026-04-25 --json
```

### Get context around a message

Once a search returns a hit, expand the surrounding thread:

```sh
wacli messages context --chat <jid> --id <message-id> --before 10 --after 10 --json
```

### Pull older messages a primary device hasn't yet shared

```sh
wacli history backfill --chat <jid> --count 50 --requests 3 --wait 60s
```

This asks the user's phone to send a history slab. Best-effort — phone must be online and recently active.

## Send recipes

> Stop any running `wacli sync` before send commands, or they'll fail on the store lock.

### Text

```sh
wacli send text --to <phone-or-jid> --message "your text"
# Phone form is auto-converted to JID; omit `+`. E.g. --to 61400000000
```

### File (image / video / audio / document)

```sh
wacli send file --to <jid> --file /abs/path.png --caption "look at this"
wacli send file --to <jid> --file /abs/notes.pdf --filename "Meeting notes.pdf"
```

`--mime` overrides detection if `wacli` mis-classifies an attachment.

## Group management

```sh
wacli groups list --json                              # known groups (from local DB)
wacli groups refresh                                  # pull fresh group list from server
wacli groups info --jid <group-jid>                   # participants, name, description
wacli groups join --code <invite-code>
wacli groups leave --jid <group-jid>
wacli groups participants add --jid <group> --participants <jid>,<jid>
wacli groups participants remove --jid <group> --participants <jid>
wacli groups invite get --jid <group-jid>             # current invite link
```

## Media download

Search returned a media message ID? Pull the binary:

```sh
wacli media download --chat <jid> --id <message-id> --output /tmp/media
```

Outputs to the configured media dir under the store by default.

## Diagnostics

```sh
wacli doctor                  # store path, lock state, auth, FTS availability
wacli doctor --connect        # try a live connection (requires lock be free)
wacli auth status             # auth-only check
wacli version
```

If `LOCKED true` and the user isn't expecting a sync running, kill it:

```sh
pkill -f 'wacli sync' && wacli doctor
```

## Common agent flows

### "Find that WhatsApp thread where we talked about X"

```sh
wacli messages search "X" --limit 30 --json \
  | jq '.data.messages[] | {ChatName, FromMe, Timestamp, Text}'
```

If a hit looks promising, fetch context:

```sh
wacli messages context --chat <jid> --id <message-id> --before 8 --after 8 --json
```

### "Send Alice the link to Y"

```sh
ALICE=$(wacli contacts search "Alice" --json | jq -r '.data[0].JID')
wacli send text --to "$ALICE" --message "Y: https://..."
```

### "What's in the family group lately?"

```sh
GROUP=$(wacli groups list --json | jq -r '.data[] | select(.Name=="Family") | .JID')
wacli messages list --chat "$GROUP" --limit 50 --after $(date -v-7d +%Y-%m-%d) --json
```

### Confirm sync is fresh before reporting

```sh
wacli sync --once --idle-exit 15s   # foreground catch-up, ~15s
wacli messages list --chat <jid> --limit 5 --json
```

## Output flags reference

Every command supports:

- `--json` — structured output (use this when piping to jq or returning to Claude)
- `--store <dir>` — alternate store dir (default `~/.wacli` or `$WACLI_STORE_DIR`)
- `--timeout <duration>` — bound non-sync commands (default 5m)

## What NOT to do

- Don't run `wacli send ...` while a `wacli sync --follow` is up — store is locked. Stop sync first.
- Don't paste a phone number with `+` or spaces to `--to` — strip to digits only (e.g. `61400000000`).
- Don't try to send to a JID you fished out of message metadata that ends in `@lid` (linked device alias) — use the `@s.whatsapp.net` form. `wacli contacts show` returns the right one.
- Don't attribute a quote from the sender JID, the human output, or `DisplayText`/`Snippet` — only `FromMe` (direction) + the message's own `Text` (content) are reliable. See "Attribution" above.
- Don't expect old history to be there. Run `wacli history backfill` for a specific chat if the user asks about messages older than the sync window.
- Don't commit `~/.wacli/` — it contains session keys.
