---
name: aeo-monitor
description: Track AI chatbot citations (ChatGPT, Perplexity, Google AI Overview, Claude) for any project. Use when the user wants to monitor brand/domain mentions in AI search, track which queries cite their site, set up AEO/GEO monitoring, or measure visibility in chatbot responses. Triggers on "track AI citations", "monitor ChatGPT mentions", "AEO monitoring", "GEO tracking", "AI search visibility", "are we cited in ChatGPT", "what do chatbots say about us", "track mentions in Perplexity", or any project-level question about appearing in AI answers.
---

# AEO Monitor

Track how often AI chatbots cite your site for queries that matter to your audience. Stores everything locally in SQLite per project; tracks actual cost per provider; works via `/loop` for recurring checks.

## How to use it

This is a Node.js CLI. Invoke via the `aeo` wrapper script at the skill root:

```
<plugin-path>/skills/aeo-monitor/aeo <command>
```

The wrapper auto-installs deps on first run (pnpm preferred, npm fallback). The skill data **lives with the user's project**, not with the plugin — every command is run from inside the project directory (`cwd`), and writes to `<project>/.aeo/`.

For convenience, suggest the user alias it:

```
alias aeo='<plugin-path>/skills/aeo-monitor/aeo'
```

Requirements:
- Node 22+
- pnpm or npm (for the one-time dep install)

## Setup flow — guide the user through this

When the user first asks to set this up for a project:

1. **Verify env vars are set** — run `aeo doctor`. If any of these are missing, give them the get-it links and stop:
   - `FIRECRAWL_API_KEY` (firecrawl.dev) — for ChatGPT + Perplexity
   - `DATAFORSEO_API_KEY` (base64 of `login:password`) — for Google AI Overview
   - `GEMINI_API_KEY` (aistudio.google.com/apikey) — for structured extraction
   - `ANTHROPIC_API_KEY` (optional, console.anthropic.com) — for Claude

2. **`cd` into the user's project**, then `aeo init`. This creates `<project>/.aeo/runs.sqlite`.

3. **Research the project before adding queries** — read `CLAUDE.md`, `README.md`, `src/lib/content-registry.ts` (or equivalent), the site map. Understand:
   - What does this project do?
   - Who is the audience?
   - What questions do they ask AI chatbots?

4. **Propose 10-20 natural-language queries** the audience would actually ask. Examples:
   - "what is X and how does it work" (general)
   - "X vs competitor" (comparison)
   - "X side effects / pricing / when launches" (specific)
   - "how do I do Y" (how-to that the project answers)

   Don't just list keywords. Phrase them like real people type into ChatGPT.

5. **Confirm queries with the user**, then add them one at a time:
   ```
   aeo query add "what is retatrutide and how does it work"
   aeo query add "retatrutide vs mounjaro for weight loss"
   ...
   ```

6. **Add domains to detect.** The user's own domain + close competitors:
   ```
   aeo domain add glp3.wiki --label own
   aeo domain add www.glp3.wiki --label own
   aeo domain add competitor.com --label competitor
   ```

7. **Dry run** to confirm cost: `aeo run --dry-run`. Then **first real run**: `aeo run`.

8. **(Optional) Set a budget** if they want a warning when costs rise: `aeo budget set 1000` (= $10/mo).

9. **Suggest a /loop or /schedule** for ongoing monitoring:
   - `/loop 24h aeo run` for daily checks
   - Or use the `schedule` skill for cron-based remote runs

## Daily run flow (used by /loop)

```
aeo run               # runs all queries × all configured platforms
aeo report --days 7   # citation rate per query per platform
aeo cost --days 7     # actual spend last 7 days
```

The user can also restrict scope:
- `aeo run --platform chatgpt`
- `aeo run --query "specific question"`
- `aeo run --dry-run` (cost estimate without executing)

## Reading results

After a run, the structured data is in SQLite. Useful commands:

| Question | Command |
|---|---|
| Are we cited at all? | `aeo report --days 7` |
| For which queries? | `aeo history --query "..."` |
| Who are we losing to? | `aeo competitors --days 30` |
| What did we spend? | `aeo cost --by provider` |
| Which queries cost most? | `aeo cost --by query` |

## Cost reference

Per query × platform (rough):
- ChatGPT (Firecrawl + Gemini extract): ~$0.012
- Perplexity (Firecrawl + Gemini extract): ~$0.012
- Google AI Overview (DataForSEO + Gemini extract): ~$0.003
- Claude (Anthropic Haiku + Gemini extract): ~$0.010

A full daily run with 10 queries × 4 platforms ≈ $0.40/day or ~$12/month per project.

## When user wants new queries

Don't just guess. Sources of real questions people ask:

1. **GA4 referrer data** — what queries from ChatGPT/Perplexity drove existing traffic? (Look at landing pages with `utm_source=chatgpt.com`.)
2. **GSC top impressions** — what Google queries do they already get impressions on? Convert to natural-language form for chatbots.
3. **Reddit/YouTube comments** — pull questions from `comment-mine` skill if available.
4. **The site's content map** — every major article suggests 2-3 corresponding queries.

Propose, confirm, add. Don't bulk-add without review.

## Gotchas

- **Responses vary run to run.** ChatGPT may cite you 1 in 5 times for the same query — that's normal. Citation rates are statistical, not deterministic. Run daily, look at rates over time.
- **Mobile app traffic strips referrers.** GA4 won't show all AI traffic — many ChatGPT users on mobile land as Direct.
- **First run is slowest.** ChatGPT/Perplexity scrapes wait 15-18s for streaming responses.
- **Concurrency is capped (default 3).** ChatGPT/Perplexity are Firecrawl scrapes; firing every job at once saturates the Firecrawl **hobby** plan's concurrency limit and trips server-side `SCRAPE_TIMEOUT` (408) — a single scrape succeeds in ~15s, so a wall of timeouts means too much parallelism, not a broken URL. Tune with `AEO_CONCURRENCY` (raise it on a paid Firecrawl plan: `aeo config set firecrawl_plan standard`), or `--serial`.
- **Firecrawl → DataForSEO fallback.** If a ChatGPT/Perplexity scrape still errors or returns empty, the run falls back to the DataForSEO Google-AI-Overview citation set for that query (tagged `operation: ai_overview_fallback`, `metadata.fallback_provider`) so a run never zeroes out. It's a *different surface* (Google's AI answer, not the native chatbot) — treat fallback rows as a proxy. Disable with `AEO_DISABLE_DATAFORSEO_FALLBACK=1`.
- **`.aeo/` should be gitignored.** It's local data, not source. The skill auto-creates `.aeo/raw/` for debugging — same applies.

## Architecture notes (for debugging)

- `aeo` — shell wrapper that runs `tsx src/cli.ts` from the skill's own `node_modules`
- `src/cli.ts` — commander entrypoint
- `src/scrapers.ts` — one function per platform (Firecrawl, DataForSEO, Anthropic)
- `src/extract.ts` — Gemini 2.5 Flash structured extraction (regex fallback if no `GEMINI_API_KEY`)
- `src/db.ts` — SQLite (better-sqlite3) schema + query helpers
- `src/costs.ts` — provider rate tables (update when prices change)

Every API call records to `cost_events`. Every scrape writes raw output to `.aeo/raw/` for debugging when extraction is weird.
