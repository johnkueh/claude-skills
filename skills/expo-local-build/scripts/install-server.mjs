// install-server.mjs — serve locally-built Expo artifacts (.ipa / .apk) over
// the cloudflare-tunnel-portless chain so a phone on any network can install
// them. Generic / project-agnostic; configured entirely by env vars.
//
//   PROJECT_LABEL        required. e.g. "recipes-im". Public host becomes
//                        ${PROJECT_LABEL}-install.${TUNNEL_TLD} and the
//                        portless route is ${PROJECT_LABEL}-install.localhost.
//   ARTIFACT_DIR         required. Directory scanned (at request time) for
//                        canonical-slot filenames matching
//                        ^[a-z][a-z0-9]*-(ios|android)\.(ipa|apk)$
//                        — e.g. dev-ios.ipa, preview-ios.ipa, prod-android.apk.
//                        Anything else in the dir is ignored.
//   INSTALL_SERVER_PORT  default 1360.
//   TUNNEL_TLD           default "example.dev".
//
// Routes:
//   GET /                 install page: itms-services button per IPA, download link per APK
//   GET /healthz          "ok" (used by deliver.sh to detect a live server)
//   GET /manifest/<file>  Apple OTA manifest plist for that IPA
//   GET /dl/<file>        streams the artifact
//
// Registers itself in ~/.portless/routes.json on start, removes the entry on exit.

