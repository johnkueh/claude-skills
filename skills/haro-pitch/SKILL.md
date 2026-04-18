---
name: haro-pitch
description: "Draft HARO/Qwoted journalist-query pitches grounded in an article corpus, and manage the pitch queue. The skill itself (you, Claude Code) reads the query + corpus and writes the pitch — the Python CLI handles mechanical parts (topic/outlet filtering, queue CRUD, reporting). Invoke when the user pastes a HARO or Qwoted journalist query, or says 'haro', 'qwoted', 'pitch this query', 'draft a response to this journalist'."
---

# HARO / Qwoted pitch drafter

Turn journalist queries into grounded, editable pitches that the user sends manually. Optimized for earning DR 60–85 editorial backlinks in YMYL niches.

**Ethical boundary:** journalists blacklist sources that send raw AI output. This skill drafts + queues; the human reviews, edits, and sends. The skill itself never hits send.

## Setup

Plugin cache path (preferred):
```bash
/Users/johnkueh/.claude/plugins/cache/johnkueh-skills/claude-skills/1.0.0/skills/haro-pitch
```

Local-clone fallback:
```bash
/Users/johnkueh/Projects/claude-skills/skills/haro-pitch
```

No one-time install required (Python-only, `uv` handles deps).

## How to use — typical workflow

### 1. User pastes a journalist query

User drops a HARO email, a Qwoted query, or a batch of queries into the chat. You can accept these as free text — don't require JSON.

### 2. Parse + filter

Ask the user where the project config lives if not obvious. Example: `/Users/johnkueh/Projects/glp3.wiki/.claude/skills/link-building/project-config.json`.

Convert pasted queries into the canonical JSON shape (see `fixtures/sample-queries.json`), save to a temp file, and run:

```bash
uv run cli.py filter score --queries /tmp/queries.json --config <project-config.json> --format table
```

This prints a relevance-scored table. Any query below `min_relevance=0.5` should be skipped unless the user overrides.

### 3. Draft (you do this, not the CLI)

For each query that passes the filter:

1. Read the project's corpus (paths from `project-config.json`'s `corpus_dir`)
2. Identify the 2–3 most relevant corpus articles (keyword-match against the query)
3. Read those articles — extract specific numbers, primary-source URLs, trial names
4. Write a draft pitch following the quality rules below

**Quality rules (BLOCKING):**

- Under **150 words** (HARO standard; Qwoted is similar)
- Matches the journalist's **specific angle** — don't pivot to something else
- At least **2 specific numbers** (e.g. "28.7%", "Phase 3 TRIUMPH-4", "48 weeks")
- At least **1 URL** to a primary source (NEJM, Lancet, investor press release, ClinicalTrials.gov — never your own site as the only source)
- Include the configured `author_credentials` footer exactly
- **Cite your own article** as the secondary reference (this is the link you want back)
- **Do not** use any blacklist phrase: "I'd be happy to", "I'm happy to", "In today's fast-paced world", "In the modern era", "It's important to note", "At the end of the day", "leverage", "delve", "unleash", "harness", "elevate"
- **Do not** fabricate. If you're not sure a number is in the corpus, don't cite it.
- Match the journalist's tone (news-explainer: factual + short; feature: slightly more narrative)

### 4. Queue the draft

```bash
uv run cli.py queue new \
    --queue-dir /path/to/project/seo/haro/queue \
    --source haro \
    --query-id FIXTURE-001 \
    --outlet "Everyday Health" \
    --outlet-tier HIGH \
    --journalist "Sarah Chen" \
    --deadline "2026-04-21T17:00:00-04:00" \
    --relevance 0.9 \
    --matched-keywords "retatrutide,GLP-1,tirzepatide" \
    --target-article "what-is-retatrutide" \
    --subject "Seeking experts on retatrutide" \
    --query-text "<original query>" \
    --draft "<your draft pitch>" \
    --why "High-tier health outlet, triple-agonist angle matches our flagship article"
```

### 5. Report back to the user

Show the user:
- Slug of the new draft in the queue
- First few sentences of the draft
- Path to the full file (`seo/haro/queue/{slug}.md`) for review
- Any quality checks that failed or needed manual judgment

### 6. After the user sends manually

