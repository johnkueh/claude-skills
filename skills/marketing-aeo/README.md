# aeo-monitor

Track how often AI chatbots cite your site for the queries that matter to your audience. Per-project, local-first, with actual cost tracking.

## What it does

For every `(query, platform)` you register, weekly or daily:

1. Scrapes the AI chatbot response (ChatGPT, Perplexity, Google AI Overview, Claude)
2. Extracts citations via Gemini 2.5 Flash into structured form
3. Detects whether your domains were cited
4. Stores everything in SQLite so you can trend over time

## Requirements

- Node 22+
- pnpm or npm (one-time dep install)
- API keys as environment variables:
  - `FIRECRAWL_API_KEY` (firecrawl.dev) — for ChatGPT + Perplexity scraping
  - `DATAFORSEO_API_KEY` (base64 of `login:password`) — for Google AI Overview
  - `GEMINI_API_KEY` (aistudio.google.com) — for structured extraction
  - `ANTHROPIC_API_KEY` (optional) — for Claude with web search

## Install

This skill ships as part of the `johnkueh-skills` plugin. After installing the plugin, set up a shell alias:

```bash
alias aeo='<plugin-path>/skills/marketing-aeo/aeo'
```

The `aeo` wrapper auto-installs Node deps on first run.

## Quick start

```bash
cd ~/Projects/yourproject

# 1. Initialize per-project data store
aeo init

# 2. Verify keys + balance
aeo doctor

# 3. Add domains to detect
aeo domain add yourdomain.com --label own
aeo domain add competitor.com --label competitor

# 4. Add queries to track
aeo query add "what is X and how does it work"
aeo query add "X vs competitor Y"

# 5. First run (estimate cost first)
aeo run --dry-run
aeo run

# 6. Review results
aeo report --days 7
aeo competitors --days 30
aeo cost --by provider
```

## Recurring monitoring

Use Claude Code's `/loop`:

```
/loop 24h aeo run
```

Or schedule a remote agent via the `schedule` skill.

## Data layout

Everything is per-project, in `<project>/.aeo/`:

```
.aeo/
├── runs.sqlite          # all runs, citations, cost events
└── raw/                 # raw scraped output per run (for debugging)
```

Gitignore the `.aeo/` directory.

## Cost

Per query × platform (rough):
- ChatGPT (Firecrawl + Gemini): ~$0.012
- Perplexity (Firecrawl + Gemini): ~$0.012
- Google AI Overview (DataForSEO + Gemini): ~$0.003
- Claude Haiku (Anthropic + Gemini): ~$0.010

A full daily run with 10 queries × 4 platforms ≈ $0.40/day, ~$12/month per project.

Set a budget warning: `aeo budget set 1500` (= $15/month).

## Commands

| Command | Purpose |
|---|---|
| `aeo init` | Create `.aeo/` in current directory |
| `aeo doctor` | Validate env vars, show balance, config, DB stats |
| `aeo config show/set` | Per-project config (firecrawl_plan, project_name) |
| `aeo query add/list/remove` | Manage tracked queries |
| `aeo domain add/list/remove` | Manage domains to detect |
| `aeo budget set/show/clear` | Monthly cost budget (warning only) |
| `aeo run [--platform X] [--query "..."] [--dry-run]` | Execute checks |
| `aeo report [--days 7]` | Citation rate per (query, platform) |
| `aeo competitors [--days 30]` | Top cited domains across your queries |
| `aeo history --query "..."` | Full history for one query |
| `aeo cost [--by provider\|platform\|query]` | Spend breakdown |
| `aeo export --format json\|csv` | Dump all data |

## How it works under the hood

| Platform | Method | Why |
|---|---|---|
| ChatGPT | Firecrawl scrape `chatgpt.com/?q=...` + 18s wait | No anon API; web UI gives real citations |
| Perplexity | Firecrawl scrape `perplexity.ai/search?q=...` + 12s wait | API requires paid key; scraping is fine |
| Google AI Overview | DataForSEO SERP API + `load_async_ai_overview: true` | reCAPTCHA blocks direct scraping |
| Claude | Anthropic API + `web_search_20250305` tool (Haiku 4.5) | Auth-walled web UI; API uses same Brave backend (~87% URL overlap with claude.ai) |

After scraping, every response is passed to Gemini 2.5 Flash with a strict JSON schema for extraction. Cost is tracked per call and stored in `cost_events`.

## Known limitations

- LLM responses are stochastic — same query gives different citations across runs. Run daily to build statistical rates rather than relying on single shots.
- Mobile app traffic from chatbots strips referrers — GA4 will miss most of it; this monitor measures what chatbots return, which is what gets sent to users regardless of platform.
- DataForSEO is paid per query; Firecrawl is per credit; Anthropic is per token. Set a budget warning if you're cost-sensitive.
