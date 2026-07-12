#!/usr/bin/env bun
/**
 * reddit-miner: pull structured data from Reddit through a headless browser.
 *
 * Reddit hard-blocks the public `.json` API for datacenter/cloud IPs and serves
 * a JS bot-challenge to anything automated. The decisive signal is the
 * `HeadlessChrome` token in the User-Agent — override it to a clean `Chrome/...`
 * string and headless Chrome passes the challenge; the same-origin `fetch()`
 * then carries the clearance cookie and returns real JSON.
 *
 * Drives `agent-browser` (headless) through a residential proxy with a clean UA,
 * clears the challenge once per run, then fetches `.json` via in-page `fetch()`,
 * metering real wire bytes (proxy bandwidth) and cost. Question/cluster NLP is
 * ported in-tool, so there is no Python dependency.
 *
 * Commands:
 *   reddit-miner setup   [--proxy <url>] [--usd-per-gb <rate>]
 *   reddit-miner doctor
 *   reddit-miner posts   --subreddit <s> [--sort top|hot|new|rising] [--time month] [--limit 30]
 *   reddit-miner thread  --url <permalink> [--limit 500]
 *   reddit-miner mine    --subreddit <s> [--time month] [--threads 30] [--topic-keywords <re>]
 *
 * Credential resolution: --proxy flag, REDDIT_PROXY env, then the machine-local
 * config (~/.config/reddit-miner/config.json). The proxy secret is NEVER read
 * from or written to the skill repo (which is public).
 *
 * Env: REDDIT_PROXY, REDDIT_MINER_UA, REDDIT_PROXY_USD_PER_GB
 *
 * Bandwidth rate resolution: REDDIT_PROXY_USD_PER_GB env, then config
 * `usd_per_gb` (`setup --usd-per-gb <rate>`), then the $8/GB default. Providers
 * differ by ~8x, so the printed cost is only as good as this rate.
 */
import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

const CLEAN_UA =
  process.env.REDDIT_MINER_UA ??
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36";
const USD_PER_GB_DEFAULT = 8;
const CONFIG_PATH = path.join(os.homedir(), ".config", "reddit-miner", "config.json");
const SESSION = "reddit-miner";
const BLOCK_MARKER = "blocked by network security";

// ----------------------------- NLP: question detection + clustering -----------------------------

const QWORDS =
  /^\s*(what|how|when|why|where|which|who|does|do|is|are|was|were|be|been|being|can|should|would|will|has|have|did|any|anyone|anybody)\b/i;
const URL_RX = /https?:\/\/\S+|\bwww\.\S+|\[[^\]]+\]\([^)]+\)/g;
const SNARK_RX =
  /\b(ever stop|are you kidding|are you serious|seriously\?|wtf|lol|lmao|🤣|😂)\b/i;
const STOPWORDS = new Set(
  (
    "a an the of for on in to with from at by is are was were be been being " +
    "have has had do does did will would can could should may might must shall need ought " +
    "i you he she it we they me him her us them my your his its our their " +
    "this that these those there where when how what why which who whom whose " +
    "and or but if then so as than not no yes do dont don cant won wont about into over under out up down off yeah ya hey lol u ok okay " +
    "get got getting gets give gives gave giving go goes going went gone come comes came coming " +
    "know knew known knows think thinks thought thinking want wants wanted wanting need needs needed " +
    "use uses used using make makes made making take takes took taken taking " +
    "see sees saw seen seeing say says said saying tell tells told telling ask asks asked asking " +
    "try tries tried trying find finds found finding work works worked working " +
    "feel feels felt thing things stuff way ways one two many much lot lots really very just also even still always never " +
    "guy guys people person someone anybody anyone everybody everyone friend friends " +
    "today yesterday tomorrow day days week weeks month months year years time times " +
    "good great bad better best worse worst nice fine ok okay sure right wrong same different " +
    "help helps helped helping please thanks thank "
  ).split(/\s+/),
);

function cleanText(s: string): string {
  if (!s) return "";
  return s.replace(URL_RX, " ").replace(/&amp;/g, "&").replace(/\s+/g, " ").trim();
}

function isQuestion(body: string, topicRx: RegExp | null): boolean {
  if (!body || !body.includes("?")) return false;
  if (body.length < 20 || body.length > 400) return false;
  if (!QWORDS.test(body)) return false;
  if (topicRx && !topicRx.test(body)) return false;
  return true;
}

function extractQuestion(body: string): string | null {
  body = cleanText(body);
  if (!body) return null;
  if (SNARK_RX.test(body)) return null;
  const m = body.match(/([^.?!]{5,300}\?)/);
  if (!m) return null;
  let q = m[1].trim().replace(/^(and|but|so|also|oh|hey|hi)[, ]+/i, "").trim();
  if (!QWORDS.test(q)) return null;
  const tokens = q.match(/[A-Za-z'][A-Za-z']*/g) ?? [];
  if (tokens.length < 4 || tokens.length > 25) return null;
  return q;
}

function answered(replyBodies: string[]): boolean {
  for (let r of replyBodies) {
    r = (r ?? "").trim();
    if (r.length < 40) continue;
    if (r.endsWith("?")) continue;
    if (["idk", "dunno", "same", "this", "yes", "no"].includes(r.toLowerCase())) continue;
    return true;
  }
  return false;
}

