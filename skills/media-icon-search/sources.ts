/**
 * Icon-set source modules. Each set = a builder (its own package → IconRecord[])
 * + an emitter (record → correct React import). Add a set: write one SetSource,
 * push it to SOURCES. The runtime never changes.
 *
 * Layouts verified against the installed packages (2026-05-31):
 *   lucide-static        icons/<name>.svg + icon-nodes.json + tags.json   24×24 stroke
 *   @phosphor-icons/core assets/<weight>/<name>[-weight].svg + dist icons[] 256×256 fill
 *   @tabler/icons        icons/<style>/<name>.svg + icons.json            24×24 stroke (+filled)
 *   heroicons            <size>/<style>/<name>.svg (no metadata)          24/20/16
 *   @hugeicons/core-free-icons  dist/esm/<Name>.js tuple arrays           24×24 stroke
 */

import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import {
  type IconRecord,
  type SetSource,
  toPascal,
  dedupeLower,
  extractViewBox,
  innerSvg,
  nodesToSvg,
} from "./lib.ts";

const STROKE = (w: number) => ({
  fill: "none",
  stroke: "currentColor",
  "stroke-width": w,
  "stroke-linecap": "round",
  "stroke-linejoin": "round",
});
const FILL = { fill: "currentColor" };

const listSvgs = (dir: string): string[] =>
  existsSync(dir) ? readdirSync(dir).filter((f) => f.endsWith(".svg")).map((f) => f.slice(0, -4)) : [];

// ───────────────────────────────────────────────────────────── lucide

const lucide: SetSource = {
  meta: {
    id: "lucide",
    label: "Lucide",
    license: "ISC",
    reactPackage: "lucide-react",
    detectPackages: ["lucide-react", "lucide-react-native", "lucide-static", "lucide"],
    defaultStyle: "default",
  },
  async build(root) {
    const base = join(root, "node_modules", "lucide-static");
    const nodes = JSON.parse(readFileSync(join(base, "icon-nodes.json"), "utf8")) as Record<string, any[]>;
    const tags = JSON.parse(readFileSync(join(base, "tags.json"), "utf8")) as Record<string, string[]>;
    return Object.entries(nodes).map(([name, n]) => ({
      name,
      viewBox: "0 0 24 24",
      wrap: STROKE(2),
      body: nodesToSvg(n as any),
      keywords: dedupeLower([...(tags[name] ?? []), ...name.split("-")]),
      styles: ["default"],
    }));
  },
  emit(rec) {
    const c = toPascal(rec.name);
    return { imports: [`import { ${c} } from 'lucide-react';`], usage: `<${c} size={24} />` };
  },
};

// ──────────────────────────────────────────────────────────── phosphor

const PH_WEIGHTS = ["regular", "thin", "light", "bold", "fill", "duotone"];

const phosphor: SetSource = {
  meta: {
    id: "phosphor",
    label: "Phosphor",
    license: "MIT",
    reactPackage: "@phosphor-icons/react",
    detectPackages: ["@phosphor-icons/react", "@phosphor-icons/core", "phosphor-react"],
    defaultStyle: "regular",
  },
  async build(root) {
    const base = join(root, "node_modules", "@phosphor-icons", "core");
    const mod: any = await import(pathToFileURL(join(base, "dist", "index.mjs")).href);
    const meta: any[] = mod.icons ?? [];
    const out: IconRecord[] = [];
    for (const it of meta) {
      const file = join(base, "assets", "regular", `${it.name}.svg`);
      if (!existsSync(file)) continue;
      const svg = readFileSync(file, "utf8");
      out.push({
        name: it.name,
        component: it.pascal_name,
        viewBox: extractViewBox(svg, "0 0 256 256"),
        wrap: FILL,
        body: innerSvg(svg),
        keywords: dedupeLower([...(it.tags ?? []), ...(it.categories ?? []), ...it.name.split("-")]),
        category: it.categories?.[0],
        styles: PH_WEIGHTS,
      });
    }
    return out;
  },
  emit(rec, style) {
    const c = rec.component ?? toPascal(rec.name);
    const w = style && style !== "regular" ? ` weight="${style}"` : "";
    return { imports: [`import { ${c} } from '@phosphor-icons/react';`], usage: `<${c} size={24}${w} />` };
  },
};

// ───────────────────────────────────────────────────────────── tabler

const TABLER_BBOX = /<path[^>]*d="M0 0h24v24H0z"[^>]*\/>/g;

