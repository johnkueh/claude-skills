---
name: dev-goto
description: Resolve a short project name to its repo under ~/Projects, cd in, and load that repo's context before doing the actual task. Use whenever John starts a request with "go into X", "in X, ...", "switch to X", "open X", "over in X", or just names a project as the place to work — e.g. drafty, drafty.im, marky, johnkueh.com, glp3, journeys, recipes, clove, subs.rip, claude-skills, bq-analytics. Sessions start at ~/Projects, so the target repo's CLAUDE.md is NOT auto-loaded — this skill is how it gets loaded.
---

# Goto Project

Entry routine for "go into <project>, then <task>" requests. Do the four steps below quickly and quietly, then get on with the task — the routine itself needs at most one line of narration.

## Entry routine

1. **Resolve** the name via the table below. Unknown name → `ls -d ~/Projects/*/` and fuzzy-match; ask only if genuinely ambiguous after that.
2. **cd** into the repo as a standalone `cd <abs-path>` command (a `cd` inside a compound command triggers a permission prompt). Use absolute paths in later commands anyway.
3. **Read `<repo>/CLAUDE.md`** if it exists — before any real work. It usually answers "why doesn't X work locally" (dev harness, env tokens, test setup).
4. **Check state**: `git branch --show-current` + `git status --short`. John often parks the main checkout on a feature branch with WIP — never assume main/master, and never ship over uncommitted work without flagging it.

Then load any project-specific skill the task calls for (see table notes) and do the task.

## Project table

| Say | Path | Notes |
|---|---|---|
| drafty, drafty.im, marky | `~/Projects/drafty.im` | Main app (Next.js + InstantDB). Push to main auto-deploys — never `vercel deploy`. Repo CLAUDE.md documents the e2e/dev harness. |
| drafty plugin | `~/Projects/drafty` | Claude plugin marketplace repo (plugins/, scripts/) — NOT the app. |
| drafty outreach | `~/Projects/drafty-outreach` | Pipeline data dir; the workflow lives in the `drafty-outreach` skill. |
| johnkueh.com | `~/Projects/johnkueh.com` | Personal site. Articles: understated voice, draft locally, never straight to prod. |
| glp3, glp3.wiki | `~/Projects/glp3.wiki` | Content site. Build-gate before push; `glp3-daily` skill owns the daily loop. |
| journeys, journeys.im | `~/Projects/journeys.im` | Travel app monorepo; agent CLI is `pnpm -F trips-parser journeys <cmd>` in packages/trips-parser/. |
| recipes, myapp | `~/Projects/myapp` | Expo app, default branch is **master**. OTA releases need per-release authorization; EAS builds use the `production` profile only. |
| clove | `~/Projects/clove` | Work repo (clovekitchen/clove). For PRs/review load `johns-github-style`; for backend work load `clove-be-reviewers`. |
| subs.rip | `~/Projects/subs.rip` | CLI releases via `subsrip-release` skill; credit grants via `subsrip-grant`. |
| claude-skills | `~/Projects/claude-skills` | Published skills repo — follow docs/skill-conventions.md there. Personal skills live in ~/.claude/skills/ instead. |
| bq-analytics | `~/Projects/bq-analytics` | Analytics SDK; the bq-analytics:* skills cover install/query/flags/release. |
| chat-archives | `~/Projects/chat-archives` | Data only (WhatsApp/Slack archives), not a repo. |

## Stale / trap directories — do not enter unless John names them explicitly

`marky.im`, `drafty.im-og`, `drafty.im-improvements`, `drafty-art-proto`, `sveds.com`, `myapp-server-v2`, `myapp-wide-events`, `ledgersignal3/4/5`, `archived/`, `Projects/`. These are old copies or experiments that shadow the real repos above. "marky" always means `drafty.im` (the Marky rename was reverted 2026-06-07).

## Maintenance

When a new project appears under ~/Projects or a row here turns out wrong, update this table in `~/Projects/claude-skills/skills/dev-goto/SKILL.md` (the marketplace source), then republish the plugin (version bump + `claude plugin update dev-goto@johnkueh-skills` + reload).
