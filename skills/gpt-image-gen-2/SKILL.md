---
name: gpt-image-gen-2
description: Generate images, illustrations, logos, infographics, photoreal shots, UI mockups, and ads with OpenAI's GPT Image 2. Translates the user's loose request into a cookbook-aligned prompt, supports reference images / moodboards for style transfer, and logs token usage + actual $ cost per call. Triggers on "make me a logo", "generate an image of…", "create an illustration", "design a poster", "gpt-image-gen", "gpt image", "image generation", "moodboard", "style transfer from this image", or any visual asset request.
---

# gpt-image-gen-2

Turn the user's loose visual brief into a well-engineered GPT Image 2 prompt, generate the asset, and log cost. Built around OpenAI's official prompting guide — see `PROMPTING.md` in this directory for the full distilled cookbook.

**Setup:** TypeScript CLI (`cli.ts`) — run `pnpm install` in this directory once (needs Node.js ≥ 18). Auth either way:
- **API key** (default): in `~/.config/image-gen/env` as `export OPENAI_API_KEY=sk-…`, or exported in shell.
- **ChatGPT plan** (default when signed in): no API key — bills your ChatGPT Plus/Pro quota. Run `pnpm exec tsx cli.ts setup` once to sign in; after that it's used automatically unless you pass `--api`. See the auth section below.

Usage log at `~/.config/image-gen/usage.jsonl`.

## Your job

1. **Classify** the request into one of these categories:
   `logo | illustration | photoreal | infographic | ui-mockup | ad | story-panel | style-transfer | edit`
