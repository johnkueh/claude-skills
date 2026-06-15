/**
 * Icon-selection advisor — the always-on footer that makes this more than a
 * string matcher. Rules distilled from NN/g, WCAG 2.2, Apple HIG. Returns ≤3
 * short lines relevant to the current query/results.
 */

import { humanize } from "./lib.ts";

/** glyphs whose metaphor is overloaded — flag + disambiguate with a label. */
const OVERLOADED: Record<string, string> = {
  heart: "love vs. save",
  star: "rating vs. favorite vs. featured",
  bookmark: "save vs. read-later",
  gear: "settings vs. profile/account",
  settings: "the gear is read as settings, not profile",
  share: "send vs. export vs. social",
  bell: "notifications vs. reminders",
  flag: "report vs. milestone vs. country",
  archive: "archive vs. delete vs. download",
  clock: "history vs. schedule vs. recent",
};

interface Ctx {
  results: Array<{ set: string; name: string }>;
  scopeSetCount: number;
  needsLabel?: boolean;
}

export function advise({ results, scopeSetCount, needsLabel }: Ctx): string[] {
  const out: string[] = [];
  const top = results.slice(0, 6).map((r) => humanize(r.name));

  // NN/g 5-second rule: abstract concepts have no shared metaphor.
  if (needsLabel)
    out.push("No strong universal metaphor here — only home, search, and print are near-universal (NN/g). Pair it with a text label or use a word.");

  // Overloaded glyph among the top picks.
  for (const [g, why] of Object.entries(OVERLOADED)) {
    if (top.some((n) => n.split(" ").includes(g))) {
      out.push(`"${g}" is overloaded (${why}) — add a label so users don't guess wrong (NN/g).`);
      break;
    }
  }

  // Consistency: results pulled from multiple families.
  const setsInTop = new Set(results.slice(0, 6).map((r) => r.set));
  if (scopeSetCount > 1 && setsInTop.size > 1)
    out.push("Results span multiple icon sets — pick one family and one stroke weight; mixing sets/weights reads as broken (designsystems.com).");

  // Always close with the accessibility floor.
  out.push("Any functional icon needs an aria-label, a ≥24px target (WCAG 2.5.8), and ≥3:1 contrast (WCAG 1.4.11).");

  return out.slice(0, 3);
}