function contentTokens(qText: string): string[] {
  const toks = (qText.match(/[A-Za-z][A-Za-z']{2,}/g) ?? []).map((t) => t.toLowerCase());
  return toks.filter((t) => !STOPWORDS.has(t) && !QWORDS.test(t));
}

interface Q {
  q: string; score: number; answered: boolean; n_replies: number;
  source: string; thread_title: string; permalink: string;
}

function cluster(qs: Q[], topN = 10) {
  if (!qs.length) return [];
  const df = new Map<string, number>();
  for (const q of qs) for (const t of new Set(contentTokens(q.q))) df.set(t, (df.get(t) ?? 0) + 1);
  const N = qs.length;
  const rarity = (t: string) => -Math.log(((df.get(t) ?? 0) + 1) / (N + 1));

  const buckets = new Map<string, { key: string[]; items: Q[] }>();
  const put = (key: string[], q: Q) => {
    const id = key.join("\u001f");
    if (!buckets.has(id)) buckets.set(id, { key, items: [] });
    buckets.get(id)!.items.push(q);
  };
  for (const q of qs) {
    const toks = contentTokens(q.q).filter((t) => (df.get(t) ?? 0) >= 2);
    if (!toks.length) { put(["_singleton", q.q.slice(0, 40).toLowerCase()], q); continue; }
    const ranked = [...new Set(toks)].sort((a, b) => rarity(b) - rarity(a) || (a < b ? -1 : 1));
    put(ranked.length >= 2 ? [ranked[0], ranked[1]].sort() : [ranked[0]], q);
  }
  // promote 2-token singleton buckets down to 1-token keys
  const merged = new Map<string, { key: string[]; items: Q[] }>();
  const mput = (key: string[], items: Q[]) => {
    const id = key.join("\u001f");
    if (!merged.has(id)) merged.set(id, { key, items: [] });
    merged.get(id)!.items.push(...items);
  };
  for (const { key, items } of buckets.values()) {
    if (key[0] === "_singleton") mput(key, items);
    else if (items.length === 1 && key.length === 2) mput([key[0]], items);
    else mput(key, items);
  }
  const out = [];
  for (const { key, items } of merged.values()) {
    if (key[0] === "_singleton") continue;
    items.sort((a, b) => b.score - a.score);
    out.push({
      key: key.join(" + "), count: items.length, top_score: items[0].score,
      sample: items[0].q, permalink: items[0].permalink,
      examples: items.slice(0, 3).map((it) => ({ q: it.q, score: it.score, permalink: it.permalink })),
    });
  }
  out.sort((a, b) => b.count - a.count || b.top_score - a.top_score);
  return out.slice(0, topN);
}

// ----------------------------- credential resolution (repo-safe) -----------------------------

function loadConfig(): Record<string, any> {
  try { return JSON.parse(fs.readFileSync(CONFIG_PATH, "utf8")); } catch { return {}; }
}
function resolveProxy(flag?: string): [string | null, string | null] {
  if (flag) return [flag, "flag"];
  if (process.env.REDDIT_PROXY) return [process.env.REDDIT_PROXY, "env"];
  const cfg = loadConfig();
  if (cfg.proxy) return [cfg.proxy, `config (${CONFIG_PATH})`];
  return [null, null];
}
const mask = (p: string | null) => (p ?? "").replace(/(\/\/[^:]+:)[^@]+(@)/, "$1***$2");

function resolveUsdPerGb(): number {
  const env = parseFloat(process.env.REDDIT_PROXY_USD_PER_GB ?? "");
  if (Number.isFinite(env) && env > 0) return env;
  const cfg = parseFloat(String(loadConfig().usd_per_gb ?? ""));
  if (Number.isFinite(cfg) && cfg > 0) return cfg;
  return USD_PER_GB_DEFAULT;
}

// Sticky proxy sessions (Oxylabs `sessid-…`) expire (~10 min) and then fail with
// SSL/connection errors mid-run. If the proxy URL carries a sessid, mint a FRESH one
// per process run — stable within the run (same exit IP → clearance cookie holds),
// fresh across runs so an unattended cron never inherits a dead session. Stored
// config is untouched; only the runtime value rotates.
const RUN_SESSID = `rm${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
function rotateSessid(proxy: string | null): string | null {
  if (!proxy) return proxy;
  return proxy.replace(/sessid-[^-:@/]+/i, `sessid-${RUN_SESSID}`);
}

// ----------------------------- headless browser -----------------------------

class BrowserError extends Error {}

function runAgentBrowser(args: string[], input: string | undefined, timeoutMs: number): { out: string; timedOut: boolean } {
  const tmp = path.join(os.tmpdir(), `reddit-miner-ab-${process.pid}-${Math.random().toString(36).slice(2)}.out`);
  const fd = fs.openSync(tmp, "w");
  let timedOut = false;
  try {
    execFileSync("agent-browser", args, {
      input, stdio: [input !== undefined ? "pipe" : "ignore", fd, fd], timeout: timeoutMs,
    });
  } catch (e: any) {
    if (e?.code === "ETIMEDOUT" || e?.killed === true || e?.signal === "SIGTERM") timedOut = true;
  } finally {
    try { fs.closeSync(fd); } catch {}
  }
  let out = "";
  try { out = fs.readFileSync(tmp, "utf8"); } catch {}
  try { fs.unlinkSync(tmp); } catch {}
  return { out, timedOut };
}

class RedditBrowser {
  proxy: string | null; session: string; ua: string; verbose: boolean;
  wireBytes = 0; decodedBytes = 0; requests = 0; private launched = false; private timeouts = 0;
  constructor(proxy: string | null, session = SESSION, ua = CLEAN_UA, verbose = true) {
    this.proxy = proxy; this.session = session; this.ua = ua; this.verbose = verbose;
    if (!process.env.AGENT_BROWSER_MAX_OUTPUT) process.env.AGENT_BROWSER_MAX_OUTPUT = "8000000";
  }
  private log(...a: any[]) { if (this.verbose) console.error(...a); }
  private ab(args: string[], stdin?: string, timeoutMs = 90_000): string {
    // --proxy/--user-agent apply only at daemon launch; pass them on the first `open`
    // only, so later calls don't emit "daemon already running, options ignored".
    const full = ["--session", this.session, ...args];
    if (args[0] === "open" && !this.launched) {
      full.splice(2, 0, "--user-agent", this.ua);
      if (this.proxy) full.splice(2, 0, "--proxy", this.proxy);
      this.launched = true;
    }
    const { out, timedOut } = runAgentBrowser(full, stdin, timeoutMs);
    if (timedOut) {
      this.timeouts++;
      this.log(`[reddit-miner] agent-browser ${args[0]} timed out after ${timeoutMs}ms (dead/unreachable proxy exit or stalled load)`);
    }
    return out;
  }
  clear(sub: string) {
    // agent-browser applies --proxy/--user-agent at DAEMON launch; a running daemon
    // ignores them. Kill it so THIS run's UA/proxy actually take effect (the clean UA
    // is what passes Reddit's headless challenge — non-negotiable for correctness).
    runAgentBrowser(["close", "--all"], undefined, 30_000);
    for (let attempt = 1; attempt <= 3; attempt++) {
      const before = this.timeouts;
      this.ab(["open", `https://www.reddit.com/r/${sub}/`], undefined, 35_000);
      this.ab(["wait", "3500"], undefined, 30_000);
      const body = this.ab(["get", "text", "body"], undefined, 30_000) || "";
      if (!body.includes(BLOCK_MARKER) && body.toLowerCase().replace(/\s/g, "").includes("r/" + sub.toLowerCase())) {
        this.log(`[reddit-miner] challenge cleared (attempt ${attempt})`); return;
      }
      if (this.timeouts > before)
        throw new BrowserError(
          `could not reach Reddit — agent-browser timed out ${this.timeouts}× (proxy exit dead/unreachable; test \`curl -x <proxy> https://ipinfo.io/json\` and rotate/fix the proxy)`,
        );
      this.log(`[reddit-miner] still blocked, retry ${attempt}/3`);
      Bun.sleepSync(2000);
    }
    throw new BrowserError("could not clear Reddit JS challenge (proxy exit IP likely flagged)");
  }
  fetchJson(url: string, tries = 3): any {
    const script =
      `(async()=>{const u=${JSON.stringify(url)};` +
      `const r=await fetch(u,{credentials:"include"});const t=await r.text();` +
      `await new Promise(s=>setTimeout(s,150));` +
      `const e=performance.getEntriesByType("resource").filter(x=>x.name===u).pop();` +
      `return JSON.stringify({s:r.status,t:t,ts:e?e.transferSize:0});})()`;
    let last = "";
    for (let i = 0; i < tries; i++) {
      const out = this.ab(["eval", "--stdin", "--json"], script);
      let payload: any;
      try { payload = JSON.parse(JSON.parse(out).data.result); }
      catch (e) { last = `eval parse failed: ${e}`; Bun.sleepSync(1500); continue; }
      if (payload.s !== 200 || (payload.t ?? "").includes(BLOCK_MARKER)) {
        last = `http ${payload.s} / blocked`; Bun.sleepSync(1500); continue;
      }
      try {
        const data = JSON.parse(payload.t);
        this.requests++;
        this.wireBytes += Number(payload.ts) || 0;
        this.decodedBytes += Buffer.byteLength(payload.t ?? "", "utf8");
        return data;
      } catch (e) { last = `json decode failed: ${e}`; Bun.sleepSync(1500); }
    }
    throw new BrowserError(`fetchJson failed for ${url}: ${last}`);
  }
  bandwidth() {
    const gb = this.wireBytes / 1e9;
    const rate = resolveUsdPerGb();
    return {
      requests: this.requests, wire_bytes: this.wireBytes,
      wire_mb: +(this.wireBytes / 1e6).toFixed(3), decoded_mb: +(this.decodedBytes / 1e6).toFixed(3),
      usd_per_gb: rate, est_cost_usd: +(gb * rate).toFixed(6),
      note: "wire_bytes = real proxy-billed bytes (gzip, incl. headers)",
    };
  }
  close() { try { this.ab(["close"], undefined, 15_000); } catch {} }
}

