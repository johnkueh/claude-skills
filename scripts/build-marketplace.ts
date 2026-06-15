#!/usr/bin/env bun
/**
 * Regenerates `.claude-plugin/marketplace.json` and the `plugins/` symlink tree
 * from the canonical `skills/<name>/SKILL.md` folders.
 *
 * Produces:
 *   - one "claude-skills" bundle plugin (source "./") that ships every skill, and
 *   - one single-skill plugin per skill (source "./plugins/<name>").
 *
 * Why the symlink tree: a plugin only narrows to a single skill when its source
 * root contains a `skills/<name>/` dir holding just that skill. A per-plugin
 * `skills: [...]` array does NOT narrow a shared "./" source — it still
 * auto-discovers everything under the root `skills/`. So each single-skill plugin
 * gets its own root at `plugins/<name>/`, whose `skills/<name>` symlinks back to
 * the canonical `skills/<name>` (no file duplication).
 *
 * Skills are enumerated from `git ls-files`, so untracked work-in-progress skills
 * never leak into a published manifest until they're committed.
 *
 * Shared code: each skill dir must stay self-contained when shipped as a
 * single plugin, so cross-skill modules live canonically in `scripts/shared/`
 * and are SYNCED (copied with a generated-file header) into each consuming
 * skill dir by this script. Edit the canonical file, rerun this script, and
 * commit the synced copies alongside it.
 *
 * Usage:  bun scripts/build-marketplace.ts
 * Verify: claude plugin validate --strict .
 */
import { execFileSync } from "node:child_process";
import {
  mkdirSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { dirname, join } from "node:path";

const root = join(dirname(new URL(import.meta.url).pathname), "..");

const MARKETPLACE_NAME = "johnkueh-skills";
const OWNER = { name: "John Kueh", url: "https://github.com/johnkueh" };
const MARKETPLACE_DESCRIPTION =
  "John Kueh's Claude Code skills. Install the whole collection in one command, or add any single skill on its own.";
const BUNDLE_NAME = "claude-skills";
const BUNDLE_DESCRIPTION =
  "The full collection of John Kueh's Claude Code skills in one install: research (DataForSEO keyword/SERP, Reddit, YouTube transcripts), build & ship (Vercel logs, expo-local-build, InstantDB, daily digest, Cloudflare tunnel), copy & design (brand-copy, brand-design, gpt-image-gen-2, icon-search), comms (Notion, Slack, WhatsApp, X), voice (johns-writing-style), and macOS hygiene. Prefer a single skill? Each is also installable on its own — see the per-skill plugins in this marketplace.";

function frontmatterField(md: string, key: string): string {
  const block = md.match(/^---\n([\s\S]*?)\n---/);
  if (!block) throw new Error("missing frontmatter");
  const line = block[1].match(new RegExp(`^${key}:\\s*(.*)$`, "m"));
  if (!line) throw new Error(`missing "${key}" in frontmatter`);
  return line[1].trim().replace(/^["']|["']$/g, "");
}

// Sync canonical shared modules into their consuming skill dirs so each skill
// stays self-contained when distributed as a single plugin.
const SHARED_MODULES: Array<{ canonical: string; targets: string[] }> = [
  {
    canonical: "scripts/shared/dataforseo.py",
    targets: [
      "skills/keyword-data/dataforseo.py",
      "skills/serp-data/dataforseo.py",
    ],
  },
];

for (const { canonical, targets } of SHARED_MODULES) {
  const content = readFileSync(join(root, canonical), "utf8");
  const header =
    `# GENERATED FILE — synced from ${canonical} by scripts/build-marketplace.ts.\n` +
    `# Do not edit here: edit the canonical file, then run \`bun scripts/build-marketplace.ts\`.\n`;
  for (const target of targets) {
    writeFileSync(join(root, target), header + content);
  }
  console.log(`Synced ${canonical} -> ${targets.join(", ")}`);
}

// Committed skills only — keeps untracked WIP out of the published manifest.
const skillNames = execFileSync(
  "git",
  ["ls-files", "skills/*/SKILL.md"],
  { cwd: root, encoding: "utf8" },
)
  .trim()
  .split("\n")
  .filter(Boolean)
  .map((p) => p.split("/")[1])
  .sort();

if (skillNames.length === 0) throw new Error("no committed skills found");

// Rebuild the generated symlink tree from scratch.
const pluginsDir = join(root, "plugins");
rmSync(pluginsDir, { recursive: true, force: true });

const skillPlugins = skillNames.map((name) => {
  const md = readFileSync(join(root, "skills", name, "SKILL.md"), "utf8");
  const skillDir = join(pluginsDir, name, "skills");
  mkdirSync(skillDir, { recursive: true });
  symlinkSync(`../../../skills/${name}`, join(skillDir, name));
  return {
    name,
    description: frontmatterField(md, "description"),
    source: `./plugins/${name}`,
  };
});

const marketplace = {
  name: MARKETPLACE_NAME,
  owner: OWNER,
  metadata: { description: MARKETPLACE_DESCRIPTION },
  plugins: [
    { name: BUNDLE_NAME, description: BUNDLE_DESCRIPTION, source: "./" },
    ...skillPlugins,
  ],
};

writeFileSync(
  join(root, ".claude-plugin", "marketplace.json"),
  JSON.stringify(marketplace, null, 2) + "\n",
);

console.log(
  `Wrote marketplace.json: 1 bundle + ${skillPlugins.length} single-skill plugins`,
);
console.log(skillNames.join(", "));
