---
name: marketing-reddit
description: Pull structured data from Reddit (posts, threads, comments, and question clusters) through a headless browser that bypasses Reddit's JS bot-challenge. Use when Reddit's public .json API is 403-blocked from a server/cloud IP, or when mining a subreddit for content gaps, questions, or post data. Triggers on "mine reddit", "reddit-miner", "scrape subreddit", "reddit questions", "reddit 403", "reddit blocked", "pull reddit posts/comments".
---

# marketing-reddit
Reddit hard-blocks the public `.json` API for datacenter/cloud IPs and serves a
JS bot-challenge to anything automated. The decisive signal is the
**`HeadlessChrome` token in the User-Agent** — override it to a clean
`Chrome/...` UA and headless Chrome passes the challenge. The same-origin in-page
`fetch()` then carries the clearance cookie and returns real JSON.

This tool drives `agent-browser` (headless) with a clean UA — optionally through a
residential proxy — clears the challenge once per run, then fetches `.json` via
in-page `fetch()`, metering real wire bytes (proxy bandwidth) and cost. Question
detection + clustering are ported in-tool (no Python dependency).

Written in TypeScript, run with **bun** (runs `.ts` directly, zero install).

## Why headless works here

| Signal | Headless default | What we send | Verdict |
|--------|------------------|--------------|---------|
| User-Agent | `…HeadlessChrome/…` | `…Chrome/…` (clean) | **decisive** — clean UA passes |
| navigator.webdriver | true | true (unchanged) | not enough alone to block |

`--proxy`/`--user-agent` apply at agent-browser **daemon launch**, so the tool
runs `agent-browser close --all` at the start of a run to guarantee they take
effect (this also closes other agent-browser sessions).

## Setup

- `bun` installed (https://bun.sh) and `agent-browser` (`npm i -g agent-browser`).
- **Proxy is optional.** From a clean/residential IP it works direct. From a
  flagged datacenter/cloud IP (e.g. a CI box) you need a residential proxy.

```bash
# Store a proxy in machine-local config (chmod 600, OUTSIDE the skill repo — repo is public)
bun ~/.claude/skills/marketing-reddit/cli.ts setup --proxy "http://user:pass@host:port"

# Verify everything needed to run
bun ~/.claude/skills/marketing-reddit/cli.ts doctor
```

Proxy resolution order: `--proxy` flag → `REDDIT_PROXY` env → `~/.config/reddit-miner/config.json`.
The proxy secret is never read from or written to the skill repo. Use `--no-proxy` to force direct.

## Setup flow — guide the user through this

When the user first asks to set this up, don't dump manual steps — drive it. Run
`doctor`, then fix each FAIL yourself (ask before any global install or before
handling a proxy secret). `<cli>` below is `bun <this-skill-dir>/cli.ts`.

1. **Run `<cli> doctor` first.** It reports each requirement as PASS/FAIL with the
   exact fix. Work down the failures in order.

2. **`bun runtime` FAIL** → bun isn't installed. Offer to run:
   ```bash
   curl -fsSL https://bun.sh/install | bash
   ```

3. **`agent-browser installed` FAIL** → offer to run:
   ```bash
   npm i -g agent-browser
   ```

4. **`browser engine (Chrome) reachable` FAIL** → agent-browser has no browser to
   drive. Offer to run (downloads a Chromium it controls; existing Chrome/Brave is
   auto-detected too):
   ```bash
   agent-browser install
   ```

5. **`proxy credential resolved` is INFO, not a failure.** Ask the user: do they
   have a residential/ISP proxy? Reddit blocks datacenter IPs, so a cloud/CI box
   needs one; a clean home IP often works direct.
   - If yes, take the proxy URL and store it for them — never paste it into the repo:
     ```bash
     <cli> setup --proxy "http://user:pass@host:port"
     ```
   - If no, tell them it'll run direct and only works from a clean IP. They can add
     a proxy later with `setup`.

6. **Re-run `<cli> doctor` until it prints `RESULT: READY`.** Don't proceed past a
   FAIL — a failing engine or a flagged IP means every mine returns nothing.

7. **Smoke test** once READY:
   ```bash
   <cli> mine --subreddit <their-subreddit> --threads 5
   ```
   Confirm it returns clustered questions and a small bandwidth/cost line.

For convenience, suggest the user alias the CLI:
`alias reddit-miner='bun <this-skill-dir>/cli.ts'`.

## Usage

```bash
# Busiest posts (title, selftext, score, comments, flair, author)
bun ~/.claude/skills/marketing-reddit/cli.ts posts --subreddit Retatrutide --sort top --time month --limit 30

# A single thread's full comment tree (raw Reddit JSON)
bun ~/.claude/skills/marketing-reddit/cli.ts thread --url https://www.reddit.com/r/Retatrutide/comments/<id>/<slug>/

# Mine questions from POSTS + COMMENTS, mark answered/unanswered, cluster the gaps
bun ~/.claude/skills/marketing-reddit/cli.ts mine --subreddit Retatrutide --time month --threads 30 \
  --topic-keywords "reta|retatrutide|dose|side effect"
```

`--sort`: `top|hot|new|rising|controversial` (`--time` applies to `top`/`controversial`).
`--keep-open`: leave the browser session running for inspection.
`--no-proxy`: force a direct connection even if a proxy is configured.
`--no-rotate`: keep the proxy's stored `sessid` instead of minting a fresh one (see below).

## Sticky-session auto-rotation

Oxylabs-style sticky sessions (`sessid-…-sesstime-N`) expire (~10 min) and then fail
with SSL/connection errors mid-run — fatal for an unattended cron. If the proxy URL
carries a `sessid-`, the tool **mints a fresh sessid per run** (stable within the run
so the clearance cookie holds; fresh across runs so a stale session is never inherited).
The stored config is untouched. Pass `--no-rotate` to keep a fixed sessid.

## Output

- `posts` → `{subreddit, sort, posts: [...], bandwidth}`
- `thread` → `{thread: <raw Reddit listing JSON>, bandwidth}`
- `mine` → `{threads_scanned, posts_considered, questions, n_questions, n_unanswered, clusters_unanswered, top_questions, bandwidth}`
  - `questions[].source` is `reddit` (comment) or `reddit-post` (selftext) — "more than just comments".

Every run also prints a one-line bandwidth/cost summary to stderr.

## Bandwidth & cost

`bandwidth` reports real wire bytes (`transferSize`, post-gzip, incl. headers) — what
a metered proxy bills. Set `REDDIT_PROXY_USD_PER_GB` (default 8) for cost estimates.
Reference: a 30-thread `mine` ≈ **1 MB wire ≈ $0.008** at $8/GB (~955 runs per GB).

## Failure modes

- `could not clear Reddit JS challenge` → the IP (direct or proxy exit) is flagged.
  Add/rotate a residential proxy; sticky sessions hold one clean IP per run.
- `fetchJson failed … http 403 / blocked` → challenge expired mid-run; the tool
  retries, and a fresh run re-clears.