// ----------------------------- listing / thread -----------------------------

function listPosts(rb: RedditBrowser, sub: string, sort: string, time: string, limit: number) {
  const lim = Math.min(limit, 100);
  const url = ["top", "controversial"].includes(sort)
    ? `https://www.reddit.com/r/${sub}/${sort}.json?t=${time}&limit=${lim}`
    : `https://www.reddit.com/r/${sub}/${sort}.json?limit=${lim}`;
  const d = rb.fetchJson(url);
  const posts = (d?.data?.children ?? [])
    .map((c: any) => c.data)
    .filter((pd: any) => !pd.stickied)
    .map((pd: any) => ({
      id: pd.id, title: pd.title ?? "", selftext: pd.selftext ?? "",
      score: pd.score ?? 0, num_comments: pd.num_comments ?? 0, upvote_ratio: pd.upvote_ratio,
      flair: pd.link_flair_text, created_utc: pd.created_utc, author: pd.author,
      permalink: `https://reddit.com${pd.permalink ?? ""}`,
    }));
  posts.sort((a: any, b: any) => b.num_comments - a.num_comments);
  return posts.slice(0, limit);
}

function fetchThread(rb: RedditBrowser, permalink: string, limit = 500) {
  const m = permalink.match(/(\/r\/[^/]+\/comments\/[^?]*)/);
  const p = (m ? m[1] : permalink).replace(/\/+$/, "");
  return rb.fetchJson(`https://www.reddit.com${p}/.json?limit=${limit}`);
}