import { createServer } from "node:http";
import { createReadStream, existsSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { join, basename } from "node:path";
import { homedir } from "node:os";

const LABEL = (process.env.PROJECT_LABEL || "").trim();
const ARTIFACT_DIR = (process.env.ARTIFACT_DIR || "").trim();
const PORT = Number(process.env.INSTALL_SERVER_PORT || 1360);
const TLD = (process.env.TUNNEL_TLD || "example.dev").trim();
if (!LABEL) { console.error("install-server: PROJECT_LABEL is required"); process.exit(2); }
if (!ARTIFACT_DIR || !existsSync(ARTIFACT_DIR)) { console.error(`install-server: ARTIFACT_DIR missing or not found: ${ARTIFACT_DIR}`); process.exit(2); }

// PUBLIC_HOST is what goes in the install page's links / OTA manifest. deliver.sh
// passes the host it actually wired (portless `<label>-install.<tld>` or dedicated
// ingress `<label>-localbuild.<tld>`); fall back to the portless form if unset.
const PUBLIC_HOST = (process.env.PUBLIC_HOST || `${LABEL}-install.${TLD}`).trim();
const PORTLESS_HOST = `${LABEL}-install.localhost`;
const ROUTES_FILE = join(homedir(), ".portless", "routes.json");

// ---- artifact discovery -----------------------------------------------------
// Only filenames matching `<profile>-<platform>.<ext>` are shown. Each slot is
// a single canonical filename — the build is expected to overwrite in place
// (set `--output build-output/<slot>.<ext>` on the eas build command). No
// timestamps, no symlinks, no historical noise.
const SLOT = /^([a-z][a-z0-9]*)-(ios|android)\.(ipa|apk)$/;
function listArtifacts() {
  const out = [];
  for (const name of readdirSync(ARTIFACT_DIR)) {
    const m = name.match(SLOT);
    if (!m) continue;
    const path = join(ARTIFACT_DIR, name);
    let st; try { st = statSync(path); } catch { continue; }
    if (!st.isFile()) continue;
    out.push({
      name, path,
      kind: m[3],                              // "ipa" | "apk"
      profile: m[1].toLowerCase(),             // "dev" | "preview" | "prod" | …
      platform: m[2].toLowerCase(),            // "ios" | "android"
      variant: `${m[1].toLowerCase()}-${m[2].toLowerCase()}`,
      mtimeMs: st.mtimeMs,
      size: st.size,
    });
  }
  return out;
}

// ---- IPA metadata (bundle id / version / display name) ----------------------
const ipaMetaCache = new Map();
function ipaMeta(ipaPath) {
  const c = ipaMetaCache.get(ipaPath);
  if (c) return c;
  let xml = "";
  try {
    // unzip -> binary plist -> xml so we can regex it without a plist parser
    const sh = `unzip -p ${JSON.stringify(ipaPath)} 'Payload/*.app/Info.plist' | plutil -convert xml1 -o - -`;
    xml = execFileSync("/bin/sh", ["-c", sh], { encoding: "utf8", maxBuffer: 8 * 1024 * 1024 });
  } catch (e) {
    console.warn("install-server: could not read Info.plist of", basename(ipaPath), "-", e?.message);
  }
  const pick = (k) => { const m = xml.match(new RegExp(`<key>${k}</key>\\s*<string>([^<]*)</string>`)); return m ? m[1] : null; };
  const meta = {
    bundleId: pick("CFBundleIdentifier") || "com.unknown.app",
    bundleVersion: pick("CFBundleShortVersionString") || "1.0.0",
    title: pick("CFBundleDisplayName") || pick("CFBundleName") || LABEL,
  };
  ipaMetaCache.set(ipaPath, meta);
  return meta;
}

// ---- HTML / plist -----------------------------------------------------------
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const mb = (bytes) => (bytes / 1024 / 1024).toFixed(1);

function manifestPlist(meta, ipaName) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>items</key><array><dict>
  <key>assets</key><array><dict>
    <key>kind</key><string>software-package</string>
    <key>url</key><string>https://${PUBLIC_HOST}/dl/${encodeURIComponent(ipaName)}</string>
  </dict></array>
  <key>metadata</key><dict>
    <key>bundle-identifier</key><string>${esc(meta.bundleId)}</string>
    <key>bundle-version</key><string>${esc(meta.bundleVersion)}</string>
    <key>kind</key><string>software</string>
    <key>title</key><string>${esc(meta.title)}</string>
  </dict>
</dict></array></dict></plist>
`;
}

function page(artifacts) {
  // Stable ordering across renders: prod → preview → dev → others; iOS before Android.
  const PROFILE_ORDER = { prod: 0, preview: 1, dev: 2 };
  const PLAT_ORDER = { ios: 0, android: 1 };
  const variantSort = (a, b) =>
       (PROFILE_ORDER[a.profile] ?? 9) - (PROFILE_ORDER[b.profile] ?? 9)
    || (PLAT_ORDER[a.platform]   ?? 9) - (PLAT_ORDER[b.platform]   ?? 9);
  const rows = [...artifacts].sort(variantSort).map((a) => {
    const built = new Date(a.mtimeMs).toLocaleString();
    const profileBadge = `<span class="badge profile ${a.profile}">${esc(a.profile)}</span>`;
    if (a.kind === "ipa") {
      const m = ipaMeta(a.path);
      const manifestUrl = encodeURIComponent(`https://${PUBLIC_HOST}/manifest/${encodeURIComponent(a.name)}`);
      return `<div class="card">
        <div class="t">${esc(m.title)} <span class="badge ios">iOS</span>${profileBadge}</div>
        <div class="meta">${esc(a.name)} · ${esc(m.bundleId)} · v${esc(m.bundleVersion)} · ${mb(a.size)} MB · ${esc(built)}</div>
        <a class="button" href="itms-services://?action=download-manifest&amp;url=${manifestUrl}">Install</a>
      </div>`;
    }
    return `<div class="card">
      <div class="t">${esc(a.name)} <span class="badge android">Android</span>${profileBadge}</div>
      <div class="meta">${mb(a.size)} MB · ${esc(built)}</div>
      <a class="button android" href="/dl/${encodeURIComponent(a.name)}">Download APK</a>
    </div>`;
  }).join("\n");
  return `<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Install — ${esc(LABEL)}</title>
<style>
:root{color-scheme:light dark}
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:560px;margin:0 auto;padding:28px 18px;line-height:1.45}
h1{font-size:20px;margin:0 0 18px}
.card{padding:14px 16px;border-radius:14px;background:rgba(127,127,127,.10);margin-bottom:14px}
.t{font-weight:600;font-size:16px;margin-bottom:4px}
.meta{color:#888;font-size:12.5px;margin-bottom:12px;word-break:break-all}
.badge{font-size:11px;font-weight:600;padding:1px 7px;border-radius:999px;vertical-align:middle}
.badge.ios{background:#0A84FF22;color:#0A84FF}.badge.android{background:#3DDC8422;color:#1a9d5e}
.badge.profile{margin-left:6px;text-transform:uppercase;letter-spacing:.04em}
.badge.profile.prod{background:#FF950022;color:#c87100}.badge.profile.preview{background:#0A84FF22;color:#0A84FF}.badge.profile.dev{background:#8E8E9322;color:#666}
a.button{display:block;text-align:center;padding:14px;border-radius:11px;font-weight:600;text-decoration:none;font-size:16px;background:#0A84FF;color:#fff}
a.button.android{background:#1a9d5e}
.note{margin-top:18px;padding:11px 14px;background:rgba(127,127,127,.10);border-radius:10px;font-size:12.5px;color:#777}
.empty{color:#888}
@media(prefers-color-scheme:dark){body{background:#000;color:#eee}}
</style></head><body>
<h1>Install — ${esc(LABEL)}</h1>
${rows || `<p class="empty">No builds in this dir yet. Build one with <code>pnpm build:dev:local</code> (or whichever <code>:local</code> slot you want), then re-open this page.</p>`}
<div class="note">
iOS: the install only works if this device's UDID is in the EAS provisioning profile (run <code>eas device:create</code> then rebuild if it fails). After installing, trust the cert at Settings → General → VPN &amp; Device Management.<br>
Android: enable "Install unknown apps" for your browser if prompted.<br>
Served from this Mac over the Cloudflare tunnel — if the page 502s, the tunnel/Mac is down.
</div>
</body></html>
`;
}

