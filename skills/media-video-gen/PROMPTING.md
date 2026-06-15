# Veo 3.1 prompt guide (distilled)

Structure a prompt with these components (Google's official order). For
image→video the still already supplies **subject + scene**, so spend the prompt
on **action, camera, and ambiance**.

- **Subject** — who/what is in frame.
- **Action** — what they do. Keep it to ONE grounded beat for a background clip.
- **Camera** — `locked-off`, `slow dolly push-in`, `aerial`, `eye-level`, `static`.
- **Composition** — `wide shot`, `single shot`, `subject framed right, negative space left`.
- **Focus / lens** — `deep focus`, `shallow focus`, `wide-angle`, `macro`.
- **Ambiance** — light + color: `warm tones`, `even morning daylight`, `low-key`.
- **Style** — `cinematic`, `fine 35mm film grain`, `muted color grade`.
- **Audio** (optional) — dialogue in "quotes", named SFX, ambient bed. Omit for
  silent background heroes.

## Background-hero rules (what we learned shipping a content-site hero)

- **Subtle, single motion.** A background must not distract. One slow beat
  (a breath, a settle, a gentle stretch), not a sequence.
- **Kill the "AI glow."** Explicitly negate it: `absolutely NO volumetric
  god-rays, NO light beams, NO glowing, NO floating dust`. Ask for `natural,
  even, realistic daylight` instead.
- **Play-once beats looping.** For directional/gestural motion, play the clip
  once and freeze on the last frame (drop the HTML `loop` attribute) — the
  Superpower pattern. Only loop genuinely ambient/cyclical motion.
- **For a real loop**, use `--loop` (first frame == last frame) so motion
  departs and returns. Add `--web --crossfade 0.5` if the seam is still loose.

## RAI / safety filter (the #1 cost sink)

Veo's media filter rejects body/physique content, especially a **shirtless
subject** in the source image.

- **Avoid** body words: `shirtless, athletic, muscular, chest, shoulders, abs,
  torso, arms overhead, raising arms`. The CLI warns when it spots them.
- **Use** neutral language: `a person`, plain verbs, describe the room/light.
- **Keep `personGeneration: allow_adult`** (on by default in this CLI).
- **Lite is stricter than Fast** — it rejects figure content Fast accepts.
  Use Fast (or Standard) for any human/fitness subject; Lite is for
  landscapes/objects/abstract.
- A rejection costs **$0**, but it burns a ~1–10 min round-trip. Get the wording
  right the first time.

## Hard limits

- `durationSeconds`: **4, 6, or 8 only** (no 10s).
- Resolutions: 720p / 1080p / 4k (Lite has no 4k).
- Scene extension (+7s) exists on Fast/Standard, not Lite (not wired in this CLI).

## Worked example (the content-site hero)

```bash
pnpm exec tsx cli.ts generate \
  -i d6-wide.png --loop --model fast --duration 8 --resolution 720p \
  -p "A person standing in a warm, minimalist concrete room with a floor-to-ceiling
      window overlooking distant mountains in soft natural morning daylight. A calm
      morning moment: they ease into a gentle upward stretch, then settle back to a
      natural standing rest, beginning and ending in the same pose. Locked-off
      eye-level wide shot, figure framed right with negative space left. Natural,
      even daylight — absolutely NO god-rays, NO light beams, NO glowing, NO dust.
      Cinematic, fine 35mm film grain, muted natural grade. No walking, no people
      entering frame." \
  --web --out hero.mp4
```
