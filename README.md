<p align="center">
  <img src="assets/hero.png" alt="claude-skills — skills that make Claude Code actually useful" width="1100" />
</p>

**claude-skills** is a collection of [Claude Code](https://docs.claude.com/en/docs/claude-code) skills I've built and use every day — to mine Reddit, do keyword and SERP research, query analytics, ship Expo builds, generate images and video, and keep my Mac clean. Install the whole set in one command, or add a single skill on its own.

```
/plugin marketplace add johnkueh/claude-skills
/plugin install claude-skills@johnkueh-skills
```

That's the full collection. Want just one? Every skill is its own plugin:

```
/plugin install media-icon-search@johnkueh-skills
/plugin install marketing-reddit@johnkueh-skills
```

## Why skills

A skill teaches Claude Code a job you'd otherwise re-explain every session — which API to call, which flags matter, what the output should look like. Claude loads the right one on its own when your request matches, so "find me an icon for a vegetarian recipe" or "what are people asking about retatrutide on Reddit" just works, with the real tool behind it instead of a guess.

These are the ones that earned a permanent spot in my setup. They lean on real keys and CLIs (DataForSEO, the YouTube Data API, `gcloud`, OpenAI, Gemini), so most need a token or two — each skill's `SKILL.md` says exactly what.

## The skills

### Research & SEO

| Skill | What it does |
|---|---|
| [`marketing-reddit`](skills/marketing-reddit) | Pull posts, threads, and question clusters from Reddit through a headless browser that gets past the bot challenge. |
| [`marketing-keyword-data`](skills/marketing-keyword-data) | DataForSEO keyword research — search volume, intent, difficulty, CPC, and suggestions for content planning. |
| [`marketing-serp`](skills/marketing-serp) | Geo-targeted SERP analysis — who ranks where, content gaps, and features like featured snippets and PAA. |
| [`marketing-aeo`](skills/marketing-aeo) | Track which AI chatbots (ChatGPT, Perplexity, Google AI Overview, Claude) cite a project, and how that moves. |
| [`marketing-ai-crawler`](skills/marketing-ai-crawler) | See which AI bots (GPTBot, ClaudeBot, PerplexityBot, ...) crawl your Vercel sites and which paths they hit. |
| [`marketing-youtube-transcribe`](skills/marketing-youtube-transcribe) | Get a clean transcript from any YouTube video for research, fact-checking, or content. |
| [`marketing-youtube-mine`](skills/marketing-youtube-mine) | Mine YouTube comments for unanswered questions, clustered — drop-in compatible with `marketing-reddit`'s output for SEO loops. |
| [`marketing-x`](skills/marketing-x) | Watch X profiles for new posts and get a daily digest of what they said. |

### Comms

| Skill | What it does |
|---|---|
| [`comms-slack`](skills/comms-slack) | Search Slack messages, pull a thread, or look someone up — across your channels and DMs. |
| [`comms-whatsapp`](skills/comms-whatsapp) | Read and send WhatsApp messages from the command line — search chats, list groups, grab a thread. |
| [`comms-notion`](skills/comms-notion) | Read a Notion page from its URL and return the body as markdown. |

### Build & ship

| Skill | What it does |
|---|---|
| [`dev-expo`](skills/dev-expo) | Build an Expo app locally and send the IPA or APK straight to a phone over a Cloudflare tunnel. |
| [`dev-up`](skills/dev-up) | One-verb dev-server + worktree QA lifecycle (dev-up/dev-down, metro-takeover, expo-qa fingerprint gate + EAS Update publish, worktrees-gc), backed by an ngrok-replacing Cloudflare tunnel. |
| [`dev-vercel-logs`](skills/dev-vercel-logs) | Query Vercel runtime and build logs to debug production, with full message bodies the dashboard truncates. |
| [`dev-instantdb`](skills/dev-instantdb) | Build a working React, vanilla JS, or Expo app with InstantDB as a realtime, local-first backend. |
| [`dev-flow`](skills/dev-flow) | A master dev workflow that routes a request from "go work on X" to landed-and-verified, picking web vs OTA vs native-rebuild on landing. |
| [`dev-ship`](skills/dev-ship) | A standing ship authorization — execute an agreed plan in a worktree, validate locally, and open/merge a PR when there's no regression risk. |
| [`drafty-proof-canvas`](skills/drafty-proof-canvas) | Publish proof-of-work screenshots to a drafty.im canvas so you can review and annotate visual results from any device. |

### Data

| Skill | What it does |
|---|---|
| [`data-digest`](skills/data-digest) | A per-project morning roundup — new signups, top activity, API and LLM cost, and what changed — pulled from your own data. |

### Copy & design

| Skill | What it does |
|---|---|
| [`media-icon-search`](skills/media-icon-search) | Find the right icon across Lucide, Phosphor, Tabler, Heroicons, and HugeIcons by describing it, and get the exact React import back. |
| [`media-image-gen`](skills/media-image-gen) | Generate logos, illustrations, photoreal shots, UI mockups, and ads with GPT Image 2 — with cost logged per call. |
| [`media-video-gen`](skills/media-video-gen) | Generate cinematic videos with Veo 3.1 (text/image→video) — pairs with a still, quotes exact per-second cost up front, true-loop + web MP4/WebM/poster output. |
| [`brand-design`](skills/brand-design) | A house UI/UX playbook for reviewing app and web screens — typography, spacing, dark mode, motion, the "looks AI-generated" smell test. |
| [`brand-copy`](skills/brand-copy) | A house copy guide for UI strings, errors, empty states, onboarding, and marketing — voice, tone, and microcopy. |

### Mac hygiene

| Skill | What it does |
|---|---|
| [`system-disk-cleanup`](skills/system-disk-cleanup) | Find what's eating your disk and clear it safely. |
| [`system-memory-cleanup`](skills/system-memory-cleanup) | Spot CPU and memory hogs, and clean up orphaned processes. |

## Installing one skill vs. all of them

The `claude-skills` plugin ships every skill above. Each skill is also published as its own plugin, so you can take only what you need:

```
/plugin marketplace add johnkueh/claude-skills

/plugin install claude-skills@johnkueh-skills      # everything
/plugin install exa@johnkueh-skills                # just one
```

Use the skill name as the plugin name — `<name>@johnkueh-skills`. Both can coexist; they're alternatives, not a dependency.

Once a skill is installed, Claude Code loads it automatically when your request matches its triggers. You don't call it by name — just ask for the thing.

## How this repo is built

Each skill is a folder under `skills/<name>/` with a `SKILL.md` and whatever supporting files it needs. The marketplace manifest is generated, not hand-written:

```sh
bun scripts/build-marketplace.ts
```

This walks the committed skill folders, regenerates `.claude-plugin/marketplace.json` (the bundle plus one plugin per skill), and rebuilds the `plugins/` symlink tree each single-skill plugin points at. Add a skill folder, run it, and every install command stays in sync. Verify with:

```sh
claude plugin validate --strict .
```

Writing or changing a skill? Follow [docs/skill-conventions.md](docs/skill-conventions.md) — frontmatter triggers, line budgets, `setup`/`doctor`, secrets handling.

## License

MIT.