// ---- portless route registration -------------------------------------------
function readRoutes() { try { return JSON.parse(readFileSync(ROUTES_FILE, "utf8")); } catch { return []; } }
function setRoute() {
  const routes = readRoutes().filter((r) => r.hostname !== PORTLESS_HOST);
  routes.push({ hostname: PORTLESS_HOST, port: PORT, pid: process.pid });
  try { writeFileSync(ROUTES_FILE, JSON.stringify(routes, null, 2)); console.log(`install-server: registered ${PORTLESS_HOST} → 127.0.0.1:${PORT}`); }
  catch (e) { console.warn("install-server: could not write routes.json -", e?.message); }
}
function clearRoute() {
  try { writeFileSync(ROUTES_FILE, JSON.stringify(readRoutes().filter((r) => r.hostname !== PORTLESS_HOST), null, 2)); } catch {}
}

// ---- server -----------------------------------------------------------------
function findArtifact(name) {
  // name is decodeURIComponent'd; only allow plain basenames inside ARTIFACT_DIR
  const safe = basename(name);
  if (safe !== name) return null;
  const p = join(ARTIFACT_DIR, safe);
  if (!existsSync(p)) return null;
  return p;
}

// install pages / manifests must never be cached (Safari + Cloudflare both will,
// otherwise — and then a freshly-published build doesn't show up on the phone).
const NOCACHE = { "cache-control": "no-store, no-cache, must-revalidate", "pragma": "no-cache" };

const server = createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || "localhost"}`);
  const path = decodeURIComponent(url.pathname);
  try {
    if (path === "/healthz") { res.writeHead(200, { "content-type": "text/plain", ...NOCACHE }); return res.end("ok"); }
    if (path === "/whoami") { res.writeHead(200, { "content-type": "application/json", ...NOCACHE }); return res.end(JSON.stringify({ label: LABEL, port: PORT, publicHost: PUBLIC_HOST, artifactDir: ARTIFACT_DIR })); }
    // `/`, `/install`, `/i` all render the install page. (The aliases are an
    // escape hatch when a phone has cached a stale `/` — a never-visited path
    // can't be served from cache.)
    if (path === "/" || path === "" || path === "/install" || path === "/i") {
      const html = page(listArtifacts());
      res.writeHead(200, { "content-type": "text/html; charset=utf-8", ...NOCACHE }); return res.end(html);
    }
    if (path.startsWith("/manifest/")) {
      const name = path.slice("/manifest/".length);
      const p = findArtifact(name);
      if (!p || !p.endsWith(".ipa")) { res.writeHead(404); return res.end("not found"); }
      res.writeHead(200, { "content-type": "application/xml", ...NOCACHE }); return res.end(manifestPlist(ipaMeta(p), name));
    }
    if (path.startsWith("/dl/")) {
      const name = path.slice("/dl/".length);
      const p = findArtifact(name);
      if (!p) { res.writeHead(404); return res.end("not found"); }
      const st = statSync(p);
      const type = p.endsWith(".ipa")
        ? "application/octet-stream"
        : "application/vnd.android.package-archive";
      const baseHdrs = {
        "content-type": type,
        "accept-ranges": "bytes",                       // iOS's OTA installer requires this
        "content-disposition": `attachment; filename="${name}"`,
      };
      // HEAD: iOS probes with HEAD before downloading
      if (req.method === "HEAD") { res.writeHead(200, { ...baseHdrs, "content-length": st.size }); return res.end(); }
      // Range: iOS downloads the IPA with byte-range requests — must answer 206.
      const range = req.headers.range;
      const m = range && /^bytes=(\d*)-(\d*)$/.exec(range.trim());
      if (m) {
        let start = m[1] === "" ? null : parseInt(m[1], 10);
        let end = m[2] === "" ? null : parseInt(m[2], 10);
        if (start === null) { start = st.size - (end ?? 0); end = st.size - 1; }    // suffix range
        else if (end === null || end >= st.size) { end = st.size - 1; }
        if (start > end || start < 0) { res.writeHead(416, { "content-range": `bytes */${st.size}` }); return res.end(); }
        res.writeHead(206, { ...baseHdrs, "content-range": `bytes ${start}-${end}/${st.size}`, "content-length": end - start + 1 });
        return createReadStream(p, { start, end }).pipe(res);
      }
      res.writeHead(200, { ...baseHdrs, "content-length": st.size });
      return createReadStream(p).pipe(res);
    }
    res.writeHead(404, { "content-type": "text/plain" }); res.end("not found");
  } catch (e) {
    console.error("install-server: request error -", e?.message);
    if (!res.headersSent) res.writeHead(500);
    res.end("error");
  }
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`install-server: ${LABEL} listening on 127.0.0.1:${PORT}`);
  console.log(`install-server: public URL  https://${PUBLIC_HOST}/`);
  console.log(`install-server: serving from ${ARTIFACT_DIR}`);
  setRoute();
});

function shutdown(sig) { console.log(`install-server: ${sig} — cleaning up`); clearRoute(); server.close(() => process.exit(0)); setTimeout(() => process.exit(0), 1000); }
process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("exit", clearRoute);