function walkCommentQuestions(children: any[], title: string, topicRx: RegExp | null, out: Q[]) {
  for (const node of children ?? []) {
    if (node.kind !== "t1") continue;
    const data = node.data ?? {};
    const body = (data.body ?? "").trim();
    const replies = data.replies || {};
    const rkids = (typeof replies === "object" && replies.data?.children
      ? replies.data.children : []).filter((r: any) => r.kind === "t1");
    if (isQuestion(body, topicRx)) {
      const q = extractQuestion(body);
      if (q !== null)
        out.push({
          q, score: data.score ?? 0, answered: answered(rkids.map((r: any) => r.data?.body ?? "")),
          n_replies: rkids.length, source: "reddit", thread_title: title,
          permalink: `https://reddit.com${data.permalink ?? ""}`,
        });
    }
    walkCommentQuestions(rkids, title, topicRx, out);
  }
}

function mine(rb: RedditBrowser, sub: string, time: string, nThreads: number, topicRx: RegExp | null) {
  const seen = new Set<string>(); let posts: any[] = [];
  for (const sort of ["top", "hot"])
    for (const p of listPosts(rb, sub, sort, time, 50))
      if (!seen.has(p.id)) { seen.add(p.id); posts.push(p); }
  posts.sort((a, b) => b.num_comments - a.num_comments);
  posts = posts.slice(0, nThreads);

  const questions: Q[] = [];
  for (const p of posts) {
    const blob = `${p.title}. ${p.selftext}`;
    if (isQuestion(blob, topicRx)) {
      const q = extractQuestion(blob);
      if (q !== null)
        questions.push({
          q, score: p.score, answered: p.num_comments > 0, n_replies: p.num_comments,
          source: "reddit-post", thread_title: p.title, permalink: p.permalink,
        });
    }
  }
  let scanned = 0;
  for (const p of posts) {
    let d;
    try { d = fetchThread(rb, p.permalink, 500); }
    catch (e) { console.error(`WARN thread ${p.permalink}: ${e}`); continue; }
    scanned++;
    try { walkCommentQuestions(d[1].data.children, p.title, topicRx, questions); }
    catch (e) { console.error(`WARN parse ${p.permalink}: ${e}`); }
  }
  return { threads_scanned: scanned, posts_considered: posts.length, questions };
}

// ----------------------------- setup / doctor -----------------------------

// Health-check a CLI by EXECUTING it, not just locating it on PATH.
// `which` finds a shim even when it can't run — most commonly a stale shebang
// after a Node/Python upgrade (npm/pipx/uv global installs break exactly this
// way: which() resolves the shim, exec then fails pointing at the shim itself).
// Distinguishes the three modes a bare `which` flattens into one PASS:
//   missing — not on PATH;  broken — found but won't execute;  ok — ran.
type ProbeResult = { status: "ok" | "missing" | "broken"; path: string; detail: string };
function probeCommand(cmd: string, args: string[] = ["--version"]): ProbeResult {
  let cmdPath = "";
  try { cmdPath = execFileSync("which", [cmd], { encoding: "utf8" }).trim(); } catch {}
  if (!cmdPath) return { status: "missing", path: "", detail: "not on PATH" };
  try {
    execFileSync(cmd, args, { encoding: "utf8", timeout: 15_000, stdio: ["ignore", "pipe", "pipe"] });
  } catch (e: any) {
    // ENOENT/EACCES (errno) or shell codes 126/127 = couldn't exec → broken.
    // Any OTHER nonzero exit means the binary DID run (e.g. unsupported flag) → ok.
    const errno = e?.code, code = e?.status;
    if (errno === "ENOENT" || errno === "EACCES" || code === 126 || code === 127) {
      return { status: "broken", path: cmdPath,
        detail: `found at ${cmdPath} but won't execute (stale shim? reinstall) — ${String(e?.message || errno).slice(0, 80)}` };
    }
  }
  return { status: "ok", path: cmdPath, detail: cmdPath };
}

