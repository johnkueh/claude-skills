---
name: marketing-reddit
description: Pull structured data from Reddit (posts, threads, comments, and question clusters) through a headless browser that bypasses Reddit's JS bot-challenge, and optionally LLM-classify the mined snippets into pain / demand / question gaps with Gemini (when a GEMINI_API_KEY is set; falls back to the in-tool heuristic otherwise). Use when Reddit's public .json API is 403-blocked from a server/cloud IP, or when mining a subreddit for content gaps, questions, pain points, product ideas, or post data. Triggers on "mine reddit", "reddit-miner", "scrape subreddit", "reddit questions", "reddit pain points", "reddit product ideas", "classify reddit", "reddit 403", "reddit blocked", "pull reddit posts/comments".
---

# marketing-reddit
Reddit hard-blocks the public `.json` API for datacenter/cloud IPs and serves a
JS bot-challenge to anything automated. The decisive signal is the
**`HeadlessChrome` token in the User-Agent** — override it to a clean
`Chrome/...` UA and headless Chrome passes the challenge. The same-origin in-page
`fetch()` then carries the clearance cookie and returns real JSON.

This tool drives `agent-browser` (headless) with a clean UA through a
residential proxy, clears the challenge once per run, then fetches `.json` via
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
- **Proxy is required for mining.** A direct connection exposes your IP to Reddit
  and risks a ban, so `posts`/`thread`/`mine`/`classify` refuse to run without one;
  `--no-proxy` is the explicit accept-the-risk override.

```bash
# Store a proxy in machine-local config (chmod 600, OUTSIDE the skill repo — repo is public)
bun ~/.claude/skills/marketing-reddit/cli.ts setup --proxy "http://user:pass@host:port"

# Verify everything needed to run
bun ~/.claude/skills/marketing-reddit/cli.ts doctor
```

Proxy resolution order: `--proxy` flag → `REDDIT_PROXY` env → `~/.config/reddit-miner/config.json`.
The proxy secret is never read from or written to the skill repo. Use `--no-proxy` only to
explicitly accept the ban risk and run direct.

Gemini key resolution (for `classify`): `GEMINI_API_KEY` env → `gemini_key` in
`~/.config/reddit-miner/config.json` (set via `setup --gemini-key <key>`). Optional — without it
`classify` falls back to the heuristic question detector. Like the proxy, the key is never read
from or written to the skill repo.

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

5. **A proxy is required for mining.** Ask the user for a residential/ISP proxy —
   mining direct exposes their IP to Reddit and risks a ban, so the mining commands
   refuse to run without one.
   - Take the proxy URL and store it for them — never paste it into the repo:
     ```bash
     <cli> setup --proxy "http://user:pass@host:port"
     ```
   - If they insist on running without one, `--no-proxy` is the explicit
     accept-the-risk override — the ban risk is theirs.

6. **`LLM classification` is INFO, not a failure.** If they want pain/demand mining
   (not just questions), set a Gemini key so `classify` uses `gemini-2.5-flash`:
   ```bash
   <cli> setup --gemini-key "<key>"     # or: export GEMINI_API_KEY=...
   ```
   `doctor` then shows `[PASS] LLM classification — gemini-2.5-flash live`. Without it,
   `classify` still works via the heuristic fallback (questions only).

7. **Re-run `<cli> doctor` until it prints `RESULT: READY`.** Don't proceed past a
   FAIL — a failing engine or a flagged IP means every mine returns nothing.

8. **Smoke test** once READY:
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

# Classify every post + comment into pain / demand / question (Gemini if a key is set)
bun ~/.claude/skills/marketing-reddit/cli.ts classify --subreddit Retatrutide --time year --threads 30 \
  --for "frustrations with TRACKING or LOGGING doses/food/weight, reminder apps, or tracking tools"
