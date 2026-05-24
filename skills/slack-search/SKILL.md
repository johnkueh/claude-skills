---
name: slack-search
description: Search Slack messages and fetch threads. Use when the user asks to find Slack conversations, look up a colleague, list channels, or pull a specific thread by URL. Personal-token-based (xoxp-...). Triggers on "search Slack", "find that Slack thread", "what did X say in Slack", "Slack DM history", "pull this Slack URL", "who in [channel]", "Slack message about", "look up [name] on Slack", or any Slack permalink (slack.com/archives/...).
---

# slack-search

Search Slack workspace content using your personal user token (xoxp-...).

## Setup

Add your Slack User Token to `~/.claude/settings.json` under `env`:

```json
{
  "env": {
    "SLACK_USER_TOKEN": "xoxp-...",
    "SLACK_USER_ID": "U..."
  }
}
```

The skill also falls back to a `.env` in the current working directory if present.

## Commands

All commands accept `--json` for structured output (useful when piping to `jq`).

### Search messages

```bash
uv run python slack_search.py search "keyword"

# Filters
uv run python slack_search.py search "deploy" --channel engineering --from sam --limit 10

# Slack search modifiers also work inside the query
uv run python slack_search.py search "bug after:2026-01-01 has:link"
```

### Fetch a thread

Paste any Slack permalink, or pass `<channel-id>:<ts>`:

```bash
uv run python slack_search.py thread https://your-team.slack.com/archives/C0123456/p1700000000000001
uv run python slack_search.py thread C0123456:1700000000.000001 --json
```

Returns the parent message + all replies, with `<@U…>` mentions resolved to `@username`. Each message also includes a `files` array with metadata for any attached images / videos / docs.

### Download attachments

`search` and `thread` both accept `--download [DIR]`. When set, file attachments
on each message are downloaded and the local path is added to the `files`
entry as `local_path`. Omit DIR to use `~/.cache/slack-search/files/<scope>/`.

```bash
# default cache dir
uv run python slack_search.py thread C0123456:1700000000.000001 --download --json

# explicit dir
uv run python slack_search.py thread <permalink> --download /tmp/slack-files
```

Requires the `files:read` scope on the user token; without it Slack returns the
workspace login HTML and the downloader prints a clear error.

### List channels / users / profile (lookup helpers for filters)

```bash
uv run python slack_search.py channels   # public + private the user is in
uv run python slack_search.py users      # active workspace members
uv run python slack_search.py me         # your profile (auth check)
```

## Search modifiers

Slack's native modifiers work inside the query string:

- `in:channel` — restrict to channel
- `from:user` — restrict to author
- `before:YYYY-MM-DD`, `after:YYYY-MM-DD`
- `has:link`, `has:reaction`

`--channel` / `--from` are sugar for `in:` / `from:`.

## Required scopes

Personal user token (xoxp-…) needs:

- `search:read`
- `channels:read`, `groups:read`
- `users:read`
- `channels:history`, `groups:history` (for `thread`)
- `files:read` (only required for `--download`; without it, Slack bounces file URLs to the workspace login page)

## Troubleshooting

- **`missing_scope`**: add the missing scope in your Slack App's OAuth settings, then reinstall the app.
- **`invalid_auth`**: token expired — regenerate at https://api.slack.com/apps.
- **Token not picked up**: confirm with `printenv SLACK_USER_TOKEN`. If empty, the env block in `~/.claude/settings.json` may not have been reloaded — restart Claude Code.