function cmdSetup(proxyArg?: string | boolean, geminiArg?: string, usdArg?: string): number {
  const cfg = loadConfig();
  const saved: string[] = [];

  // proxy: explicit value, or (when --proxy is given with no value) read from stdin
  let proxy: string | undefined;
  if (typeof proxyArg === "string") proxy = proxyArg;
  else if (proxyArg === true) proxy = (fs.readFileSync(0, "utf8") || "").trim();
  if (proxy) {
    if (!/^https?:\/\//.test(proxy)) { console.error("ERROR: proxy must start with http:// or https://"); return 2; }
    cfg.proxy = proxy; saved.push(`proxy ${mask(proxy)}`);
  }

  // gemini key: enables the LLM `classify` path. Stored machine-local, never the repo.
  if (typeof geminiArg === "string" && geminiArg) { cfg.gemini_key = geminiArg; saved.push(`gemini_key ${geminiArg.slice(0, 6)}…`); }

  // proxy bandwidth rate: providers differ by ~8x, so the printed cost is only as good as this.
  if (typeof usdArg === "string" && usdArg) {
    const rate = parseFloat(usdArg);
    if (!Number.isFinite(rate) || rate <= 0) { console.error("ERROR: --usd-per-gb must be a positive number"); return 2; }
    cfg.usd_per_gb = rate; saved.push(`usd_per_gb ${rate}`);
  }

  if (!saved.length) {
    console.error("ERROR: nothing to set. Pass --proxy <url>, --usd-per-gb <rate> and/or --gemini-key <key>."); return 2;
  }
  fs.mkdirSync(path.dirname(CONFIG_PATH), { recursive: true });
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2));
  fs.chmodSync(CONFIG_PATH, 0o600);
  console.log(`Saved to ${CONFIG_PATH} (chmod 600): ${saved.join(", ")}`);
  console.log("This path is machine-local and outside the skill repo.");
  console.log("Next: run `reddit-miner doctor` to verify.");
  return 0;
}

async function cmdDoctor(proxyFlag?: string, noProxy = false): Promise<number> {
  let ok = true;
  const line = (status: boolean, label: string, detail = "") => {
    if (!status) ok = false;
    console.log(`  [${status ? "PASS" : "FAIL"}] ${label}${detail ? " — " + detail : ""}`);
  };
  console.log("reddit-miner doctor");
  const ab = probeCommand("agent-browser");
  const abPath = ab.status === "ok" ? ab.path : "";
  line(ab.status === "ok", "agent-browser installed",
    ab.status === "broken" ? ab.detail
      : ab.status === "missing" ? "install: npm i -g agent-browser  (then: agent-browser install)"
      : ab.path);
  line(typeof Bun !== "undefined", "bun runtime", typeof Bun !== "undefined" ? Bun.version : "install: https://bun.sh");

  // browser engine: agent-browser drives Chrome — verify one is actually reachable
  if (abPath) {
    let engineOk = false, engineErr = "";
    try {
      execFileSync("agent-browser", ["--session", "reddit-miner-engine", "open", "about:blank"],
        { encoding: "utf8", timeout: 60_000 });
      const r = execFileSync("agent-browser", ["--session", "reddit-miner-engine", "eval", "1+1", "--json"],
        { encoding: "utf8", timeout: 30_000 });
      engineOk = JSON.parse(r)?.success === true;
      try { execFileSync("agent-browser", ["--session", "reddit-miner-engine", "close"], { timeout: 20_000 }); } catch {}
    } catch (e: any) { engineErr = String(e?.stderr || e?.message || e).slice(0, 120); }
    line(engineOk, "browser engine (Chrome) reachable",
      engineOk ? "ok" : `no browser launched — run: agent-browser install  ${engineErr ? "(" + engineErr + ")" : ""}`);
  }

  let [proxy, source] = noProxy ? [null, null] : resolveProxy(proxyFlag);
  if (proxy) { const r = rotateSessid(proxy); if (r !== proxy) { proxy = r; source = `${source} (fresh sessid)`; } }
  // proxy is OPTIONAL: present = use it; absent = direct (only works from a clean/residential IP)
  console.log(`  [INFO] proxy ${proxy ? `configured — ${mask(proxy)} (from ${source})` : "not set — direct connection exposes this IP to Reddit and risks a ban; mining requires a proxy (run `setup --proxy <url>`)"}`);

  // LLM classification is OPTIONAL: present = the `classify` command uses Gemini
  // (higher recall); absent = `classify` falls back to the heuristic question detector.
  const [gkey, gsrc] = resolveGeminiKey();
  if (gkey) {
    let label = "", live = false;
    try {
      const v = await geminiBatch(gkey, null, [{ id: "probe", text: "I wish there was an app that reminded me to take my meds on time." }]);
      label = v["probe"] ?? ""; live = !!label;
    } catch (e) { label = String(e).slice(0, 60); }
    console.log(`  [${live ? "PASS" : "INFO"}] LLM classification — ${live ? `${GEMINI_MODEL} live (key from ${gsrc}, probe→${label})` : `key set (${gsrc}) but probe failed: ${label}`}`);
  } else {
    console.log("  [INFO] LLM classification disabled — set GEMINI_API_KEY or run `setup --gemini-key <key>` for higher-recall pain/demand/question classification (the `classify` command). Heuristic question detection still works without it.");
  }

  if (proxy) {
    try {
      // vendor-neutral IP echo — works through ANY proxy (override via REDDIT_IP_ECHO_URL)
      const echo = process.env.REDDIT_IP_ECHO_URL ?? "https://ipinfo.io/json";
      const out = execFileSync("curl", ["-s", "--max-time", "40", "-x", proxy, echo],
        { encoding: "utf8", timeout: 50_000 });
      const info = out.trim().startsWith("{") ? JSON.parse(out) : {};
      const ip = info.ip ?? info.query;
      const country = info.country ?? info.country_code ?? "?";
      line(!!ip, "proxy connectivity", ip ? `exit IP ${ip} (${country})` : "no response through proxy");
    } catch (e) { line(false, "proxy connectivity", String(e).replaceAll(proxy, mask(proxy))); }
  }

  const rb = new RedditBrowser(proxy, "reddit-miner-doctor", CLEAN_UA, false);
  try {
    rb.clear("Retatrutide");
    line(true, "Reddit JS challenge cleared (headless + clean UA)");
    const d = rb.fetchJson("https://www.reddit.com/r/Retatrutide/top.json?t=week&limit=2");
    const n = (d?.data?.children ?? []).length;
    const bw = rb.bandwidth();
    line(n > 0, "json API fetch via proxy", `${n} posts, ${bw.wire_mb} MB wire (~$${bw.est_cost_usd})`);
  } catch (e) { line(false, "Reddit challenge / fetch", String(e)); }
  finally { rb.close(); }

  console.log(`\nRESULT: ${ok ? "READY" : "NOT READY"}`);
  return ok ? 0 : 1;
}

