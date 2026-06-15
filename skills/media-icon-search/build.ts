#!/usr/bin/env bun
/**
 * Build the normalized icon catalog from the installed source packages.
 *
 *   bun build.ts            → writes catalog/<set>.json + catalog/manifest.json
 *
 * Run once after `bun install` (the catalog/ dir is a build artifact, gitignored).
 * Each catalog/<set>.json is IconRecord[]; manifest.json carries SetMeta + counts.
 */

import { mkdirSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { SOURCES } from "./sources.ts";
import { dedupeLower, type SetMeta } from "./lib.ts";

const SKILL_DIR = dirname(fileURLToPath(import.meta.url));
const OUT = join(SKILL_DIR, "catalog");
const ALTNAMES = join(SKILL_DIR, "altnames");

/** LLM-generated synonyms per icon (from the web app's enrichment) — folded into
 *  keywords so concept search works on the keyword-poor libraries (e.g. Heroicons). */
function loadAltnames(setId: string): Record<string, string[]> {
  const f = join(ALTNAMES, `${setId}.json`);
  return existsSync(f) ? JSON.parse(readFileSync(f, "utf8")) : {};
}

async function main() {
  if (!existsSync(OUT)) mkdirSync(OUT, { recursive: true });
  const manifest: { generatedAt: string; sets: SetMeta[] } = { generatedAt: new Date().toISOString(), sets: [] };
  let total = 0;

  for (const src of SOURCES) {
    const t0 = Date.now();
    let records;
    try {
      records = await src.build(SKILL_DIR);
    } catch (e: any) {
      console.error(`  ✗ ${src.meta.id} — build failed: ${e.message} (is its package installed?)`);
      continue;
    }
    // Fold LLM alt-names into each icon's keywords (search-recall boost).
    const alt = loadAltnames(src.meta.id);
    let enriched = 0;
    for (const r of records) {
      const a = alt[r.name];
      if (a?.length) { r.keywords = dedupeLower([...r.keywords, ...a]); enriched++; }
    }

    // Split: a small SEARCH index (committed, zero-setup) + heavy RENDER data
    // (gitignored build artifact, needed only for preview + the web box).
    const search = records.map((r) => ({
      name: r.name,
      component: r.component,
      keywords: r.keywords,
      category: r.category,
      styles: r.styles,
    }));
    const render = Object.fromEntries(records.map((r) => [r.name, { viewBox: r.viewBox, wrap: r.wrap, body: r.body }]));
    writeFileSync(join(OUT, `${src.meta.id}.search.json`), JSON.stringify(search));
    writeFileSync(join(OUT, `${src.meta.id}.render.json`), JSON.stringify(render));
    manifest.sets.push({ ...src.meta, count: records.length });
    total += records.length;
    console.error(`  ✓ ${src.meta.id.padEnd(10)} ${String(records.length).padStart(5)} icons  (+${enriched} alt-names, ${Date.now() - t0}ms)`);
  }

  writeFileSync(join(OUT, "manifest.json"), JSON.stringify(manifest, null, 2));
  console.error(`\ncatalog built: ${total} icons across ${manifest.sets.length} sets → ${OUT}`);
}

main();
