# claude-skills — agent guardrails

**This repository is PUBLIC.** Everything you commit is world-readable — and so is the
**entire git history**. Deleting a leak in a later commit does **not** remove it: it
stays recoverable in history forever (and a committed secret is compromised the moment
it's pushed — it must be rotated, not just scrubbed). So the rule is simple:

> Never write anything into this repo that you would not put on a public website.

These skills are published for anyone to install. Keep them generic, useful, and free of
anything personal, private, or secret.

## Never commit

- **Credentials of any kind** — API keys, tokens, bearer tokens, passwords, OAuth/refresh
  tokens, proxy credentials, admin tokens, private keys, connection strings, signed URLs.
  A skill reads its secrets at runtime from **environment variables**, `~/.config/<skill>/`,
  or `~/.cache/<skill>/` — never from a file in this repo. In docs, name the **variable
  only** (e.g. "set `DATAFORSEO_API_KEY`"), never a value, never an example that looks real.
- **Private or stealth project names.** Do not name unreleased/stealth projects. If an
  example needs a project, use a **placeholder** (`myapp`, `myapp.com`, `example.com`,
  `your-app`, `~/Projects/myapp`) — never a real private repo or product.
- **Private notes, strategy, or "intelligence."** No growth numbers, revenue/MRR, user or
  signup counts, roadmaps, internal plans, business context, competitor notes, or
  decision/provenance logs. Skills describe *how a tool works*, not what John is building.
- **Personal paths & machine details.** No `/Users/<name>/...` absolute paths, no machine
  names, no iCloud/Dropbox personal paths in examples. Use `~/Projects/myapp` and generic
  home-relative paths.
- **Scratch / provenance / session notes.** No internal initiative docs, "local-copy"
  provenance files, or working notes. Those belong in a private repo, not here.

## OK to name

- **`drafty` / `drafty.im`** — a public product, used here as a genuine integration target
  (e.g. `drafty-proof-canvas` pushes to it). Naming it is fine.
- **`bq-analytics`** — a public tool some skills integrate with.
- Other **already-public** projects, but only when a real integration genuinely needs the
  name. When in doubt, prefer a placeholder — a skill that reads as generic is the goal.

## Before you commit or open a PR

1. `git grep -niE "(sk-|xox[pb]-|ghp_|AKIA|-----BEGIN|bearer |api[_-]?key|password|secret)"`
   — confirm no real credential, only env-var names.
2. No real private/stealth project names; examples use placeholders.
3. No personal absolute paths, no private notes/metrics/strategy.
4. Remember history is public too — if you're *removing* a leak, flag it to John; a file
   edit alone leaves it in history (and a leaked secret needs rotating).

If you spot a leak that's already committed, **stop and tell John** — don't quietly patch it.