// ----------------------------- Gemini classification (optional, key-gated) -----------------------------
// When a Gemini key resolves, snippets are classified by an LLM into
// pain | demand | question | other. This has far higher recall than the in-tool
// question/keyword heuristics: it reads MEANING, so it catches complaints and
// product-demand that carry no question mark and no pain keyword (benchmarked
// ~100% recall vs ~60% for the best regex on a GLP-1 logger mine). Without a key
// the tool falls back to the heuristic question detector — same as before. No new
// dependency: a plain HTTPS fetch, like the Reddit path. The key is read from env
// or the machine-local config, NEVER the (public) skill repo.

const GEMINI_MODEL = process.env.REDDIT_GEMINI_MODEL ?? "gemini-2.5-flash";
// rough cost: gemini-2.5-flash ~ $0.30 / 1M input tokens; a short snippet ≈ 90 tok
// plus per-batch prompt overhead → ≈ $0.000027 per classified unit.
const GEMINI_USD_PER_UNIT = 0.000027;

function resolveGeminiKey(): [string | null, string | null] {
  if (process.env.GEMINI_API_KEY) return [process.env.GEMINI_API_KEY, "env GEMINI_API_KEY"];
  const cfg = loadConfig();
  if (cfg.gemini_key) return [cfg.gemini_key, `config (${CONFIG_PATH})`];
  return [null, null];
}

function classifyPrompt(forCtx: string | null): string {
  const focus = forCtx
    ? `The researcher is mining specifically for: ${forCtx}\n` +
      "Only label a snippet \"pain\", \"demand\", or \"question\" if it is RELEVANT to that focus. " +
      "Complaints, requests, or questions unrelated to the focus are \"other\".\n"
    : "";
  return (
    "You classify short Reddit snippets for a researcher mining a subreddit for content gaps and product ideas.\n" +
    focus +
    "Labels:\n" +
    "- \"pain\": a frustration, complaint, friction, or unmet need (often NOT phrased as a question).\n" +
    "- \"demand\": asking for / wishing for / requesting a product, tool, app, or solution.\n" +
    "- \"question\": an information-seeking question that is not itself a complaint or a tool request.\n" +
    "- \"other\": anything else — success stories, neutral chat, advice, jokes, generic motivation, neutral mentions, or (when a focus is given) anything off-focus.\n" +
    "Be strict: a neutral or positive mention is \"other\"; only real friction is \"pain\".\n" +
    "Return a JSON array of {\"id\": string, \"label\": string}, classifying every input id."
  );
}

