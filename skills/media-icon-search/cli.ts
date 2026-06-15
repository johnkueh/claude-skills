#!/usr/bin/env bun
/**
 * icon-search — natural-language icon search across many icon sets.
 *
 *   search "<query>"   find icons; returns the correct import + JSX per set
 *   preview <slug...>  render matches to a PNG contact sheet (slug = set/name)
 *   build              (re)build the catalog from installed source packages
 *   doctor             check runtime, key, catalog, sets
 *
 * Reads the prebuilt catalog (see build.ts). Search uses the small committed
 * index (zero-setup); preview needs the render artifact (`bun build.ts`).
 * Scope = the project's installed sets when --project resolves them, else all.
 *
 * Strategy: tier-0 fuzzy over name+keywords → Gemini Flash rerank for concepts.
 */

import { readFileSync, existsSync, mkdirSync, writeFileSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import { humanize, wrapAttrs, type SetMeta } from "./lib.ts";
import { SOURCE_BY_ID } from "./sources.ts";
import { advise } from "./heuristics.ts";

const SKILL_DIR = dirname(fileURLToPath(import.meta.url));
const CATALOG = join(SKILL_DIR, "catalog");
const GEMINI_MODEL = "gemini-2.5-flash";

// ─────────────────────────────────────────────────────── catalog loading

interface SearchRec {
  set: string;
  name: string;
  component?: string;
  keywords: string[];
  styles: string[];
  human: string; // precomputed
  hay: string; // name + keywords, for fuzzy
}

function loadManifest(): { sets: SetMeta[] } {
  const f = join(CATALOG, "manifest.json");
  if (!existsSync(f)) throw new Error(`catalog not built — run: (cd ${SKILL_DIR} && bun install && bun build.ts)`);
  return JSON.parse(readFileSync(f, "utf8"));
}

function loadSearch(setIds: string[]): SearchRec[] {
  const recs: SearchRec[] = [];
  for (const id of setIds) {
    const f = join(CATALOG, `${id}.search.json`);
    if (!existsSync(f)) continue;
    for (const r of JSON.parse(readFileSync(f, "utf8"))) {
      const human = humanize(r.name);
      recs.push({ set: id, ...r, human, hay: `${human} ${(r.keywords ?? []).join(" ")}` });
    }
  }
  return recs;
}

function projectDeps(projectDir: string): Record<string, string> {
  try {
    const pj = JSON.parse(readFileSync(join(projectDir, "package.json"), "utf8"));
    return { ...(pj.dependencies ?? {}), ...(pj.devDependencies ?? {}) };
  } catch {
    return {};
  }
}

/** a package is "present" if declared in package.json OR resolvable in node_modules
 *  walking up (covers monorepos that install into a sub-package's node_modules). */
function pkgPresent(projectDir: string, pkg: string, deps: Record<string, string>): boolean {
  if (pkg in deps) return true;
  let dir = projectDir;
  for (let i = 0; i < 6; i++) {
    if (existsSync(join(dir, "node_modules", pkg, "package.json"))) return true;
    // also peek one level into common monorepo workspace dirs
    for (const ws of ["app", "web", "packages", "apps"]) {
      if (existsSync(join(dir, ws, "node_modules", pkg, "package.json"))) return true;
    }
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return false;
}

/** sets actually installed in a project, via each set's detectPackages. */
function installedSetIds(projectDir: string, sets: SetMeta[]): string[] {
  const deps = projectDeps(projectDir);
  return sets.filter((s) => s.detectPackages.some((p) => pkgPresent(projectDir, p, deps))).map((s) => s.id);
}

// ─────────────────────────────────────────────────────────── tier 0: fuzzy

interface Hit {
  set: string;
  name: string;
  score: number;
}

const STOPWORDS = new Set([
  "a", "an", "the", "for", "of", "to", "in", "on", "at", "by", "with", "and", "or",
  "my", "your", "our", "their", "its", "that", "this", "these", "those", "some",
  "something", "anything", "thing", "app", "application", "icon", "icons", "ui",
  "button", "symbol", "sign", "image", "page", "screen", "is", "are", "be",
]);

function fuzzyRank(query: string, recs: SearchRec[], limit: number): Hit[] {
  const q = query.trim().toLowerCase();
  // strip filler words so "pantry for a recipe app" doesn't match "forward" via "for"
  const raw = q.split(/\s+/).filter(Boolean);
  const content = raw.filter((t) => !STOPWORDS.has(t));
  const qt = content.length ? content : raw;
  const hits: Hit[] = [];
  for (const r of recs) {
    const nameTokens = r.human.split(" ");
    const hayTokens = r.hay.split(" ");
    let score = 0;
    if (r.human === q) score = 1000;
    else {
      const nameHits = qt.filter((t) => nameTokens.includes(t)).length;
      const hayHits = qt.filter((t) => hayTokens.includes(t)).length;
      if (nameHits === qt.length) {
        score = 100 + 12 * nameHits - Math.max(0, nameTokens.length - qt.length) * 6;
        if (nameTokens[0] === qt[0]) score += 15;
      } else if (hayHits === qt.length) {
        score = 60 + 6 * hayHits; // matched via keyword
      } else if (q.length >= 3 && r.hay.includes(q)) {
        score = 50;
      } else if (hayHits > 0) {
        score = 12 * hayHits;
      } else {
        score = qt.filter((t) => t.length >= 3 && hayTokens.some((h) => h.startsWith(t))).length * 7;
      }
    }
    if (score > 0) hits.push({ set: r.set, name: r.name, score });
  }
  hits.sort((a, b) => b.score - a.score || a.name.length - b.name.length);
  return hits.slice(0, limit);
}

// ──────────────────────────────────────────── tier 1: Gemini LLM-rank

interface LlmOut {
  needsLabel: boolean;
  results: Array<{ set: string; name: string; reason?: string }>;
}

async function llmRank(query: string, recs: SearchRec[], limit: number): Promise<LlmOut> {
  const key = process.env.GEMINI_API_KEY;
  if (!key) throw new Error("GEMINI_API_KEY not set (semantic search; --fuzzy works without it)");

  const valid = new Set(recs.map((r) => `${r.set}:${r.name}`));
  const list = recs.map((r) => `${r.set}:${r.name}`).join("\n");
  const prompt =
    `You are an icon search engine spanning multiple icon sets.\n` +
    `User intent: "${query}"\n\n` +
    `Pick up to ${limit} icons from the list below whose visual meaning best matches. ` +
    `Reason about synonyms/related concepts (e.g. "vegetarian" → leaf, plant, broccoli, salad). ` +
    `Spread good options across sets when comparable. Only return genuinely relevant matches — if few ` +
    `or none fit, return fewer (empty is fine); never pad with weak icons. Also judge whether this ` +
    `concept even HAS a clear icon metaphor — if it's abstract (only home/search/print are near-universal), set needsLabel=true.\n\n` +
    `Rules: return ONLY "set:name" entries that appear VERBATIM below; best first.\n\n` +
    `ICONS (set:name):\n${list}`;

  const body = {
    contents: [{ parts: [{ text: prompt }] }],
    generationConfig: {
      temperature: 0.1,
      responseMimeType: "application/json",
      responseSchema: {
        type: "OBJECT",
        properties: {
          needsLabel: { type: "BOOLEAN" },
          results: {
            type: "ARRAY",
            items: {
              type: "OBJECT",
              properties: { set: { type: "STRING" }, name: { type: "STRING" }, reason: { type: "STRING" } },
              required: ["set", "name"],
            },
          },
        },
        required: ["needsLabel", "results"],
      },
    },
  };

  const url = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent?key=${key}`;
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) throw new Error(`Gemini ${res.status}: ${(await res.text()).slice(0, 300)}`);
  const json: any = await res.json();
  const u = json?.usageMetadata;
  if (u) {
    const cost = ((u.promptTokenCount ?? 0) / 1e6) * 0.3 + ((u.candidatesTokenCount ?? 0) / 1e6) * 2.5;
    console.error(`  llm: ${u.promptTokenCount} in + ${u.candidatesTokenCount} out ≈ $${cost.toFixed(5)}`);
  }
  let parsed: LlmOut;
  try {
    parsed = JSON.parse(json?.candidates?.[0]?.content?.parts?.[0]?.text ?? "{}");
  } catch {
    parsed = { needsLabel: false, results: [] };
  }
  parsed.results = (parsed.results ?? []).filter((r) => valid.has(`${r.set}:${r.name}`)).slice(0, limit);
  return parsed;
}

// ─────────────────────────────────────────────────────── preview (rasterise)

function loadRender(setIds: string[]): Record<string, any> {
  const map: Record<string, any> = {};
  for (const id of setIds) {
    const f = join(CATALOG, `${id}.render.json`);
    if (!existsSync(f)) continue;
    const data = JSON.parse(readFileSync(f, "utf8"));
    for (const [name, r] of Object.entries(data)) map[`${id}:${name}`] = r;
  }
  return map;
}

async function buildPreview(slugs: string[], query: string): Promise<string> {
  let Resvg: any;
  try {
    ({ Resvg } = await import("@resvg/resvg-js"));
  } catch {
    throw new Error(`preview needs @resvg/resvg-js — run: (cd ${SKILL_DIR} && bun install)`);
  }
  const setIds = [...new Set(slugs.map((s) => s.split(":")[0].split("/")[0]))];
  const render = loadRender(setIds);
  if (!Object.keys(render).length) throw new Error(`render data missing — run: (cd ${SKILL_DIR} && bun build.ts)`);

  const color = "#111827";
  const cols = Math.min(slugs.length, 5);
  const cellW = 152, cellH = 128, iconSize = 44;
  const rows = Math.ceil(slugs.length / cols);
  const W = cols * cellW, H = rows * cellH + 8;

  const cells: string[] = [];
  slugs.forEach((slug, i) => {
    const key = slug.replace("/", ":");
    const rec = render[key];
    const col = i % cols, row = Math.floor(i / cols);
    const cx = col * cellW, cy = row * cellH;
    if (rec) {
      const [, , vbW] = rec.viewBox.split(" ").map(Number);
      const scale = iconSize / (vbW || 24);
      const ix = cx + (cellW - iconSize) / 2, iy = cy + 18;
      cells.push(`<g transform="translate(${ix},${iy}) scale(${scale})" ${wrapAttrs(rec.wrap)}>${rec.body}</g>`);
    }
    const label = key.length > 22 ? key.slice(0, 21) + "…" : key;
    cells.push(`<text x="${cx + cellW / 2}" y="${cy + cellH - 16}" font-family="ui-sans-serif,system-ui,sans-serif" font-size="10" text-anchor="middle" fill="#374151">${label}</text>`);
  });

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"><rect width="${W}" height="${H}" fill="#ffffff"/>${cells.join("")}</svg>`;
  const png = new Resvg(svg, { fitTo: { mode: "width", value: W * 2 } }).render().asPng();

  const outDir = process.env.CLAUDE_JOB_DIR ? join(process.env.CLAUDE_JOB_DIR, "tmp") : tmpdir();
  if (!existsSync(outDir)) mkdirSync(outDir, { recursive: true });
  const out = join(outDir, `icon-preview-${(query.replace(/[^a-z0-9]+/gi, "-").toLowerCase().slice(0, 40) || "preview")}-${Date.now()}.png`);
  writeFileSync(out, png);
  return out;
}

// ──────────────────────────────────────────────────────── output helpers

function emitFor(set: string, name: string, style?: string) {
  const src = SOURCE_BY_ID[set];
  const searchFile = join(CATALOG, `${set}.search.json`);
  const rec = JSON.parse(readFileSync(searchFile, "utf8")).find((r: any) => r.name === name);
  const s = style || rec?.styles?.[0] || src.meta.defaultStyle;
  return src.emit({ name, component: rec?.component, viewBox: "", wrap: {}, body: "", keywords: [], styles: rec?.styles ?? [s] }, s);
}

// ──────────────────────────────────────────────────────────────── CLI

function parseArgs(argv: string[]) {
  const flags: Record<string, string | boolean> = {};
  const pos: string[] = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith("--")) {
      const k = a.slice(2);
      const next = argv[i + 1];
      if (next && !next.startsWith("--")) { flags[k] = next; i++; } else flags[k] = true;
    } else pos.push(a);
  }
  return { flags, pos };
}

