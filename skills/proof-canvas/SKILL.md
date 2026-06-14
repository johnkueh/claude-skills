---
name: proof-canvas
description: >
  Publish proof-of-work screenshots to a private drafty canvas so John can eye
  visual results from any device and annotate directly on the images. Use at
  the END of any task whose correctness is visual (UI, layout, component,
  email render, chart, design) — the proof canvas IS part of the deliverable,
  required by ~/Projects/CLAUDE.md and ship-it step 10. NOT for work that
  merely renders somewhere (README/doc/copy/config changes) — if John doesn't
  need to look at pixels to judge it, skip the canvas.
  Triggers: finishing visual work, "proof canvas", "proof image", "show me",
  "where's the proof", or re-pushing updated proof after addressing feedback.
---

# Proof canvas

Turn verification screenshots into a private drafty canvas: captions tell the
story, John annotates the pixels Figma-style, and the comments flow back
through the normal drafty loop. Terminal-friendly too — the canvas URL is a
plain https link (clickable in Ghostty), unlike file paths.

## When

At the end of any task whose **correctness is visual** — John has to look at
it to judge it (UI, layout, component, design, email render, chart). Before
(or as part of) the final report. Screenshot the states that matter while
verifying — final state, before/after if the diff tells the story, mobile
(375px) if the surface is responsive — and keep the PNGs.

**Skip it** when verification isn't visual, even if the artifact displays on
a page: README/doc rewrites, copy edits, config/script changes. Verify those
yourself and report in text. (John, 2026-06-11, on a README-rewrite proof
canvas: "for things that don't need visual verification, no need to make a
canvas and show proof.")

## How

```sh
"${CLAUDE_PLUGIN_ROOT}/skills/proof-canvas/scripts/push-proof.sh" \
  --title "Proof: <feature, plain words>" \
  --project <project> \
  --meta "branch <b> · commit <sha> · <where verified> · <date>" \
  [--story notes.html] \
  shot1.png "<strong>Read state.</strong> What to look at and why it's right." \
  shot2.png "<strong>Editing.</strong> ..." \
  mobile.png "<strong>Mobile, long title.</strong> ..."
```

- Captions are HTML; lead with a `<strong>` label, then one sentence of what
  the shot proves. This is the story — write it for John skimming on his
  phone, not as alt text.
- `--story` takes a file of HTML paragraphs for anything longer than captions
  carry: the bug found along the way, a before/after narrative, what was NOT
  changed. Optional — don't pad.
- **Paste-ready text goes in `<div class="paste">…</div>` (or `<pre>`)** in
  the story — the template styles it and adds a copy button automatically.
  Never hand-roll a block style for copy-targets: a copy-target without a
  copy button is a bug (John, 2026-06-13, on the X-profile canvas — selecting
  text on a phone is not a workflow). Markdown canvases get buttons free from
  the platform (`.canvas-prose pre`); HTML artifacts like proof canvases only
  get them from this template's script.
- Portrait screenshots are auto-rendered at phone width; landscape full-bleed.
- Iterating after feedback? Re-push with `--slug <existing>` so the canvas
  updates in place and history keeps the old version.
- The script pushes `--private` (owner-only) and prints the URL.
- `--project` is required and the script always tags `proof` — proof canvases
  used to land unfiled/untagged, which is what the 2026-06-12 canvas audit
  spent most of its time cleaning up. Use the repo name (drafty, clove,
  recipes, johnkueh.com, …).

## Report

- Put the **bare URL** in the final report (never bold-wrap links).
- ALSO send the raw PNGs via SendUserFile — they render inline in the mobile
  app, which is often where John first sees a background job's report.
- Then watch the canvas like any drafty canvas: comments on the proof are
  feedback on the work — address, reply, resolve.

## Notes

- Images ride inline as data URIs — no asset hosting. Keep each PNG under
  ~500KB (screenshot at 1x, crop dead space) and the canvas under ~5MB.
- Don't reuse one mega proof canvas across features — one canvas per feature
  (or per ship), `--slug` only for iterations of the same proof.
- Proof canvases are disposable; archive/rm old ones freely.
