---
name: icon-search
description: Find the right icon across many icon libraries (Lucide, Phosphor, Tabler, Heroicons, HugeIcons — 14k+ icons, more coming) using natural language, and get a paste-ready, per-package React import + JSX back. Scopes to the icon sets a project actually installed (no hallucinated names), with an instant local fuzzy pass and a Gemini Flash semantic pass for concept/synonym queries ("vegetarian", "delete a recipe"). Always appends icon-selection heuristics (NN/g, WCAG). Optional PNG contact-sheet preview. Triggers on "find an icon for", "which icon", "icon for X", "search icons", "what icon should I use".
---

# icon-search

Natural-language icon lookup across **multiple icon libraries** at once. Ask for
*"something vegetarian"* and get the best matches from every set — each with the
**correct import for that package** (`<Vegan/>` from lucide-react, `<IconSalad/>`
from @tabler/icons-react, `<HugeiconsIcon icon={VegetarianFoodIcon}/>`, …) so you
never hand-translate a name.

TypeScript, run with **bun**.

## How it works

Each icon set has a **builder** (reads its own npm package → normalized records:
name, SVG body, native keywords, styles, license) and an **emitter** (record →
correct React import). `build.ts` writes a **catalog**; the runtime is set-agnostic.
Adding a library = one source module in `sources.ts`. Current sets: Lucide,
Phosphor, Tabler, Heroicons, HugeIcons (**14,113 icons**); expanding toward ~15.

Two search tiers:
| Tier | Engine | Good for | Cost |
|------|--------|----------|------|
| 0 | local fuzzy over name + native keywords | literal queries | free, instant |
| 1 | Gemini `gemini-2.5-flash` ranks the in-scope names | concepts/synonyms | logged to stderr |

Default **auto**: fuzzy first; fall through to the LLM only when fuzzy is weak.

**Scope** = the icon sets a project actually installed (detected from its
`node_modules`/deps, monorepo-aware) when `--project` is given; otherwise all sets.
So an agent in a project only gets icons it can actually import.

Every result is followed by an **always-on heuristics footer** (NN/g 5-second rule,
overloaded-glyph flags, multi-set consistency, WCAG a11y) — the tool tells you when
*not* to use an icon, not just which one.

## Setup

```bash
# bun: https://bun.sh
cd <this-skill-dir> && bun install   # installs source packages + resvg
bun <this-skill-dir>/cli.ts build    # builds the catalog (search + render data)
export GEMINI_API_KEY=...             # semantic search (fuzzy works without it)
bun <this-skill-dir>/cli.ts doctor    # should end RESULT: READY — N icons across M sets
```

The small **search index** (`catalog/*.search.json`) is committed, so plain search
works right after install. `build` regenerates it and the heavier **render data**
(needed for `preview`) from the installed source packages.

## Usage

`<cli>` = `bun <this-skill-dir>/cli.ts`.

```bash
# Concept search across all sets (auto: fuzzy → LLM)
<cli> search "something vegetarian"

# Scope to a project's installed sets (correct imports, no unimportable icons)
<cli> search "delete a recipe" --project ~/Projects/myapp

# One library only:
<cli> search "calendar" --set lucide --fuzzy

# Visual confirm — render matches to a PNG (prints `PREVIEW <path>`; surface it)
<cli> search "vegetarian" --preview
<cli> preview lucide/house phosphor/carrot tabler/salad

# Machine-readable:
<cli> search "settings" --json
```

Flags: `--set id[,id]` · `--project DIR` · `--limit N` (default 12) · `--fuzzy` /
`--semantic` · `--preview` · `--json` · `--all` (ignore project scope).
When the CLI prints `PREVIEW <path>`, surface that PNG to the user.

## Output

```
Query: "something vegetarian" · scope: all 5 sets (14,113 icons) · via llm

 1. [hugeicons] VegetarianFoodIcon  <HugeiconsIcon icon={VegetarianFoodIcon} ... />  — …
 2. [lucide]    Vegan               <Vegan size={24} />  — …
 3. [tabler]    IconSalad           <IconSalad size={24} stroke={2} />  — …
Top pick — hugeicons / VegetarianFoodIcon:
  import { HugeiconsIcon } from '@hugeicons/react';
  import { VegetarianFoodIcon } from '@hugeicons/core-free-icons';
  <HugeiconsIcon icon={VegetarianFoodIcon} size={24} strokeWidth={1.5} />
Heuristics:
  • Results span multiple icon sets — pick one family + one weight for consistency.
  • Any functional icon needs an aria-label, ≥24px target, ≥3:1 contrast (WCAG).
```

`--json` returns `{ query, scope, total, via, needsLabel, results[], heuristics[], preview? }`.

## Architecture (for extending)

- `lib.ts` — `IconRecord` / `SetMeta` / `SetSource` types + SVG/string helpers.
- `sources.ts` — one `SetSource` per library (builder + emitter). **Add a set here.**
- `build.ts` — runs builders → `catalog/<set>.search.json` (committed) +
  `<set>.render.json` (artifact) + `manifest.json`.
- `cli.ts` — set-agnostic runtime: scope → fuzzy/LLM → emit → heuristics → preview.
- `heuristics.ts` — the selection-advisor rules.

To add a library: implement `build()` (its package → `IconRecord[]`) and `emit()`
(record → import + JSX), push to `SOURCES`, `bun build.ts`. See `ROADMAP.md` for the
full expansion plan, the web search box, and the per-icon pSEO pages.

## Notes

- All-sets semantic search sends every in-scope name to Gemini (~108k tokens at 5
  sets ≈ $0.033). Fine for agent use; the web box adds a lexical prefilter. Cost
  logged to stderr.
- Licenses are tracked per set (`manifest.json`). Font Awesome (when added) is
  CC-BY — its icons need visible attribution wherever rendered.
- `catalog/*.render.json` + `node_modules` are gitignored; run `bun build.ts` after
  install on a fresh machine.
