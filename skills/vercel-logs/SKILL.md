---
name: vercel-logs
description: "Query Vercel runtime and build logs to debug production issues. PREFER THE CLI over the MCP for log search — the MCP runtime-logs tool truncates message bodies. Use when debugging a production error, investigating a 500 / 4xx, looking at deployment build output, or any 'what happened on Vercel' question. Triggers on 'vercel logs', 'production error', 'vercel debug', 'deployment logs', 'build logs', 'what's failing in prod', 'check vercel'."
---

# vercel-logs

Query Vercel logs from the command line. CLI ≥51.7 supports a backfill mode the MCP doesn't replicate.

## First — does this project have bq-analytics installed?

If yes (the repo has `bq-analytics` in `package.json` or a `/api/internal/log-drain/route.ts` file), **prefer the `bq-analytics-query` skill** for log search. BQ has:

- 30+ day retention vs Vercel's 1–3 days
- Structured columns (path, status, level, request_id) instead of substring grep
- JSON output that Claude can pipe into reasoning

`vercel-logs` is still right for these cases even when bq-analytics is installed:

- **Live tail** during a deploy or while reproducing a bug — drain has ~1–2 min lag
- **Build logs** — drain only captures runtime, not compile errors / install failures
- **The first ~10 minutes after a new deployment** — drain delivery hasn't caught up

For projects without bq-analytics, `vercel-logs` is the canonical tool — keep reading.

## Hard rule: prefer the CLI over the MCP for log search

Both `mcp__plugin_vercel_vercel__get_runtime_logs` and the dashboard exist, but **for inspecting log message bodies the CLI is the canonical tool**.

- The MCP `get_runtime_logs` tool **truncates the message column** — useless for reading stack traces or request bodies.
- The default `vercel logs <deployment>` is **stream-only** — waits forever for new logs, never returns past output.
- The CLI ≥51.7 has backfill flags that fix both and let you read full historical bodies.

Use the MCP tool **only for counting** (e.g. "how many 500s in the last hour by route?"). Use the CLI for **reading**.

## Canonical command

```sh
vercel logs --no-follow --no-branch --since 30m --query "<keyword>" --expand --limit 50
```

| Flag | Why it matters |
|---|---|
| `--no-follow` | Exits after fetching, doesn't stream. |
| `--no-branch` | Disables the implicit "current git branch" filter. **Without this, non-main branches return "no logs found"** even when there clearly are logs. |
| `--since <relative>` | Time window. Accepts `30m`, `1h`, `6h`, `7d`. |
| `--query "<keyword>"` | Substring match across the message body. Quote it. |
| `--expand` | Full message bodies, not truncated. Without this you get the same useless one-liners as the MCP. |
| `--limit 50` | Cap. Bump if needed. |

## Other useful flags

- **Specific deployment**: pass URL or alias as a positional — `vercel logs https://app-abc123.vercel.app --no-follow --since 1h --expand`
- **Filter by status**: `--status 500` (errors), `--status 404`
- **Filter by function path**: `--path /api/foo`
- **Stream live**: drop `--no-follow` to tail in real-time. Useful when reproducing an issue.

## Common debugging flows

### "Why is X failing in production?"

1. Reproduce the issue (or note the time it happened).
2. `vercel logs --no-follow --no-branch --since 30m --query "<keyword>" --expand --limit 50`
3. Read full message bodies. Look for the stack trace, request path, and error type.

### "Did my latest deployment break something?"

```sh
vercel ls --limit 1                    # get the latest deployment URL
vercel logs <url> --no-follow --since 1h --status 500 --expand --limit 100
```

### "What did the build say?"

Build logs are separate from runtime:

```sh
vercel inspect <deployment-url> --logs
```

Or via MCP: `get_deployment_build_logs` — this one **does** return useful detail for builds, fine to use.

## What NOT to do

- Don't use bare `vercel logs <deployment>` — streams forever, you'll wait for nothing.
- Don't use `get_runtime_logs` (MCP) for inspection — only for counting.
- Don't forget `--no-branch` if you're on a feature branch and getting empty results.
- Don't grep through the dashboard for stack traces — it's painful and doesn't give you `--query` substring matching.

## Setup

```sh
pnpm add -g vercel@latest    # or: npm i -g vercel@latest
vercel login
vercel link                  # in the project repo
```
