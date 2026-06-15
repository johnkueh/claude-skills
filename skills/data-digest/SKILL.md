---
name: data-digest
description: Per-project daily digest of new signups, top user activities, API/LLM costs, and recently-changed initiative docs — pulled from bq-analytics where available, plus git activity and the latest x-monitor run. Use when the user wants a "morning digest" across their projects, says "give me yesterday's roundup", or asks for a recurring summary across your projects. Designed to be invoked daily via `/loop`.
---

# data-digest
Pulls a per-project digest covering, since the last check:

- **Users** — `total` distinct user_ids in `events.identifies` ever, plus `new` first-seen-in-window count (signups since last check)
- **Top user activities** — top events by count, with distinct-user fanout
- **API / LLM / scraping costs** — `cost.recorded` rolled up by provider/operation
- **Top error paths** — `logs.raw` 5xx count by path
- **Recent feedback** — `events.feedback` items

It also appends a per-handle **x-monitor section**. The script reads each subscribed handle's local archive (`tweets/<handle>.jsonl`) and filters to tweets within the digest window — it does **not** rely on the latest run file (that file would miss handles subscribed after the run was taken). No re-fetch — costs $0.

The Python script returns structured JSON; the agent (Claude) reformats it into a tight markdown digest.

## Setup

```bash
# from anywhere
uv run --quiet <skill-dir>/daily_digest.py setup
```

State lives at `~/.cache/daily-digest/` (`projects.json`, `state.json`, `runs/<iso>.json`). Override with `DAILY_DIGEST_HOME` if you want it on iCloud Drive for cross-machine sync.

## Add a project

```bash
uv run --quiet daily_digest.py add my-project \
    --bq-project my-project \
    --group-type household \
    --description "Cooklang recipe iOS app + Next.js + Hono API"
```

Flags:

| Flag | Required | Notes |
|---|---|---|
| `--bq-project` | required | GCP project that holds `events.raw`, `events.identifies`, `events.feedback`, `logs.raw` (the bq-analytics layout). |
| `--group-type` | optional | bq-analytics `group_type` to attach to each signup (e.g. `household`, `workspace`, `team`). When set, signups include the user's `group_id` and group name (`traits.display_name` or `traits.name`). |
| `--description` | optional | One-line note printed in the digest header. |
| `--force` | flag | Overwrite an existing project entry. |

`list`, `rm`, are also there:

```bash
uv run --quiet daily_digest.py list
uv run --quiet daily_digest.py rm my-saas
```

## Daily digest workflow (what `/loop` fires)

```
/loop 1d use the data-digest skill to generate today's roundup
```

When invoked:

1. **Run the check.** Lookback window = `now − last_checked_at` per project (default 1 day on first run). Pass `--since 24h` to override, or `--no-state` to leave `last_checked_at` untouched (useful for ad-hoc runs).

   ```bash
   uv run --quiet daily_digest.py check --json
   ```

2. **Reformat the JSON into a tight bulleted digest.** Use proper markdown — `#` title, `##` per project / x-monitor, real bullet lists. Structure (NOT style) stays minimal: just signups, events, costs, optional 5xx/feedback, then x-monitor. No priorities, no initiatives, no takeaway.

   ````md
   # Daily digest — DD/MM/YYYY

   ## <project>

   - **Users:** new N, total M _(group: Household Name, …)_   ← group only if new>0 and --group-type set
   - **Events:** <rough total> — `event_a` N×, `event_b` N×, `event_c` N×
   - **Costs:** $X.XX total — `provider/op` $X.XX, `provider/op` $X.XX, …
   - **5xx:** `/path` N×, …                           ← omit line entirely when zero
   - **Feedback:** N items — _[kind] subject_         ← omit line entirely when zero

   ## <next project>
   …

   ## X-monitor

   - No new posts from @a or @b
     OR
   - **@a** — N× new: one-line summary
   ````

   Rules:
   - **Date format `DD/MM/YYYY`** in the title.
   - **`##` for each project** and for x-monitor — gives clear visual separation when scanning multiple projects.
   - **Bold the field name** (`**Signups:**`, `**Events:**`, …); inline-code the event names / paths / providers.
   - **Round large counts** — 1865 → `1.9k`, 12340 → `12k+`. Exact under 1000.
   - **Top 3 events / top 4–5 cost ops** inline, comma-separated. No nested bullets.
   - **Omit 5xx and feedback bullets when zero** — always show signups, events, costs.
   - **No priorities, no initiatives, no takeaway, no emojis.** This is a glance, not a briefing.

