---
name: gpt-image-gen-2
description: Generate images, illustrations, logos, infographics, photoreal shots, UI mockups, and ads with OpenAI's GPT Image 2. Translates the user's loose request into a cookbook-aligned prompt, supports reference images / moodboards for style transfer, and logs token usage + actual $ cost per call. Triggers on "make me a logo", "generate an image of…", "create an illustration", "design a poster", "gpt-image-gen", "gpt image", "image generation", "moodboard", "style transfer from this image", or any visual asset request.
---

# gpt-image-gen-2

Turn the user's loose visual brief into a well-engineered GPT Image 2 prompt, generate the asset, and log cost. Built around OpenAI's official prompting guide — see `PROMPTING.md` in this directory for the full distilled cookbook.

**Setup:** API key in `~/.config/image-gen/env` as `export OPENAI_API_KEY=sk-…`, or exported in shell. Usage log at `~/.config/image-gen/usage.jsonl`.

## Your job

1. **Classify** the request into one of these categories:
   `logo | illustration | photoreal | infographic | ui-mockup | ad | story-panel | style-transfer | edit`
2. **Interview** the user for anything missing. Ask one short message — no questionnaires. The critical fields by category are listed below.
3. **Assemble** the prompt using the structure in `PROMPTING.md`: Scene → Subject → Details → Composition → Constraints. Quote literal text. Spell tricky words letter-by-letter.
4. **Show the user the final prompt + estimated cost** (`--dry-run` first if you're unsure).
5. **Call** `cli.py generate` or `cli.py edit` and report the actual cost.
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
uv run python cli.py generate \
  -p "Original logo for Field & Flour, a local bakery. Warm, simple, timeless. Clean vector-like shapes, strong silhouette, balanced negative space. Flat design, minimal strokes, no gradients. Single centered mark with generous padding, plain background." \
  --size 1024x1024 --quality high --format png --out ./field-and-flour.png
```

### Generate (dry run — see prompt + cost estimate without spending)

```bash
uv run python cli.py generate -p "..." --quality high --dry-run
```

### Generate transparent (sticker / icon / empty-state art)

`gpt-image-2` dropped native transparent backgrounds — its `background` enum
only accepts `auto` and `opaque` now (the model was trained for scene
consistency, not isolated cut-outs). The `--transparent` flag works around it:
auto-appends a magenta-bg instruction block to your prompt, forces opaque
output, then post-processes the saved PNG to alpha out the magenta. Standard
chroma-key trick for sticker / cut-out assets.

```bash
uv run python cli.py generate \
  -p "Hand-illustrated watercolor still-life of a vintage red postbox with a single white envelope peeking out the slot. Soft warm lantern-yellow rim light. Centered single subject, ~70% of canvas. NO text or labels." \
  --size 1024x1024 --quality high --transparent --out ./postbox.png
```

The chroma-key is also exposed as a standalone command if you want to
strip a key color from an existing image:

```bash
uv run python cli.py chroma-key ./input.png -o ./output.png
uv run python cli.py chroma-key ./input.png --key-color FF00FF --tolerance 70
```

**Prompt the subject to avoid pure magenta.** Brand coral `#FF5A5F` is safe
(RGB distance² ≈ 33k, well above the default threshold of 14,700). True
hot-pink subjects will get partially keyed — recolor or raise tolerance.

### Edit / style-transfer / moodboard (image(s) + prompt → image)

```bash
# Single ref
uv run python cli.py edit \
  -p "Remove the flower from the man's hand. Do not change anything else — preserve face, pose, lighting, background, camera angle." \
  --ref input.png --out ./edited.png

# Style transfer — reference by index in the prompt
uv run python cli.py edit \
  -p "Image 1 is a style reference; Image 2 is the subject. Apply the watercolor brushwork, muted palette, and paper texture of Image 1 to the scene in Image 2. Keep Image 2's composition and subject pose unchanged." \
  --ref style-ref.jpg --ref subject.png --out ./styled.png

# Moodboard (multiple refs for vibe, new content)
uv run python cli.py edit \
  -p "Use the mood, palette, and lighting from these reference images. Generate a new scene: <subject>. Do not copy any subjects from the references; only their style." \
  --ref mood1.jpg --ref mood2.jpg --ref mood3.jpg --out ./new.png
```

### Cost log

```bash
uv run python cli.py cost              # total + per-mode + per-day summary
uv run python cli.py cost --tail 10    # last 10 calls
uv run python cli.py cost --days 7     # last 7 days only
```

## Options reference

- `--size` — `auto` (default), `1024x1024`, `1024x1536` (portrait), `1536x1024` (landscape)
- `--quality` — `low` (drafts, $0.008/1024² img), `medium` ($0.032), `high` ($0.125, default), `auto`
- `--format` — `png` (default), `webp`, `jpeg`
- `--background` — `auto`, `opaque`. (`transparent` is documented by the API but rejected by gpt-image-2; use `--transparent` instead.)
- `--transparent` / `-t` — opaque magenta render + chroma-key post-process → transparent PNG. Sticker / icon / empty-state use cases.
- `--n` — number of variations (default 1)
- `--dry-run` — print prompt + cost estimate, don't call API
- `--no-open` — don't auto-open the result in Preview

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
