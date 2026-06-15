/**
 * Shared types + helpers for the icon-search catalog.
 *
 * The catalog is the heart of the multi-set design: each icon set has a
 * BUILDER (reads its own npm package → normalized IconRecord[]) and an EMITTER
 * (turns a record into the correct React import + JSX for that package). The
 * runtime (search/preview) is set-agnostic and only ever sees IconRecord +
 * SetMeta — so adding set #N is one source module, nothing else.
 *
 * Every IconRecord is also the data a programmatic-SEO page needs
 * (slug, set, keywords, body SVG, license) — built once, reused by the agent
 * skill, the web search box, and the per-icon landing pages.
 */

// ─────────────────────────────────────────────────────────── types

/** Normalized, render-ready icon. One per icon per set. */
export interface IconRecord {
  name: string; // canonical name within the set (kebab, or PascalIcon for hugeicons)
  /** exact React component base when the set provides it (phosphor pascal_name, hugeicons) */
  component?: string;
  viewBox: string; // e.g. "0 0 24 24"
  /** presentation attrs applied to the enclosing <g> when rendering (stroke/fill/width…) */
  wrap: Record<string, string | number>;
  body: string; // inner SVG markup (no <svg> wrapper), currentColor-based
  keywords: string[]; // native tags + category tokens, lowercased + deduped
  category?: string;
  styles: string[]; // available styles/weights; styles[0] is the default
}

/** Set-level metadata + emitter config. Lives in catalog/manifest.json. */
export interface SetMeta {
  id: string; // "lucide"
  label: string; // "Lucide"
  license: string; // SPDX, e.g. "ISC"
  attribution?: string; // required attribution note (e.g. Font Awesome CC-BY)
  reactPackage: string; // the package devs import the component from
  /** packages whose presence in a project means this set is installed */
  detectPackages: string[];
  defaultStyle: string;
  count: number;
}

/** A buildable set: metadata + a builder that reads node_modules. */
export interface SetSource {
  meta: Omit<SetMeta, "count">;
  /** read this set's package from `pkgRoot/node_modules` → normalized records */
  build(pkgRoot: string): Promise<IconRecord[]>;
  /** render a record into the correct React import lines + JSX usage */
  emit(rec: IconRecord, style: string): { imports: string[]; usage: string };
}

// ──────────────────────────────────────────────────────── string helpers

/** "arrow-right" → "ArrowRight"; "1-circle" → "1Circle" (caller adds affixes). */
export function toPascal(kebab: string): string {
  return kebab
    .split(/[-_]/)
    .filter(Boolean)
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join("");
}

/** "arrow-right" / "ArrowRight01Icon" → "arrow right 01" for display + search. */
export function humanize(name: string): string {
  return name
    .replace(/Icon$/, "")
    .replace(/[-_]/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/([A-Za-z])(\d)/g, "$1 $2")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2")
    .trim()
    .toLowerCase();
}

export const dedupeLower = (xs: Array<string | number>): string[] =>
  [...new Set(xs.map((s) => String(s).toLowerCase().trim()).filter(Boolean))];

// ──────────────────────────────────────────────────────────── svg helpers

const camelToKebab = (k: string) => k.replace(/[A-Z]/g, (m) => "-" + m.toLowerCase());

/** extract viewBox from a full <svg> string (fallback to a default canvas). */
export function extractViewBox(svg: string, fallback = "0 0 24 24"): string {
  return svg.match(/viewBox="([^"]+)"/)?.[1] ?? fallback;
}

/** strip the <svg> wrapper + XML comments → inner markup only. */
export function innerSvg(svg: string): string {
  return svg
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/^[\s\S]*?<svg[^>]*>/, "")
    .replace(/<\/svg>\s*$/, "")
    .trim();
}

/** serialize a lucide/hugeicons [tag, attrs] node array → SVG string. */
export function nodesToSvg(nodes: ReadonlyArray<readonly [string, Record<string, any>]>): string {
  return nodes
    .map(([tag, attrs]) => {
      const parts = Object.entries(attrs)
        .filter(([k]) => k !== "key")
        .map(([k, v]) => `${camelToKebab(k)}="${v}"`);
      return `<${tag} ${parts.join(" ")} />`;
    })
    .join("");
}

/** serialize a wrap-attrs object for an SVG <g>. */
export function wrapAttrs(wrap: Record<string, string | number>): string {
  return Object.entries(wrap)
    .map(([k, v]) => `${k}="${v}"`)
    .join(" ");
}