function resolveScope(flags: Record<string, string | boolean>, sets: SetMeta[]): { ids: string[]; label: string } {
  if (flags.set) {
    const ids = String(flags.set).split(",").filter((id) => sets.some((s) => s.id === id));
    return { ids, label: ids.join(", ") };
  }
  const project = (flags.project as string) || process.env.ICON_SEARCH_PROJECT;
  if (project && !flags.all) {
    const ids = installedSetIds(project, sets);
    if (ids.length) return { ids, label: `installed in project: ${ids.join(", ")}` };
  }
  return { ids: sets.map((s) => s.id), label: `all ${sets.length} sets` };
}

async function cmdSearch(flags: Record<string, string | boolean>, pos: string[]) {
  const query = pos.join(" ").trim();
  if (!query) throw new Error('usage: search "<query>" [--set id] [--project DIR] [--limit N] [--fuzzy|--semantic] [--preview] [--json]');
  const { sets } = loadManifest();
  const scope = resolveScope(flags, sets);
  if (!scope.ids.length) throw new Error("no sets in scope");
  const total = sets.filter((s) => scope.ids.includes(s.id)).reduce((n, s) => n + s.count, 0);
  const recs = loadSearch(scope.ids);
  const limit = Number(flags.limit ?? 12);

  const mode = flags.fuzzy ? "fuzzy" : flags.semantic || flags.llm ? "semantic" : "auto";
  let picks: Array<{ set: string; name: string; reason?: string }>;
  let needsLabel = false;
  let via: string;

  if (mode === "fuzzy") {
    picks = fuzzyRank(query, recs, limit);
    via = "fuzzy";
  } else if (mode === "semantic") {
    const o = await llmRank(query, recs, limit);
    picks = o.results; needsLabel = o.needsLabel; via = "llm";
  } else {
    const fz = fuzzyRank(query, recs, limit);
    if (fz.length && fz[0].score >= 100) { picks = fz; via = "fuzzy"; }
    else { const o = await llmRank(query, recs, limit); picks = o.results; needsLabel = o.needsLabel; via = "llm"; }
  }

  if (!picks.length) { console.log(`No matches for "${query}".`); return; }

  const results = picks.map((p) => ({ ...p, human: humanize(p.name), ...emitFor(p.set, p.name) }));
  const tips = advise({ results: picks, scopeSetCount: scope.ids.length, needsLabel });

  let preview: string | undefined;
  if (flags.preview) preview = await buildPreview(results.map((r) => `${r.set}:${r.name}`), query);

  if (flags.json) {
    console.log(JSON.stringify({ query, scope: scope.ids, total, via, needsLabel, results, heuristics: tips, preview }, null, 2));
    return;
  }

  console.log(`Query: "${query}" · scope: ${scope.label} (${total.toLocaleString()} icons) · via ${via}\n`);
  results.forEach((r, i) => {
    const num = String(i + 1).padStart(2, " ");
    const reason = (r as any).reason ? `  — ${(r as any).reason}` : "";
    console.log(`${num}. [${r.set}] ${(r.component ?? r.name).padEnd(24)} ${r.usage}${reason}`);
  });
  const top = results[0];
  console.log(`\nTop pick — ${top.set} / ${top.name}:`);
  top.imports.forEach((l) => console.log(`  ${l}`));
  console.log(`  ${top.usage}`);
  console.log(`\nHeuristics:`);
  tips.forEach((t) => console.log(`  • ${t}`));
  if (preview) console.log(`\nPREVIEW ${preview}`);
}

