#!/usr/bin/env -S npx tsx
/**
 * Veo 3.1 video generation CLI (Gemini API) with deterministic cost quoting.
 *
 * Text→video and image→video (use the GPT Image still as the first frame).
 * Optional last-frame interpolation (`--last-frame`, or `--loop` to set
 * last==first for a true forward loop). Optional ffmpeg post-process to
 * web-ready MP4 + WebM + poster (`--web`).
 *
 * Pricing is flat per-second × resolution (audio included), so the exact cost
 * is quoted BEFORE every call. A safety-filtered or timed-out generation is
 * $0 (not charged) — the quote is a ceiling.
 *
 *   Fast      720p $0.10/s · 1080p $0.12/s · 4k $0.30/s
 *   Standard  720p $0.40/s · 1080p $0.40/s · 4k $0.60/s
 *   Lite      720p $0.05/s · 1080p $0.08/s
 */
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync, appendFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, parse as parsePath } from "node:path";

import { Command, Option } from "commander";

const API_BASE = "https://generativelanguage.googleapis.com/v1beta";
const CONFIG_DIR = join(homedir(), ".config", "veo-gen");
const LOG_PATH = join(CONFIG_DIR, "usage.jsonl");
const CONFIG_ENV = join(CONFIG_DIR, "env");

const MODEL_ID: Record<string, string> = {
  fast: "veo-3.1-fast-generate-preview",
  standard: "veo-3.1-generate-preview",
  lite: "veo-3.1-lite-generate-preview",
};

// Per-second rates (USD), audio included, Gemini paid tier.
const RATE: Record<string, Record<string, number>> = {
  fast: { "720p": 0.1, "1080p": 0.12, "4k": 0.3 },
  standard: { "720p": 0.4, "1080p": 0.4, "4k": 0.6 },
  lite: { "720p": 0.05, "1080p": 0.08 },
};

const MODELS = ["fast", "standard", "lite"];
const DURATIONS = [4, 6, 8];
const RESOLUTIONS = ["720p", "1080p", "4k"];
const ASPECTS = ["16:9", "9:16"];

// Words that trip the RAI media filter when a person (esp. shirtless) is in the
// source image — surfaced as a pre-flight warning, not a hard block.
const RISKY_WORDS =
  /\b(shirtless|athletic|muscular|abs|chest|shoulders?|torso|physique|biceps|six-pack|toned|ripped|arms? overhead|raising (?:both )?arms)\b/i;

// ── helpers ──────────────────────────────────────────────────────────────────
function err(msg: string): void {
  process.stderr.write(msg + "\n");
}
function die(msg: string, code = 1): never {
  err(msg);
  process.exit(code);
}
function fmtCost(c: number): string {
  return c < 0.01 ? `$${c.toFixed(4)}` : `$${c.toFixed(2)}`;
}
function slug(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "veo";
}
function ts(): string {
  // Local timestamp without ms; safe for filenames.
  return new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
}