2. **Interview** the user for anything missing. Ask one short message — no questionnaires. The critical fields by category are listed below.
3. **Assemble** the prompt using the structure in `PROMPTING.md`: Scene → Subject → Details → Composition → Constraints. Quote literal text. Spell tricky words letter-by-letter.
4. **Show the user the final prompt + estimated cost** (`--dry-run` first if you're unsure).
5. **Call** `cli.ts generate` or `cli.ts edit` and report the actual cost.
6. **Iterate small.** Single-change edits — "change only X, keep everything else the same" — and repeat the preserve list each turn (per the cookbook's anti-drift rule).

If the user already provided a complete brief, skip step 2.

## Critical fields by category

- **logo**: brand name, what it does, vibe (warm/sharp/playful/serious), whether literal wordmark or symbol-only
- **illustration**: subject, style ref (Ghibli/flat/watercolor/3D), palette, framing
- **photoreal**: subject, action, lens/lighting cues, location, mood — and the word "photorealistic" goes in the prompt
- **infographic**: topic, audience, required components (list them explicitly), label/no-label preference
- **ui-mockup**: product/app, screen purpose, real interface elements (not concept art language)
- **ad**: brand, audience, concept, exact tagline (in quotes), placement
- **story-panel**: narrative beat for this panel, characters' actions
- **style-transfer / edit**: which reference is style vs. content, what must change, what must NOT change

## Commands

Run from this skill's base directory.

### Generate (text → image)

```bash
pnpm exec tsx cli.ts generate \
  -p "Original logo for Field & Flour, a local bakery. Warm, simple, timeless. Clean vector-like shapes, strong silhouette, balanced negative space. Flat design, minimal strokes, no gradients. Single centered mark with generous padding, plain background." \
  --size 1024x1024 --quality high --format png --out ./field-and-flour.png
```

### Generate (dry run — see prompt + cost estimate without spending)

```bash
pnpm exec tsx cli.ts generate -p "..." --quality high --dry-run
```

### Generate transparent (sticker / icon / empty-state art)

`gpt-image-2` dropped native transparent backgrounds — its `background` enum
only accepts `auto` and `opaque` now (the model was trained for scene
consistency, not isolated cut-outs). Confirmed for the ChatGPT-plan/Responses
path too: requesting `background: "transparent"` returns
`"Transparent background is not supported for this model."` — it's a model
limitation, not an API-surface one. So `--transparent` works around it on both
routes: auto-appends a magenta-bg instruction block to your prompt, forces
opaque output, then keys out the magenta.

The keyer is a proper **soft matte + decontamination + despill** (not a hard
threshold), so anti-aliased edges stay clean instead of leaving a pink halo:
edge pixels get partial alpha, then their true colour is recovered by un-mixing
the known magenta background (`fg = (observed − (1−α)·magenta) / α`), and any
residual magenta cast on opaque pixels is shaved off.

```bash
pnpm exec tsx cli.ts generate \
  -p "Hand-illustrated watercolor still-life of a vintage red postbox with a single white envelope peeking out the slot. Soft warm lantern-yellow rim light. Centered single subject, ~70% of canvas. NO text or labels." \
  --size 1024x1024 --quality high --transparent --out ./postbox.png
```

The chroma-key is also exposed as a standalone command if you want to
strip a key color from an existing image:

```bash
pnpm exec tsx cli.ts chroma-key ./input.png -o ./output.png
# tune: --lo (keep more, raise toward 0.3) / --hi (cut more, lower toward 0.45) / --despill 0-1
pnpm exec tsx cli.ts chroma-key ./input.png --lo 0.18 --hi 0.55 --despill 0.8
```

**Prompt the subject to avoid pure magenta.** The keyer flags a pixel as
background by its magenta coverage `m = (min(R,B) − G)/255`, so greens, browns,
yellows, and whites are safe; only genuinely magenta/hot-pink subject areas get
keyed. If a subject edge is being eaten, raise `--lo`; if magenta survives in
corners, lower `--hi`.

### Edit / style-transfer / moodboard (image(s) + prompt → image)

```bash
# Single ref
pnpm exec tsx cli.ts edit \
  -p "Remove the flower from the man's hand. Do not change anything else — preserve face, pose, lighting, background, camera angle." \
  --ref input.png --out ./edited.png

# Style transfer — reference by index in the prompt
pnpm exec tsx cli.ts edit \
  -p "Image 1 is a style reference; Image 2 is the subject. Apply the watercolor brushwork, muted palette, and paper texture of Image 1 to the scene in Image 2. Keep Image 2's composition and subject pose unchanged." \
  --ref style-ref.jpg --ref subject.png --out ./styled.png

# Moodboard (multiple refs for vibe, new content)
pnpm exec tsx cli.ts edit \
  -p "Use the mood, palette, and lighting from these reference images. Generate a new scene: <subject>. Do not copy any subjects from the references; only their style." \
  --ref mood1.jpg --ref mood2.jpg --ref mood3.jpg --out ./new.png
```

### Cost log

```bash
pnpm exec tsx cli.ts cost              # total + per-mode + per-day summary
pnpm exec tsx cli.ts cost --tail 10    # last 10 calls
pnpm exec tsx cli.ts cost --days 7     # last 7 days only
```

### Batch — many images in parallel (ChatGPT plan)

Generate a whole set from a JSON manifest, running up to **8 at a time** against a
single shared `openai-oauth` proxy (no per-image proxy churn). This is the way to
do bulk generation on the free plan path.

```bash
pnpm exec tsx cli.ts batch --manifest images.json --concurrency 5
```

`images.json` is an array of items; each needs `prompt` + `out` (`size`/`quality`/`format` optional):

```json
[
  { "prompt": "Photorealistic editorial photograph: ...", "out": "public/images/a.webp" },
  { "prompt": "...", "out": "public/images/b.webp", "size": "1536x1024", "quality": "high" }
]
```

- `--concurrency <1-8>` — parallel generations (default 4; capped at 8).
- `--skip-existing` — skip items whose `out` already exists, so a re-run **resumes** and retries only failures.
- `--size` / `--quality` / `--format` — defaults for items that omit them; `--model` / `--reasoning` / `--oauth-port` as in `generate`.

Prints a JSON summary `{ ok, failed, failures[] }`. A failed item isn't written, so re-running with `--skip-existing` retries only the misses.

### Auth: ChatGPT plan by default, API key as fallback

The CLI **defaults to your ChatGPT plan** whenever `~/.codex/auth.json` exists
(no `$` charge — bills plan quota). If it's not signed in, it falls back to the
`OPENAI_API_KEY` path automatically. Override per call:
- `--chatgpt-auth` — force the ChatGPT-plan path.
- `--api` — force the API-key path even when ChatGPT auth is present.

The ChatGPT-plan path routes through the local
[`openai-oauth`](https://www.npmjs.com/package/openai-oauth) proxy and the
Responses API `image_generation` tool (gpt-image-2 inside the model's reasoning
loop), the same mechanism Codex itself uses.

**One-time setup** — sign in with your ChatGPT account (caches the token at `~/.codex/auth.json`) and verify:

```bash
pnpm exec tsx cli.ts setup     # runs `npx @openai/codex login` + doctor
pnpm exec tsx cli.ts doctor    # re-check anytime (npx, auth, proxy reachability)
```

If you skip `setup`, the first `--chatgpt-auth` call auto-runs the login itself. Then just add the flag — the `openai-oauth` proxy is auto-started:

```bash
pnpm exec tsx cli.ts generate -p "Flat vector logo for a bakery, warm and simple" --chatgpt-auth
pnpm exec tsx cli.ts edit -p "Make the sky a warm sunset, keep everything else" --ref photo.png --chatgpt-auth
```

- `--model` — `gpt-5.5` (default, strongest reasoning), `gpt-5.4`, `gpt-5.4-mini`. The model drives the `image_generation` tool's planning; higher tiers use more quota.
- `--reasoning` — effort for that planning: `none|low|medium|high|xhigh` (default `medium`).
- `--web-search` — off by default (keeps the prompt verbatim + faster); enable for real-person/factual accuracy.
- `--oauth-port` — proxy port (default `10531`).
- `--transparent` works (post-process chroma-key). `--mask` and `--n > 1` are **not** supported on this path.

**Trade-offs vs. the API-key path:**
- No `$` cost; usage is logged with `cost_usd: 0, plan_quota: true`.
- For **bulk** generation, use `batch` (below) — it parallelizes the plan path across one shared proxy.
- The endpoint is **undocumented** and can change without notice. Personal use only.

**Unattended / background use (when Claude drives the skill).** After the one-time
`codex login`, the token auto-refreshes — no recurring login. The only remaining
gate is Claude Code's permission prompt when the agent spawns the `openai-oauth`
proxy. To run hands-off, add this once to your **own** `.claude/settings.json`
(a plugin can't grant itself shell permissions — you must opt in):

```jsonc
"permissions": {
  "allow": [
    "Bash(npx -y openai-oauth:*)",
    "Bash(npx openai-oauth:*)",
    "Bash(npx -y @openai/codex:*)",
    "Bash(npx @openai/codex:*)"
  ]
}
```

With that in place: login persists + proxy auto-spawns silently → recurring
background generation with zero interaction. The only non-interactive stops are
plan-quota exhaustion or the upstream endpoint changing. (Running the CLI
yourself in a plain terminal needs none of this — the prompt is Claude-Code-only.)

## Options reference

- `--size` — `auto` (default), `1024x1024`, `1024x1536` (portrait), `1536x1024` (landscape)
- `--quality` — `low` (drafts, $0.008/1024² img), `medium` ($0.032), `high` ($0.125, default), `auto`
- `--format` — `png` (default), `webp`, `jpeg`
- `--background` — `auto`, `opaque`. (`transparent` is documented by the API but rejected by gpt-image-2; use `--transparent` instead.)
- `--transparent` / `-t` — opaque magenta render + soft-matte/despill keyer → clean transparent PNG. Sticker / icon / empty-state use cases. Works on both auth paths.
- `--n` — number of variations (default 1; ignored on the ChatGPT-plan path, which returns 1 per call)
- `--dry-run` — print prompt + cost estimate, don't call API
- `--no-open` — don't auto-open the result in Preview

**Auth (see auth section):**
- *(default)* — ChatGPT plan if `~/.codex/auth.json` exists, else API key
- `--chatgpt-auth` — force ChatGPT-plan path · `--api` — force API-key path
- `--model` (`gpt-5.5`|`gpt-5.4`|`gpt-5.4-mini`) · `--reasoning` (`none`..`xhigh`, default `medium`) · `--web-search` · `--oauth-port`

## Pricing (logged automatically)

- Text input: $5/1M tokens (cached $1.25/1M)
- Image input (refs): $8/1M tokens (cached $2/1M)
- Image output: $30/1M tokens

Typical actual costs:
- 1024×1024 high quality generate: ~$0.13
- 1024×1024 low quality (draft): ~$0.01
- 1024×1536 high quality generate: ~$0.19
- Edit with 1 ref + high output: ~$0.14-0.15

Cost is **estimated pre-flight** and shown before each call; **actual cost** is computed from the API's `usage` response and logged to `~/.config/image-gen/usage.jsonl`.

## Iteration rules (from the cookbook)

- **Don't overload one prompt.** Start with a clean base; refine with small single-change follow-ups ("warmer lighting", "remove the extra tree", "make the logo mark thicker").
- **Repeat the preserve list every iteration.** The model doesn't remember previous turns — say "keep face, lighting, background, camera angle" again each time.
- **Use "change only X / keep everything else the same"** for surgical edits.
- **Don't over-spec camera details.** Lens/aperture are interpreted loosely; use them for vibe, not exact simulation.
- **Stock-photo wording kills logos & UI work.** Write logos like "vector-like, balanced negative space, scalable, flat"; write UI like "shipped interface, real interface elements", not "design sketch of…".

See `PROMPTING.md` for category-by-category prompt templates and worked examples.