async function geminiBatch(key: string, forCtx: string | null, batch: { id: string; text: string }[], tries = 4): Promise<Record<string, string>> {
  const body = {
    systemInstruction: { parts: [{ text: classifyPrompt(forCtx) }] },
    contents: [{ parts: [{ text: JSON.stringify(batch) }] }],
    generationConfig: { temperature: 0, responseMimeType: "application/json" },
  };
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent?key=${key}`;
  for (let i = 0; i < tries; i++) {
    try {
      const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!res.ok) {
        if (res.status === 429 || res.status >= 500) { await Bun.sleep(1500 * (i + 1)); continue; }
        throw new Error(`http ${res.status}: ${(await res.text()).slice(0, 200)}`);
      }
      const j: any = await res.json();
      const txt = j?.candidates?.[0]?.content?.parts?.[0]?.text ?? "[]";
      const m: Record<string, string> = {};
      for (const r of JSON.parse(txt)) if (r && r.id) m[r.id] = r.label;
      return m;
    } catch (e) {
      if (i === tries - 1) { console.error(`[reddit-miner] gemini batch failed: ${String(e).slice(0, 120)}`); return {}; }
      await Bun.sleep(1200 * (i + 1));
    }
  }
  return {};
}

// Classify many units with a small concurrency pool (Gemini handles parallel calls).
async function classifyUnits(key: string, forCtx: string | null, units: RawUnit[], concurrency = 8, batchSize = 35): Promise<Record<string, string>> {
  const batches: { id: string; text: string }[][] = [];
  for (let i = 0; i < units.length; i += batchSize)
    batches.push(units.slice(i, i + batchSize).map((u) => ({ id: u.id, text: (u.text ?? "").slice(0, 500) })));
  const verdict: Record<string, string> = {};
  let cursor = 0, done = 0;
  async function worker() {
    while (cursor < batches.length) {
      const idx = cursor++;
      Object.assign(verdict, await geminiBatch(key, forCtx, batches[idx]));
      done += batches[idx].length;
      if (idx % 5 === 0 || done >= units.length) console.error(`[reddit-miner] classified ~${Math.min(done, units.length)}/${units.length}`);
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, batches.length) }, worker));
  return verdict;
}

// ----------------------------- unit collection (posts + comment bodies) -----------------------------

interface RawUnit {
  id: string; text: string; sub: string; score: number;
  permalink: string; kind: "post" | "comment"; thread_title: string;
}

function walkCommentBodies(children: any[], sub: string, title: string, out: RawUnit[]) {
  for (const node of children ?? []) {
    if (node.kind !== "t1") continue;
    const d = node.data ?? {};
    const body = (d.body ?? "").trim();
    if (body.length >= 15)
      out.push({ id: `c_${d.id ?? out.length}`, text: body, sub, score: d.score ?? 0,
        permalink: `https://reddit.com${d.permalink ?? ""}`, kind: "comment", thread_title: title });
    const reps = d.replies;
    if (reps && typeof reps === "object" && reps.data?.children) walkCommentBodies(reps.data.children, sub, title, out);
  }
}

// Fetch top+hot posts (engagement-floored) plus every comment body → flat units.
function collectUnits(rb: RedditBrowser, sub: string, time: string, nThreads: number, minScore: number, minComments: number) {
  const seen = new Set<string>(); let posts: any[] = [];
  for (const sort of ["top", "hot"])
    for (const p of listPosts(rb, sub, sort, time, 50))
      if (!seen.has(p.id)) { seen.add(p.id); posts.push(p); }
  posts = posts.filter((p) => (p.score ?? 0) >= minScore && (p.num_comments ?? 0) >= minComments);
  posts.sort((a, b) => b.num_comments - a.num_comments);
  posts = posts.slice(0, nThreads);

  const units: RawUnit[] = [];
  for (const p of posts)
    units.push({ id: `p_${p.id}`, text: `${p.title}. ${p.selftext ?? ""}`.trim(), sub,
      score: p.score, permalink: p.permalink, kind: "post", thread_title: p.title });
  let scanned = 0;
  for (const p of posts) {
    let d;
    try { d = fetchThread(rb, p.permalink, 500); }
    catch (e) { console.error(`WARN thread ${p.permalink}: ${e}`); continue; }
    scanned++;
    try { walkCommentBodies(d[1].data.children, sub, p.title, units); }
    catch (e) { console.error(`WARN parse ${p.permalink}: ${e}`); }
  }
  return { units, threads_scanned: scanned, posts_considered: posts.length };
}

// ----------------------------- arg parsing / main -----------------------------

function parseFlags(argv: string[]): Record<string, string | boolean> {
  const f: Record<string, string | boolean> = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith("--")) {
      const k = argv[i].slice(2);
      if (i + 1 < argv.length && !argv[i + 1].startsWith("--")) { f[k] = argv[++i]; }
      else f[k] = true;
    }
  }
  return f;
}

