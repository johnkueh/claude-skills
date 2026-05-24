// wire-ingress.mjs — upsert one `<hostname> -> http://127.0.0.1:<port>` rule
// into a cloudflared config.yml, inside a managed BEGIN/END block, so the
// install server is reachable over the tunnel without portless/pubproxy.
//
//   node wire-ingress.mjs <config.yml> <hostname> <port>
//
// - If the `  # BEGIN expo-local-build` ... `  # END expo-local-build` block
//   exists, parses its `- hostname:` / `service: http://127.0.0.1:N` pairs,
//   replaces the entry for <hostname> (or adds it), keeps the others, rewrites
//   the whole block.
// - If no block exists, inserts a fresh one immediately before the catch-all
//   `- service: http_status:404` line (else after `ingress:`, else at EOF).
// - Writes atomically (temp file + rename); leaves a one-time .bak.
// Exit 0 on success (changed or already correct), 2 on usage / missing file.

import { readFileSync, writeFileSync, existsSync, renameSync, copyFileSync } from "node:fs";

const [cfgPath, host, portRaw] = process.argv.slice(2);
if (!cfgPath || !host || !portRaw) { console.error("usage: wire-ingress.mjs <config.yml> <hostname> <port>"); process.exit(2); }
const port = String(parseInt(portRaw, 10));
if (!/^\d+$/.test(port)) { console.error("port must be numeric"); process.exit(2); }
if (!existsSync(cfgPath)) { console.error(`no config file at ${cfgPath}`); process.exit(2); }

const BEGIN = "  # BEGIN expo-local-build";
const END = "  # END expo-local-build";

const src = readFileSync(cfgPath, "utf8");
const lines = src.split("\n");
const bi = lines.findIndex((l) => l.trim() === BEGIN.trim());
const ei = lines.findIndex((l) => l.trim() === END.trim());
const hadBlock = bi >= 0 && ei > bi;

// existing managed host -> port pairs (preserve order)
const pairs = new Map();
if (hadBlock) {
  let curHost = null;
  for (let i = bi + 1; i < ei; i++) {
    const m1 = lines[i].match(/^\s*-\s*hostname:\s*(\S+)/);
    const m2 = lines[i].match(/^\s*service:\s*http:\/\/127\.0\.0\.1:(\d+)/);
    if (m1) curHost = m1[1];
    else if (m2 && curHost) { pairs.set(curHost, m2[1]); curHost = null; }
  }
}
pairs.set(host, port);

const block = [
  BEGIN,
  "  # Managed by the expo-local-build skill's deliver.sh — <label>-localbuild",
  "  # hosts -> their install-server ports. Don't hand-edit between the markers.",
];
for (const [h, p] of pairs) block.push(`  - hostname: ${h}`, `    service: http://127.0.0.1:${p}`);
block.push(END);

let out;
if (hadBlock) {
  out = [...lines.slice(0, bi), ...block, ...lines.slice(ei + 1)].join("\n");
} else {
  let idx = lines.findIndex((l) => /^\s*-\s*service:\s*http_status:\d+\b/.test(l));
  if (idx < 0) { const ig = lines.findIndex((l) => /^\s*ingress:\s*$/.test(l)); idx = ig < 0 ? lines.length : ig + 1; }
  out = [...lines.slice(0, idx), ...block, "", ...lines.slice(idx)].join("\n");
}

if (out === src) { console.log(`wire-ingress: ${host} -> :${port} already present`); process.exit(0); }
const bak = cfgPath + ".bak";
if (!existsSync(bak)) { try { copyFileSync(cfgPath, bak); } catch {} }
const tmp = `${cfgPath}.tmp.${process.pid}`;
writeFileSync(tmp, out);
renameSync(tmp, cfgPath);
console.log(`wire-ingress: set ${host} -> http://127.0.0.1:${port} in ${cfgPath}`);
