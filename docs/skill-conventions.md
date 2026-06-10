# Skill conventions

Prescriptive structure for every skill in this repo. Read this before writing or
touching a skill. Each skill ships both in the bundle and as its own plugin, so a
skill directory must work when it's the only thing installed.

## Layout

```
skills/<name>/
  SKILL.md          # required — frontmatter + lean instructions
  cli.py | cli.ts   # optional — the tool the skill drives
  reference/*.md    # optional — detail loaded on demand
  .gitignore        # required if the skill produces output or holds secrets
```

After any change: `bun scripts/build-marketplace.ts` then
`claude plugin validate --strict .` — both must pass before committing.

## Frontmatter description

The description is the trigger. It must contain **concrete phrases a user would
actually type**, quoted, not just a capability summary:

```yaml
description: >-
  DataForSEO keyword research for SEO and content planning. ... Triggers on
  "keyword research", "search volume", "keyword difficulty", "CPC for", ...
```

- Lead with what the skill does and when to use it (one or two sentences).
- End with `Triggers on "...", "...", ...` — 5–10 phrases, including at least one
  short colloquial form ("is GPTBot hitting", not only "AI crawler analysis").
- Name the things the skill is scoped to (APIs, sites, tools) so Claude doesn't
  fire it for lookalike requests.

## SKILL.md line budget

Target ~250 lines max. SKILL.md is loaded whole into context every time the
skill fires — it pays rent on every invocation.

- Keep in SKILL.md: setup, the commands with one example each, output shape,
  cost/limits, gotchas that change behavior.
- Push to `reference/*.md`: API field glossaries, long workflows, location/code
  tables, troubleshooting trees. Link them from SKILL.md ("read
  `reference/filters.md` when the user asks for ...") so they're loaded on demand.

## CLI-backed skills: `setup` and `doctor`

Any skill that wraps a CLI or API gets two commands in its tool:

- **`setup`** — interactive, idempotent. Writes machine-local config
  (`~/.config/<skill>/config.json` or similar) and tells the user exactly which
  env vars to export and where to get the keys. Never writes secrets into the
  repo. Re-running it must be safe.
- **`doctor`** — read-only diagnosis, exits non-zero on failure. Checks, in order:
  1. Dependencies present (binary on PATH, minimum version if behavior depends on it).
  2. Config/env vars set — name the missing variable and the one-line fix.
  3. Key actually works — a **live, free/cheap API ping** (auth check, `whoami`,
     balance endpoint), not just "variable is non-empty".

Env-var sourcing for a public repo: secrets live in the user's environment
(`~/.claude/settings.json` env block, shell profile, or an untracked `.env` in
the skill dir). The repo ships only the variable *name* and the `echo -n
'login:pass' | base64`-style recipe for producing the value.

## Human-gated setup: "you do these N things"

If setup needs steps only a human can do (create an API account, approve an
OAuth grant, add a DNS record), SKILL.md opens with an explicit split:

```markdown
## Setup — you do 2 things, I do the rest
1. You: create a DataForSEO account and grab login + password.
2. You: export DATAFORSEO_API_KEY (base64 of login:password).
Then ask me to run doctor; I handle everything else.
```

Number the human steps, keep them minimal, and say outright that the agent does
the remainder. Never bury a human-required step mid-document.

## Per-skill .gitignore

Every skill that produces output or can hold credentials ships its own
`.gitignore` (the root one helps, but the skill must stay safe when copied out
alone):

```gitignore
.env
results/
.venv/
__pycache__/
```

Auto-saved output goes in `results/` inside the skill dir — never committed.

## Wrapper bin on PATH

If the skill's tool is invoked often or from other skills, ship a tiny wrapper
in `bin/` (e.g. `bin/<name>` that execs `uv run python "$SKILL_DIR/cli.py" "$@"`)
and have `setup` symlink it somewhere on PATH (`~/.local/bin`). SKILL.md then
uses the bare command everywhere instead of `cd <skill-dir> && uv run ...`.
Skip this for skills used a few times a month — the `cd && uv run` form is fine.

## Date-stamp anything that rots

Prices, model names, rate limits, and plan features drift. Every hardcoded value
of that kind gets a verification stamp, and model names get an env-var override:

```python
COST_PER_PAGE = 0.001  # verified 2026-06
MODEL = os.environ.get("EXA_RERANK_MODEL", "exa-rerank-2")  # verified 2026-06
```

When you touch a file, re-verify any stamp older than ~6 months or flag it.

## Shared code between skills

Skill dirs must be self-contained when distributed alone — no imports from
sibling skills. Cross-skill modules live canonically in `scripts/shared/` and
are synced into each consuming skill dir by `scripts/build-marketplace.ts`
(see `SHARED_MODULES` there). Edit the canonical file, rerun the build script,
commit the synced copies with it. Never hand-edit a synced copy.

## Stack

Match what the repo already uses: Python via `uv` (PEP 723 inline deps or a
local-only pyproject) or TypeScript via `bun`. Zero-dependency stdlib scripts
are best — they need no install step at all.