```

`--sort`: `top|hot|new|rising|controversial` (`--time` applies to `top`/`controversial`).
`--keep-open`: leave the browser session running for inspection.
`--no-proxy`: run direct without a proxy — explicit accept-the-risk override (exposes your IP to Reddit).
`--no-rotate`: keep the proxy's stored `sessid` instead of minting a fresh one (see below).
`classify` flags: `--for "<focus>"` (relevance filter — see below), `--top N` (rows per bucket, default 40),
`--min-score N` / `--min-comments N` (engagement floor on the posts mined).

## LLM classification (`classify`) — pain / demand / question gaps

`mine` finds **questions** (it keys off `?` + a question word). That's perfect for content
gaps, but it structurally misses **declarative complaints** ("I can't get X to work", "the app
doesn't support my med") and **product demand** ("is there an app for this?") — which carry no
question mark. `classify` closes that: it fetches the same posts + comment bodies, then labels
each snippet `pain | demand | question | other`.

- **With a Gemini key** (default when one resolves) it uses `gemini-2.5-flash` — it reads
  meaning, so it catches keyword-free complaints/demand a regex can't. Benchmarked **~100%
  recall** on a logger-app mine vs ~60% for the best in-tool heuristic (precision ~50% — the
  surviving set is small enough to eyeball).
- **Without a key** it falls back to the heuristic question detector and tells you how to enable
  the LLM. No new dependency — it's a plain HTTPS call, like the Reddit fetch.

**`--for "<focus>"` is a relevance filter, and phrasing matters.** Name the *frustration you're
hunting*, not just the topic. `--for "GLP-1 logger app"` is read as a topic (every post qualifies);
`--for "frustrations with TRACKING/LOGGING doses, reminder apps, charts — not general side-effects"`
filters tightly. With no `--for`, it labels general pain/demand/questions across the whole mine
(good for broad content-gap discovery).

**The keyword/topic funnel leaks the best signal.** Pre-filtering to "app/track/log" keywords before
classifying drops the highest-value, keyword-free themes (e.g. adherence "I keep falling behind on
doses", anti-obsession "manic daily weighing"). For product discovery, classify the **whole** mine
(don't pre-filter) and let the LLM judge — at flash prices the full pass is cheap (see costs).

Enable the key: `export GEMINI_API_KEY=...` or store it machine-local with
`cli.ts setup --gemini-key <key>` (written to `~/.config/reddit-miner/config.json`, chmod 600,
never the repo). `doctor` reports whether classification is live and runs a one-snippet probe.

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
- `classify` (Gemini) → `{subreddit, classifier:"gemini:…", for, threads_scanned, posts_considered, n_units, n_pain, n_demand, n_question, n_other, gemini_cost_est_usd, shown_per_bucket, pain:[…], demand:[…], questions:[…]}`
  - each row: `{text, score, source:"post"|"comment", thread_title, permalink}`. `n_*` are full counts; arrays are capped to `--top`.
- `classify` (no key, heuristic fallback) → `{subreddit, classifier:"heuristic", threads_scanned, posts_considered, n_units, n_questions, questions:[…]}`

Every run also prints a one-line bandwidth/cost summary to stderr.

## Bandwidth & cost

`bandwidth` reports real wire bytes (`transferSize`, post-gzip, incl. headers) — what
a metered proxy bills. Set `REDDIT_PROXY_USD_PER_GB` (default 8) for cost estimates.
Reference: a 30-thread `mine` ≈ **1 MB wire ≈ $0.008** at $8/GB (~955 runs per GB).

`classify` adds Gemini cost on top: `gemini-2.5-flash` ≈ **$0.000027 per classified unit**
(`gemini_cost_est_usd` in the output). A 30-thread mine is ~8–10k units ≈ **$0.25 per run** —
cheap for a far-higher-recall pass. Override the model with `REDDIT_GEMINI_MODEL`.

## Failure modes

- `could not clear Reddit JS challenge` → the IP (direct or proxy exit) is flagged.
  Add/rotate a residential proxy; sticky sessions hold one clean IP per run.
- `fetchJson failed … http 403 / blocked` → challenge expired mid-run; the tool
  retries, and a fresh run re-clears.