async function cmdPreview(flags: Record<string, string | boolean>, pos: string[]) {
  if (!pos.length) throw new Error("usage: preview <set/name> [set/name...]  (e.g. lucide/house phosphor/carrot)");
  const out = await buildPreview(pos.map((s) => s.replace("/", ":")), pos[0].replace(/\W+/g, "-"));
  console.log(`PREVIEW ${out}`);
}

async function cmdBuild() {
  await import("./build.ts");
}

function cmdDoctor(flags: Record<string, string | boolean>) {
  const line = (ok: boolean | "info", label: string, detail = "") =>
    console.log(`  ${ok === "info" ? "•" : ok ? "✓" : "✗"} ${label}${detail ? ` — ${detail}` : ""}`);
  console.log(`icon-search doctor\n`);
  line(!!process.versions.bun, "bun runtime", process.versions.bun ? `bun ${process.versions.bun}` : "");
  line(process.env.GEMINI_API_KEY ? true : "info", "GEMINI_API_KEY", process.env.GEMINI_API_KEY ? "set" : "unset (fuzzy still works)");
  const hasManifest = existsSync(join(CATALOG, "manifest.json"));
  line(hasManifest, "catalog (search index)", hasManifest ? "" : "run `bun build.ts`");
  if (hasManifest) {
    const { sets } = loadManifest();
    const total = sets.reduce((n, s) => n + s.count, 0);
    sets.forEach((s) => line(existsSync(join(CATALOG, `${s.id}.search.json`)), `  ${s.id}`, `${s.count} icons (${s.license})`));
    const renderCount = readdirSync(CATALOG).filter((f) => f.endsWith(".render.json")).length;
    line(renderCount ? true : "info", "render data (preview)", renderCount ? `${renderCount} sets` : "run `bun build.ts` for preview");
    console.log(`\nRESULT: READY — ${total.toLocaleString()} icons across ${sets.length} sets`);
  } else {
    console.log(`\nRESULT: build the catalog first`);
  }
}

async function main() {
  const [cmd, ...rest] = process.argv.slice(2);
  const { flags, pos } = parseArgs(rest);
  try {
    switch (cmd) {
      case "search": await cmdSearch(flags, pos); break;
      case "preview": await cmdPreview(flags, pos); break;
      case "build": await cmdBuild(); break;
      case "doctor": cmdDoctor(flags); break;
      default:
        console.log(
          `icon-search — natural-language icon search across many sets\n\n` +
            `  search "<query>"   find icons; returns correct import + JSX per set\n` +
            `  preview <set/name> render icons to a PNG contact sheet\n` +
            `  build              (re)build catalog from installed source packages\n` +
            `  doctor             check runtime, key, catalog\n\n` +
            `flags: --set id[,id]  --project DIR  --limit N  --fuzzy  --semantic  --preview  --json\n` +
            `env:   GEMINI_API_KEY (semantic)  ICON_SEARCH_PROJECT (default project)`,
        );
    }
  } catch (e: any) {
    console.error(`error: ${e.message}`);
    process.exit(1);
  }
}

main();