The user reads the draft, edits as needed, copies, sends via HARO/Qwoted's web interface, then tells you (or types themselves):

```bash
uv run cli.py queue mark-sent --queue-dir ... --slug <slug>
```

If a placement lands:
```bash
uv run cli.py queue mark-landed --queue-dir ... --slug <slug> --url <published-url>
```

If skipped:
```bash
uv run cli.py queue mark-skipped --queue-dir ... --slug <slug> --reason "deadline passed"
```

### 7. Monthly report

```bash
uv run cli.py report --queue-dir ... --month 2026-04
```

## Input contract — project-config.json

Each host project must provide a config pointing at its corpus + brand voice:

```json
{
  "topic_keywords": ["retatrutide", "GLP-1", "tirzepatide", "semaglutide", ...],
  "corpus_dir": "/abs/path/to/articles",
  "brand_voice_file": "/abs/path/to/brand-voice.md",
  "author_credentials": "— Your Name, Title, sitename.com — one-line publication description.",
  "queue_dir": "/abs/path/to/project/seo/haro/queue",
  "preferred_outlets_tiers": {
    "HIGH": ["Wall Street Journal", "New York Times", "Everyday Health", "Healthline"],
    "MED": ["Well+Good", "MindBodyGreen"]
  }
}
```

## CLI reference

### `filter score`

Scores queries by topic relevance + classifies outlet tier.

```bash
uv run cli.py filter score \
    --queries /path/to/queries.json \
    --config /path/to/project-config.json \
    --min-relevance 0.5 \
    --format table
```

Output (table mode): one row per query, sorted by relevance desc.

### `queue new`

Create a new draft in the queue. See flags above.

### `queue list`

```bash
uv run cli.py queue list --queue-dir ... --status queued
```

Lists drafts; optional `--status` filter.

### `queue mark-sent | mark-landed | mark-skipped | mark-revision`

Transition a draft through the status workflow. See specific flag requirements.

### `report`

```bash
uv run cli.py report --queue-dir ... --month 2026-04
uv run cli.py report --queue-dir ... --all --format json
```

## Query JSON shape

When converting pasted text into structured queries, use this shape:

```json
{
  "queries": [
    {
      "id": "2026-04-18-001",
      "source": "haro" | "qwoted" | "other",
      "outlet": "Everyday Health",
      "journalist": "Sarah Chen",
      "subject": "Short description",
      "query": "Full query text from the journalist",
      "deadline": "2026-04-21T17:00:00-04:00",
      "media_outlet_url": "https://www.everydayhealth.com"
    }
  ]
}
```

See `fixtures/sample-queries.json` for a realistic 10-query mix.

## Draft format on disk

Each queued draft is a markdown file under `queue_dir/{slug}.md` with YAML frontmatter:

```markdown
---
source: haro
query_id: FIXTURE-001
outlet: Everyday Health
outlet_tier: HIGH
journalist: Sarah Chen
deadline: 2026-04-21T17:00:00-04:00
relevance: 0.9
matched_keywords: retatrutide,GLP-1,tirzepatide
target_article: what-is-retatrutide
status: queued
drafted_at: 2026-04-18T12:30:00+00:00
---

## Query

<original query text>

## Draft response

<pitch body>

## Why this pitch

<one-line justification>
```

Status transitions: `queued → sent → landed` (happy path) or `queued → skipped` or `queued → needs_revision → queued`.

## What this skill does NOT do

- Poll HARO email — that requires IMAP (deferred; user pastes emails into chat for now)
- Poll Qwoted RSS — deferred; same reason
- Send pitches — never. Human reviews + sends manually.
- Call an external LLM — you (Claude Code) are the drafter, not an API
- Track placements automatically — user marks with `queue mark-landed`

## Voice / style guardrails per project

Each project's `brand_voice_file` specifies tone, forbidden phrases, any signature structure. Read it before drafting.

## Troubleshooting

- **"Queries file not found"** — convert the pasted email into JSON first; save to `/tmp/queries.json`
- **Relevance score 0 on a query that looks relevant** — add the missing keyword to `topic_keywords` in project-config.json
- **Draft rejected by user for AI-tells** — tighten the draft; common fix is replacing hedge phrases with direct claims
- **"Status invalid"** — use one of: queued, sent, landed, skipped, needs_revision