const tabler: SetSource = {
  meta: {
    id: "tabler",
    label: "Tabler",
    license: "MIT",
    reactPackage: "@tabler/icons-react",
    detectPackages: ["@tabler/icons-react", "@tabler/icons"],
    defaultStyle: "outline",
  },
  async build(root) {
    const base = join(root, "node_modules", "@tabler", "icons");
    const meta = JSON.parse(readFileSync(join(base, "icons.json"), "utf8")) as Record<string, any>;
    const out: IconRecord[] = [];
    for (const [name, info] of Object.entries(meta)) {
      const file = join(base, "icons", "outline", `${name}.svg`);
      if (!existsSync(file)) continue;
      const svg = readFileSync(file, "utf8");
      const styles = Object.keys(info.styles ?? { outline: 1 });
      out.push({
        name,
        viewBox: "0 0 24 24",
        wrap: STROKE(2),
        body: innerSvg(svg).replace(TABLER_BBOX, "").trim(),
        keywords: dedupeLower([...(info.tags ?? []), info.category ?? "", ...name.split("-")]),
        category: info.category,
        styles: styles.includes("outline") ? styles : ["outline", ...styles],
      });
    }
    return out;
  },
  emit(rec, style) {
    const c = `Icon${toPascal(rec.name)}${style === "filled" ? "Filled" : ""}`;
    return { imports: [`import { ${c} } from '@tabler/icons-react';`], usage: `<${c} size={24} stroke={2} />` };
  },
};

// ──────────────────────────────────────────────────────────── heroicons

const heroicons: SetSource = {
  meta: {
    id: "heroicons",
    label: "Heroicons",
    license: "MIT",
    reactPackage: "@heroicons/react",
    detectPackages: ["@heroicons/react", "heroicons"],
    defaultStyle: "24/outline",
  },
  async build(root) {
    const base = join(root, "node_modules", "heroicons");
    const variants = ["24/outline", "24/solid", "20/solid", "16/solid"];
    const present: Record<string, Set<string>> = {};
    for (const v of variants) present[v] = new Set(listSvgs(join(base, ...v.split("/"))));
    return [...present["24/outline"]].map((name) => {
      const svg = readFileSync(join(base, "24", "outline", `${name}.svg`), "utf8");
      const styles = variants.filter((v) => present[v].has(name));
      return {
        name,
        viewBox: "0 0 24 24",
        wrap: STROKE(1.5),
        body: innerSvg(svg),
        keywords: dedupeLower(name.split("-")),
        styles,
      } satisfies IconRecord;
    });
  },
  emit(rec, style) {
    const c = `${toPascal(rec.name)}Icon`;
    return {
      imports: [`import { ${c} } from '@heroicons/react/${style || "24/outline"}';`],
      usage: `<${c} className="size-6" />`,
    };
  },
};

// ──────────────────────────────────────────────────────────── hugeicons

const hugeicons: SetSource = {
  meta: {
    id: "hugeicons",
    label: "HugeIcons",
    license: "MIT",
    reactPackage: "@hugeicons/react",
    detectPackages: ["@hugeicons/react", "@hugeicons/react-native", "@hugeicons/core-free-icons"],
    defaultStyle: "stroke",
  },
  async build(root) {
    const esm = join(root, "node_modules", "@hugeicons", "core-free-icons", "dist", "esm");
    const names = readdirSync(esm)
      .filter((f) => f.endsWith(".js") && !f.endsWith(".js.map") && f.endsWith("Icon.js"))
      .map((f) => f.slice(0, -3));
    const out: IconRecord[] = [];
    // limited-concurrency dynamic import of the tuple modules
    const CHUNK = 64;
    for (let i = 0; i < names.length; i += CHUNK) {
      const batch = await Promise.all(
        names.slice(i, i + CHUNK).map(async (name) => {
          const mod: any = await import(pathToFileURL(join(esm, `${name}.js`)).href);
          const tuples = mod.default ?? mod;
          return { name, body: nodesToSvg(tuples) };
        }),
      );
      for (const b of batch) {
        out.push({
          name: b.name,
          component: b.name,
          viewBox: "0 0 24 24",
          wrap: { fill: "none" },
          body: b.body,
          keywords: [], // name-only set
          styles: ["stroke"],
        });
      }
    }
    return out;
  },
  emit(rec) {
    const c = rec.component ?? rec.name;
    return {
      imports: [
        `import { HugeiconsIcon } from '@hugeicons/react';`,
        `import { ${c} } from '@hugeicons/core-free-icons';`,
      ],
      usage: `<HugeiconsIcon icon={${c}} size={24} strokeWidth={1.5} />`,
    };
  },
};

export const SOURCES: SetSource[] = [lucide, phosphor, tabler, heroicons, hugeicons];
export const SOURCE_BY_ID: Record<string, SetSource> = Object.fromEntries(SOURCES.map((s) => [s.meta.id, s]));