3. **Append the x-monitor section** from `digest.x_monitor` — the script already filtered each subscribed handle's archive to the digest window; just summarize per-handle new tweets following the x-monitor skill's bullet format.

4. **One-line takeaway across projects** — what stands out today. Skip if nothing did.

5. **State advances automatically.** The next `check` only covers what's happened since this run. Pass `--no-state` to skip the advance for ad-hoc questions ("what's happened in the last 7 days?").

## Smoke test (one-shot, no state)

```bash
uv run --quiet daily_digest.py check --since 24h --no-state --json | jq
```

This runs all configured projects with a fixed 24h window and **doesn't** advance `last_checked_at`. Use for development.

## What the JSON looks like

```jsonc
{
  "generated_at": "2026-05-07T06:10:27Z",
  "projects": [
    {
      "name": "my-project",
      "since": "2026-05-06T06:10:29Z",
      "description": "...",
      "signups":   { "new_users": 1, "sample": [...] },
      "activities":{ "top": [{event_name, n, users}, ...] },
      "costs":     { "total_usd": 0.94, "total_calls": 179, "breakdown": [...] },
      "errors":    { "top": [{path, errs, total}, ...] },
      "feedback":  { "items": [{ts, kind, subject, message, user_id}, ...] },
      "initiatives": {
         "dir": "/abs/path/to/docs/initiatives",
         "total_files": 45,
         "readme": "...full markdown content of README.md...",
         "files": [
           { "file": "...", "title": "...", "summary": "...",
             "mtime": "...", "size_bytes": N,
             "modified_recently": true }, ...
         ]
      }
    }
  ],
  "x_monitor": { ...latest x-monitor run JSON... }
}
```

Per-project fields are omitted when their source isn't configured (e.g. no `bq_project` → no `signups`/`activities`/`costs`/`errors`/`feedback`).

## Schema assumptions

The bq fetchers assume the `bq-analytics` layout:

- `events.raw` — `event_name`, `user_id`, `ts`, JSON `properties`. Cost events use `event_name = 'cost.recorded'` with `properties.{provider, operation, model, cost_micros}`.
- `events.identifies` — `user_id`, `ts`, JSON `traits`. First-seen-per-`user_id` = signup.
- `events.feedback` — `kind`, `subject`, `message`, `user_id`, `ts`.
- `logs.raw` — `ts`, `level`, `path`, `status`, `message` (Vercel Log Drain landing zone).

If your project doesn't follow this exact shape, edit `bq_signups`/`bq_costs`/etc. in `daily_digest.py` — they're independent ~15-line functions.

## Costs

- bq queries scan a few MB per project → free under the 1 TB/mo BQ on-demand quota.
- x-monitor section reads the **already-archived** latest run, so $0 in API calls. (The actual fresh fetch happens in the x-monitor skill's own `/loop`.)
- Total cost of a daily digest across 5 projects with bq-analytics: $0.

## Troubleshooting

- **`Access Denied: User does not have bigquery.jobs.create permission`** — switch gcloud accounts: `gcloud config set account <email>`. The skill calls `bq` via subprocess, so it inherits whatever account is active.
- **`signups.new_users = 0` but you know there were sign-ups** — verify `events.identifies` is being written; some projects only call `track()` and never `identify()`. In that case, treat first-seen-in-`events.raw` as the signup proxy and add a fetcher.
- **No files flagged `modified_recently`** — mtime floor is 7 days. If recent edits don't appear, the files might have been touched only in git history, not on the local filesystem (e.g. checkout from a different branch). Run `touch` or widen `INITIATIVES_LOOKBACK`.
- **x-monitor section says "no runs yet"** — set `X_MONITOR_HOME` to point at the synced folder, or run x-monitor's `setup` + `check` once.

## Recurring with /loop

```
/loop 1d use the data-digest skill to produce a digest across configured projects
```

For a self-paced cadence (let the model decide when):

```
/loop use the data-digest skill whenever appropriate to summarize project activity
```