function loadApiKey(): string {
  let key = (process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY || "").trim();
  if (!key && existsSync(CONFIG_ENV)) {
    for (const raw of readFileSync(CONFIG_ENV, "utf8").split("\n")) {
      const m = raw.trim().match(/^(?:export\s+)?(?:GEMINI_API_KEY|GOOGLE_API_KEY)=(.*)$/);
      if (m) {
        key = m[1].trim().replace(/^["']|["']$/g, "");
        break;
      }
    }
  }
  if (!key) {
    die(
      "Error: GEMINI_API_KEY not set. Put it in ~/.config/veo-gen/env as " +
        "`export GEMINI_API_KEY=...` or export it in your shell.",
      2,
    );
  }
  return key;
}

function rateFor(model: string, resolution: string): number {
  const r = RATE[model]?.[resolution];
  if (r === undefined) {
    die(`Error: ${model} does not support ${resolution} (lite has no 4k). Pick another resolution/model.`, 2);
  }
  return r;
}

function logUsage(record: Record<string, unknown>): void {
  mkdirSync(dirname(LOG_PATH), { recursive: true });
  appendFileSync(LOG_PATH, JSON.stringify(record) + "\n");
}

function readImageB64(path: string): { mimeType: string; bytesBase64Encoded: string } {
  if (!existsSync(path)) die(`Error: image not found: ${path}`, 2);
  const ext = parsePath(path).ext.toLowerCase();
  const mimeType = ext === ".jpg" || ext === ".jpeg" ? "image/jpeg" : ext === ".webp" ? "image/webp" : "image/png";
  return { mimeType, bytesBase64Encoded: readFileSync(path).toString("base64") };
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

// ── generation ───────────────────────────────────────────────────────────────
interface GenOpts {
  prompt: string;
  model: string;
  duration: number;
  resolution: string;
  aspect: string;
  image?: string;
  lastFrame?: string;
  loop?: boolean;
  negative?: string;
  allowAdult: boolean;
  out?: string;
  web?: boolean;
  crossfade?: number;
  dryRun?: boolean;
  open: boolean;
}

async function generate(opts: GenOpts): Promise<void> {
  const modelId = MODEL_ID[opts.model];
  const rate = rateFor(opts.model, opts.resolution);
  const cost = +(rate * opts.duration).toFixed(4);

  // Pre-flight quote (always shown, like gpt-image-gen-2).
  err(
    `Veo 3.1 ${opts.model} · ${opts.duration}s · ${opts.resolution} · ${opts.aspect} → ` +
      `${fmtCost(cost)} (charged $0 if safety-filtered or timed out)`,
  );

  // RAI heads-up: body/physique wording + a person image is the #1 rejection cause.
  if ((opts.image || !opts.image) && RISKY_WORDS.test(opts.prompt)) {
    err(
      "  ⚠ prompt contains body/physique wording — Veo's RAI filter often rejects this " +
        "with a person in frame. Prefer neutral language (\"a person\", plain verbs). " +
        "personGeneration=allow_adult is " + (opts.allowAdult ? "ON." : "OFF (consider enabling)."),
    );
  }
  if (opts.model === "lite" && (opts.image || RISKY_WORDS.test(opts.prompt))) {
    err("  ⚠ Lite's people filter is stricter than Fast and often rejects body/figure content. Fast is the safer floor.");
  }

  if (opts.dryRun) {
    err("  --dry-run: not calling the API.");
    return;
  }

  const apiKey = loadApiKey();
  const instance: Record<string, unknown> = { prompt: opts.prompt };
  if (opts.image) instance.image = readImageB64(opts.image);
  if (opts.loop) {
    if (!opts.image) die("Error: --loop needs --image (it sets the last frame equal to the first frame).", 2);
    instance.lastFrame = readImageB64(opts.image);
  } else if (opts.lastFrame) {
    instance.lastFrame = readImageB64(opts.lastFrame);
  }

  const parameters: Record<string, unknown> = {
    aspectRatio: opts.aspect,
    durationSeconds: opts.duration, // MUST be a number, not a string.
    resolution: opts.resolution,
    personGeneration: opts.allowAdult ? "allow_adult" : "dont_allow",
  };
  if (opts.negative) parameters.negativePrompt = opts.negative;

  const body = JSON.stringify({ instances: [instance], parameters });
  const started = Date.now();

  const submit = await fetch(`${API_BASE}/models/${modelId}:predictLongRunning`, {
    method: "POST",
    headers: { "x-goog-api-key": apiKey, "Content-Type": "application/json" },
    body,
  });
  const submitJson: any = await submit.json().catch(() => ({}));
  const opName: string | undefined = submitJson?.name;
  if (!opName) {
    die("Submit failed:\n" + JSON.stringify(submitJson?.error ?? submitJson, null, 2), 3);
  }
  err(`  operation: ${opName}`);

  // Poll (Veo runs ~40s–10min). 10s interval, up to ~12min.
  let resp: any = null;
  for (let i = 0; i < 72; i++) {
    await sleep(10_000);
    const poll = await fetch(`${API_BASE}/${opName}`, { headers: { "x-goog-api-key": apiKey } });
    resp = await poll.json().catch(() => ({}));
    if (resp?.done) break;
    if (i % 3 === 2) err(`  …still rendering (${(i + 1) * 10}s)`);
  }
  const elapsed = ((Date.now() - started) / 1000).toFixed(0);

  if (!resp?.done) {
    logUsage(rec(opts, modelId, cost, "timeout", elapsed));
    die(`  Timed out after ${elapsed}s (no charge). The operation may still finish server-side: ${opName}`, 4);
  }
  if (resp.error) {
    logUsage(rec(opts, modelId, cost, "error", elapsed));
    die("  Error:\n" + JSON.stringify(resp.error, null, 2), 3);
  }
  const rai: string | undefined =
    resp?.response?.generateVideoResponse?.raiMediaFilteredReasons?.[0];
  if (rai) {
    logUsage(rec(opts, modelId, 0, "rai_filtered", elapsed));
    die(
      `  RAI FILTERED (charged $0): ${rai}\n` +
        "  Tip: neutralize body/physique wording, keep personGeneration=allow_adult, " +
        "and prefer Fast over Lite for figures.",
      4,
    );
  }
  const uri: string | undefined =
    resp?.response?.generateVideoResponse?.generatedSamples?.[0]?.video?.uri ??
    resp?.response?.generatedSamples?.[0]?.video?.uri;
  if (!uri) {
    logUsage(rec(opts, modelId, cost, "no_uri", elapsed));
    die("  No video URI in response:\n" + JSON.stringify(resp?.response, null, 2).slice(0, 2000), 5);
  }

  const outPath = opts.out || join(process.cwd(), `${ts()}-${slug(opts.prompt)}.mp4`);
  mkdirSync(dirname(outPath), { recursive: true });
  const dl = await fetch(uri, { headers: { "x-goog-api-key": apiKey } });
  if (!dl.ok) die(`  Download failed: HTTP ${dl.status}`, 5);
  writeFileSync(outPath, Buffer.from(await dl.arrayBuffer()));
  err(`  saved ${outPath}  (${fmtCost(cost)} est, ${elapsed}s)`);
  logUsage({ ...rec(opts, modelId, cost, "ok", elapsed), out: outPath });

  if (opts.web) webEncode(outPath, opts.crossfade);
  if (opts.open) spawnSync("open", [outPath]);
  // Final machine-readable line for the agent.
  process.stdout.write(JSON.stringify({ ok: true, out: outPath, cost_usd: cost, cost_estimated: true }) + "\n");
}

function rec(opts: GenOpts, modelId: string, cost: number, status: string, elapsed: string) {
  return {
    ts: new Date().toISOString(),
    model: modelId,
    tier: opts.model,
    duration: opts.duration,
    resolution: opts.resolution,
    aspect: opts.aspect,
    mode: opts.image ? (opts.loop ? "loop-i2v" : opts.lastFrame ? "firstlast-i2v" : "i2v") : "t2v",
    status,
    elapsed_s: Number(elapsed),
    cost_usd: cost,
    cost_estimated: true,
    prompt_preview: opts.prompt.slice(0, 180),
  };
}

// ── ffmpeg web post-process ──────────────────────────────────────────────────
function hasFfmpeg(): boolean {
  return spawnSync("ffmpeg", ["-version"], { stdio: "ignore" }).status === 0;
}

function webEncode(srcMp4: string, crossfade?: number): void {
  if (!hasFfmpeg()) {
    err("  --web: ffmpeg not found on PATH; skipping web encode. (brew install ffmpeg)");
    return;
  }
  const base = srcMp4.replace(/\.mp4$/i, "");
  let src = srcMp4;

  // Optional seamless crossfade self-loop (tail→head) for looped playback.
  if (crossfade && crossfade > 0) {
    const dur = ffprobeDuration(srcMp4);
    if (dur && dur > crossfade * 2) {
      const looped = `${base}.loop.mp4`;
      const fc =
        `[0:v]split[a][b];` +
        `[a]trim=0:${(dur - crossfade).toFixed(3)},setpts=PTS-STARTPTS[main];` +
        `[b]trim=${(dur - crossfade).toFixed(3)}:${dur.toFixed(3)},setpts=PTS-STARTPTS[tail];` +
        `[tail][main]xfade=transition=fade:duration=${crossfade}:offset=0,format=yuv420p[out]`;
      run("ffmpeg", ["-y", "-loglevel", "error", "-i", srcMp4, "-filter_complex", fc, "-map", "[out]", "-an", "-c:v", "libx264", "-crf", "20", "-preset", "slow", "-movflags", "+faststart", looped]);
      src = looped;
      err(`  web: crossfade loop → ${looped}`);
    } else {
      err("  --crossfade skipped: clip too short for the requested fade.");
    }
  }

  const mp4 = `${base}.web.mp4`;
  const webm = `${base}.web.webm`;
  const poster = `${base}.poster.jpg`;
  run("ffmpeg", ["-y", "-loglevel", "error", "-i", src, "-an", "-c:v", "libx264", "-crf", "23", "-maxrate", "2M", "-bufsize", "4M", "-preset", "slow", "-pix_fmt", "yuv420p", "-movflags", "+faststart", mp4]);
  run("ffmpeg", ["-y", "-loglevel", "error", "-i", src, "-an", "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "34", "-row-mt", "1", webm]);
  run("ffmpeg", ["-y", "-loglevel", "error", "-i", src, "-frames:v", "1", "-q:v", "3", poster]);
  err(`  web: ${mp4}  +  ${webm}  +  ${poster}`);
}

function run(cmd: string, args: string[]): void {
  const r = spawnSync(cmd, args, { stdio: ["ignore", "ignore", "inherit"] });
  if (r.status !== 0) err(`  (${cmd} exited ${r.status})`);
}

function ffprobeDuration(path: string): number | null {
  const r = spawnSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", path], { encoding: "utf8" });
  const d = parseFloat((r.stdout || "").trim());
  return Number.isFinite(d) ? d : null;
}

// ── cost summary ─────────────────────────────────────────────────────────────
function costSummary(tail?: number): void {
  if (!existsSync(LOG_PATH)) return err("No usage logged yet.");
  const rows = readFileSync(LOG_PATH, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
  if (tail) {
    for (const r of rows.slice(-tail)) {
      err(`${r.ts}  ${r.tier} ${r.duration}s ${r.resolution}  ${r.mode}  ${r.status}  ${fmtCost(r.cost_usd || 0)}`);
    }
    return;
  }
  const total = rows.reduce((s, r) => s + (r.cost_usd || 0), 0);
  const ok = rows.filter((r) => r.status === "ok").length;
  const rejected = rows.filter((r) => r.status === "rai_filtered").length;
  err(`Total: ${fmtCost(total)} (estimated) across ${rows.length} calls — ${ok} delivered, ${rejected} RAI-filtered ($0).`);
}

// ── CLI wiring ───────────────────────────────────────────────────────────────
const program = new Command();
program.name("veo-gen").description("Veo 3.1 video CLI (Gemini API) — text/image→video with deterministic cost quoting.");

program
  .command("generate")
  .description("Generate a video. Text→video, or image→video with --image (first frame).")
  .requiredOption("-p, --prompt <text>", "Final, guide-shaped motion prompt (see PROMPTING.md).")
  .option("-i, --image <path>", "First-frame image (image→video). Use a GPT Image still.")
  .option("--last-frame <path>", "Last-frame image (first+last interpolation).")
  .option("--loop", "True forward loop: set last frame == first frame (needs --image).")
  .addOption(new Option("-m, --model <tier>", "fast (default) | standard | lite").choices(MODELS).default("fast"))
  .addOption(new Option("-d, --duration <s>", "4 | 6 | 8 seconds").choices(DURATIONS.map(String)).default("8"))
  .addOption(new Option("-r, --resolution <res>", "720p (default) | 1080p | 4k").choices(RESOLUTIONS).default("720p"))
  .addOption(new Option("-a, --aspect <ratio>", "16:9 (default) | 9:16").choices(ASPECTS).default("16:9"))
  .option("--negative <text>", "Negative prompt (things to avoid).")
  .option("--no-allow-adult", "Disable personGeneration=allow_adult (it is ON by default).")
  .option("-o, --out <path>", "Output .mp4 path (default: cwd/<ts>-<slug>.mp4).")
  .option("--web", "Also produce web-ready .web.mp4 + .web.webm + .poster.jpg (needs ffmpeg).")
  .option("--crossfade <sec>", "With --web: seamless crossfade self-loop of this length.", (v) => parseFloat(v))
  .option("--dry-run", "Print the cost quote and exit without calling the API.")
  .option("--no-open", "Don't auto-open the result.")
  .action(async (o) => {
    await generate({
      prompt: o.prompt,
      model: o.model,
      duration: parseInt(o.duration, 10),
      resolution: o.resolution,
      aspect: o.aspect,
      image: o.image,
      lastFrame: o.lastFrame,
      loop: o.loop,
      negative: o.negative,
      allowAdult: o.allowAdult, // commander: --no-allow-adult sets this false
      out: o.out,
      web: o.web,
      crossfade: o.crossfade,
      dryRun: o.dryRun,
      open: o.open,
    });
  });

program
  .command("cost")
  .description("Summarize estimated spend from the usage log.")
  .option("--tail <n>", "Show the last N calls.", (v) => parseInt(v, 10))
  .action((o) => costSummary(o.tail));

program.parseAsync();
