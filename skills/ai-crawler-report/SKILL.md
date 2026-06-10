---
name: ai-crawler-report
description: Report which AI bots (GPTBot, ClaudeBot, Claude-User, PerplexityBot, Bytespider, CCBot, GoogleOther, and more) are crawling your Vercel-hosted sites, and which paths they hit. Reads Vercel request logs (with user agents) and prints a per-site bot -> hits -> top paths table. Triggers on "which AI bots crawl", "ai crawler report", "is GPTBot hitting", "is ClaudeBot crawling", "AI bot traffic", "who's crawling the site", or "crawler report for [site]".
---

# AI Crawler Report (Vercel)

Per-site table of AI crawler activity — bot → hits → top paths — for Vercel-hosted
sites, pulled from Vercel request logs (which, unlike `vercel logs` CLI output,
include the client user agent).

## Setup — you do 1 thing, I do the rest

1. You: be logged in to the Vercel CLI (`vercel login`) on this machine — the
   skill reuses that token (or export `VERCEL_TOKEN`).

Then ask me to run setup + doctor; I resolve the team and project IDs and write
the machine-local config (`~/.config/ai-crawler-report/sites.json` — never in
the repo).

```bash
cd <skill-dir>
python3 cli.py setup --team <team-slug> --projects glp3wiki=glp3.wiki,drafty=drafty.im,johnkueh-com=johnkueh.com
python3 cli.py doctor   # token + config + live request-log ping per site
```

No dependencies — stdlib Python only.

## Commands

```bash
cd <skill-dir>

# The report (default last 24h, top 5 paths per bot)
python3 cli.py report

# Narrower window, one site, JSON output
python3 cli.py report --since 6h --site glp3.wiki --json
```

Output per site:

```
glp3.wiki  (4,213 requests scanned)
──────────────────────────────────────────────
  Bot                      Hits  Top paths
  GPTBot                    142  /retatrutide-dosage (38), / (22), ...
  PerplexityBot              31  / (12), /faq (8), ...
```

Every run also saves a JSON snapshot to `<skill-dir>/results/` so runs can be
compared over time.

## Coverage — be honest about the window

- **Data path (verified 2026-06):** Vercel Observability has bot/crawler
  insights, but they are dashboard-only on regular plans — the query builder
  and CSV/JSON export need Observability Plus, and there is no public bot API.
  This skill instead reads the request-logs backfill endpoint that powers
  `vercel logs` (`vercel.com/api/logs/request-logs`), authenticated with the
  CLI's own token. That endpoint returns `clientUserAgent` per request, which
  the CLI drops. It is internal — if it changes, run doctor and check here.
  Its `page` param is ignored server-side, so `cli.py` paginates by
  time-slicing `endDate` and deduping on `requestId`.
- **Retention (verified 2026-06):** on regular plans the backfill only goes
  back ~1 day; asking for ≥3 days returns `ExceedsBillingLimitError`. So a
  weekly run reports the trailing ~24h, not the whole week — the report says
  so in its footer. For trends, run daily (cron/schedule) and compare the
  saved snapshots in `results/`.
- Static/CDN-served requests ARE included (the endpoint logs all requests,
  not just function invocations).

## Bot list notes

The matcher covers GPTBot, ChatGPT-User, OAI-SearchBot, ClaudeBot, Claude-User,
Claude-SearchBot, PerplexityBot, Perplexity-User, GoogleOther, Bytespider,
CCBot, Meta-ExternalAgent, Amazonbot, Cohere, DuckAssistBot, MistralAI-User,
YouBot, AI2Bot, Diffbot, Timpibot (UA substrings in `cli.py`, verified
2026-06). Google-Extended and Applebot-Extended are robots.txt tokens, not
user agents — they never appear in logs; Gemini-related crawling shows up as
GoogleOther / Google-CloudVertexBot.

## Troubleshooting

- `doctor` fails on token → `vercel login`, or export `VERCEL_TOKEN`.
- `ExceedsBillingLimitError` → shrink `--since` (plan retention cap).
- A site shows 0 requests scanned → check the project name in
  `~/.config/ai-crawler-report/sites.json` (re-run setup).
- Truncation warning → the safety cap (20k requests/site) hit; use a smaller
  `--since`.