async function main() {
  const [cmd, ...rest] = process.argv.slice(2);
  const f = parseFlags(rest);

  if (cmd === "setup") process.exit(cmdSetup(f.proxy as string | boolean | undefined, f["gemini-key"] as string | undefined, f["usd-per-gb"] as string | undefined));
  if (cmd === "doctor") process.exit(await cmdDoctor(f.proxy as string | undefined, f["no-proxy"] === true));

  const mining = ["posts", "thread", "mine", "classify"].includes(cmd);
  const noProxy = f["no-proxy"] === true;
  let [proxy, source] = noProxy ? [null, null] : resolveProxy(f.proxy as string | undefined);
  if (mining && !proxy && !noProxy) {
    console.error("ERROR: no proxy configured — mining direct risks getting this IP banned by Reddit; run `setup --proxy <url>`, or pass --no-proxy to accept the risk");
    process.exit(2);
  }
  if (proxy && f["no-rotate"] !== true) {
    const rotated = rotateSessid(proxy);
    if (rotated !== proxy) { proxy = rotated; source = `${source} (fresh sessid)`; }
  }
  console.error(proxy
    ? `[reddit-miner] proxy from ${source}: ${mask(proxy)}`
    : "[reddit-miner] WARNING: --no-proxy — running direct; Reddit sees this IP and the ban risk is yours");
  const topicRx = f["topic-keywords"] ? new RegExp(f["topic-keywords"] as string, "i") : null;
  const keepOpen = !!f["keep-open"];

  const rb = new RedditBrowser(proxy);
  let res: any;
  try {
    if (cmd === "posts" || cmd === "mine" || cmd === "classify") rb.clear(f.subreddit as string);
    else if (cmd === "thread") {
      const mt = (f.url as string).match(/\/r\/([^/]+)\//);
      rb.clear(mt ? mt[1] : "all");
    }
    if (cmd === "classify") {
      const minScore = f["min-score"] ? parseInt(f["min-score"] as string) : 0;
      const minComments = f["min-comments"] ? parseInt(f["min-comments"] as string) : 0;
      const forCtx = (f["for"] as string) ?? null;
      const { units, threads_scanned, posts_considered } = collectUnits(
        rb, f.subreddit as string, (f.time as string) ?? "month",
        f.threads ? parseInt(f.threads as string) : 30, minScore, minComments,
      );
      const [gkey, gsrc] = resolveGeminiKey();
      if (gkey) {
        console.error(`[reddit-miner] classifying ${units.length} units with ${GEMINI_MODEL} (key from ${gsrc}, ~$${(units.length * GEMINI_USD_PER_UNIT).toFixed(3)})`);
        const verdict = await classifyUnits(gkey, forCtx, units);
        const pain: any[] = [], demand: any[] = [], questions: any[] = [];
        let other = 0;
        for (const u of units) {
          const row = { text: u.text.slice(0, 400), score: u.score, source: u.kind, thread_title: u.thread_title, permalink: u.permalink };
          const lab = verdict[u.id] ?? "other";
          if (lab === "pain") pain.push(row);
          else if (lab === "demand") demand.push(row);
          else if (lab === "question") questions.push(row);
          else other++;
        }
        for (const arr of [pain, demand, questions]) arr.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
        const top = f["top"] ? parseInt(f["top"] as string) : 40;
        res = {
          subreddit: f.subreddit, classifier: `gemini:${GEMINI_MODEL}`, for: forCtx,
          threads_scanned, posts_considered, n_units: units.length,
          n_pain: pain.length, n_demand: demand.length, n_question: questions.length, n_other: other,
          gemini_cost_est_usd: +(units.length * GEMINI_USD_PER_UNIT).toFixed(4),
          shown_per_bucket: top,
          pain: pain.slice(0, top), demand: demand.slice(0, top), questions: questions.slice(0, top),
        };
      } else {
        console.error("[reddit-miner] no Gemini key — falling back to heuristic question detection. For LLM pain/demand/question classification set GEMINI_API_KEY or run `setup --gemini-key <key>`.");
        const questions: any[] = [];
        for (const u of units) {
          if (!isQuestion(u.text, topicRx)) continue;
          const q = extractQuestion(u.text);
          if (q) questions.push({ q, score: u.score, source: u.kind, thread_title: u.thread_title, permalink: u.permalink });
        }
        questions.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
        res = {
          subreddit: f.subreddit, classifier: "heuristic", threads_scanned, posts_considered,
          n_units: units.length, n_questions: questions.length, questions,
        };
      }
    } else if (cmd === "posts") {
      res = {
        subreddit: f.subreddit, sort: (f.sort as string) ?? "top",
        posts: listPosts(rb, f.subreddit as string, (f.sort as string) ?? "top",
          (f.time as string) ?? "month", f.limit ? parseInt(f.limit as string) : 30),
      };
    } else if (cmd === "thread") {
      res = { thread: fetchThread(rb, f.url as string, f.limit ? parseInt(f.limit as string) : 500) };
    } else if (cmd === "mine") {
      res = mine(rb, f.subreddit as string, (f.time as string) ?? "month",
        f.threads ? parseInt(f.threads as string) : 30, topicRx);
      const unans = res.questions.filter((q: Q) => !q.answered);
      res.n_questions = res.questions.length;
      res.n_unanswered = unans.length;
      res.clusters_unanswered = cluster(unans, 10);
      res.top_questions = [...unans].sort((a, b) => (b.score ?? 0) - (a.score ?? 0)).slice(0, 20);
    } else {
      console.error(`Unknown command: ${cmd}`); process.exit(2);
    }
  } finally {
    res = res ?? {};
    res.bandwidth = rb.bandwidth();
    if (!keepOpen) rb.close();
  }
  const bw = res.bandwidth;
  console.error(`[reddit-miner] ${bw.requests} requests, ${bw.wire_mb} MB wire, ~$${bw.est_cost_usd} @ $${bw.usd_per_gb}/GB`);
  process.stdout.write(JSON.stringify(res, null, 2) + "\n");
}

main().catch((e) => { console.error(e); process.exit(1); });
