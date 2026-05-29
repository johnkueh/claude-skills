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
 *   reddit-miner setup   [--proxy <url>]
 *   reddit-miner doctor
 *   reddit-miner posts   --subreddit <s> [--sort top|hot|new|rising] [--time month] [--limit 30]
 *   reddit-miner thread  --url <permalink> [--limit 500]
 *   reddit-miner mine    --subreddit <s> [--time month] [--threads 30] [--topic-keywords <re>]
 *
 * Credential resolution: --proxy flag, REDDIT_PROXY env, then the machine-local
 * config (~/.config/reddit-miner/config.json). The proxy secret is NEVER read
 * from or written to the skill repo (which is public).
 *
 * Env: REDDIT_PROXY, REDDIT_MINER_UA, REDDIT_PROXY_USD_PER_GB (default 8)
 */
import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

const CLEAN_UA =
  process.env.REDDIT_MINER_UA ??
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36";
const USD_PER_GB = parseFloat(process.env.REDDIT_PROXY_USD_PER_GB ?? "8");
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

// ----------------------------- headless browser -----------------------------

class BrowserError extends Error {}

class RedditBrowser {
  proxy: string | null; session: string; ua: string; verbose: boolean;
  wireBytes = 0; decodedBytes = 0; requests = 0; private launched = false;
  constructor(proxy: string | null, session = SESSION, ua = CLEAN_UA, verbose = true) {
    this.proxy = proxy; this.session = session; this.ua = ua; this.verbose = verbose;
    if (!process.env.AGENT_BROWSER_MAX_OUTPUT) process.env.AGENT_BROWSER_MAX_OUTPUT = "8000000";
  }
  private log(...a: any[]) { if (this.verbose) console.error(...a); }
  private ab(args: string[], stdin?: string): string {
    // --proxy/--user-agent apply only at daemon launch; pass them on the first `open`
    // only, so later calls don't emit "daemon already running, options ignored".
    const full = ["--session", this.session, ...args];
    if (args[0] === "open" && !this.launched) {
      full.splice(2, 0, "--user-agent", this.ua);
      if (this.proxy) full.splice(2, 0, "--proxy", this.proxy);
      this.launched = true;
    }
    try {
      return execFileSync("agent-browser", full, {
        input: stdin, encoding: "utf8", maxBuffer: 64 * 1024 * 1024, timeout: 90_000,
      });
    } catch (e: any) { return e.stdout ?? ""; }
  }
  clear(sub: string) {
    // agent-browser applies --proxy/--user-agent at DAEMON launch; a running daemon
    // ignores them. Kill it so THIS run's UA/proxy actually take effect (the clean UA
    // is what passes Reddit's headless challenge — non-negotiable for correctness).
    try { execFileSync("agent-browser", ["close", "--all"], { timeout: 30_000 }); } catch {}
    for (let attempt = 1; attempt <= 3; attempt++) {
      this.ab(["open", `https://www.reddit.com/r/${sub}/`]);
      this.ab(["wait", "3500"]);
      const body = this.ab(["get", "text", "body"]) || "";
      if (!body.includes(BLOCK_MARKER) && body.toLowerCase().replace(/\s/g, "").includes("r/" + sub.toLowerCase())) {
        this.log(`[reddit-miner] challenge cleared (attempt ${attempt})`); return;
      }
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
    return {
      requests: this.requests, wire_bytes: this.wireBytes,
      wire_mb: +(this.wireBytes / 1e6).toFixed(3), decoded_mb: +(this.decodedBytes / 1e6).toFixed(3),
      usd_per_gb: USD_PER_GB, est_cost_usd: +(gb * USD_PER_GB).toFixed(6),
      note: "wire_bytes = real proxy-billed bytes (gzip, incl. headers)",
    };
  }
  close() { try { this.ab(["close"]); } catch {} }
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

function cmdSetup(proxyArg?: string): number {
  let proxy = proxyArg;
  if (!proxy) proxy = (fs.readFileSync(0, "utf8") || "").trim();
  if (!proxy || !/^https?:\/\//.test(proxy)) {
    console.error("ERROR: proxy must start with http:// or https://"); return 2;
  }
  fs.mkdirSync(path.dirname(CONFIG_PATH), { recursive: true });
  const cfg = loadConfig(); cfg.proxy = proxy;
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2));
  fs.chmodSync(CONFIG_PATH, 0o600);
  console.log(`Saved proxy to ${CONFIG_PATH} (chmod 600): ${mask(proxy)}`);
  console.log("This path is machine-local and outside the skill repo.");
  console.log("Next: run `reddit-miner doctor` to verify agent-browser, Chrome, and the proxy.");
  return 0;
}

function cmdDoctor(proxyFlag?: string): number {
  let ok = true;
  const line = (status: boolean, label: string, detail = "") => {
    if (!status) ok = false;
    console.log(`  [${status ? "PASS" : "FAIL"}] ${label}${detail ? " — " + detail : ""}`);
  };
  console.log("reddit-miner doctor");
  let abPath = "";
  try { abPath = execFileSync("which", ["agent-browser"], { encoding: "utf8" }).trim(); } catch {}
  line(!!abPath, "agent-browser installed",
    abPath || "install: npm i -g agent-browser  (then: agent-browser install)");
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

  const [proxy, source] = resolveProxy(proxyFlag);
  // proxy is OPTIONAL: present = use it; absent = direct (only works from a clean/residential IP)
  console.log(`  [INFO] proxy ${proxy ? `configured — ${mask(proxy)} (from ${source})` : "not set — will connect DIRECT (only works from a clean/residential IP; set one via `setup` if you get blocked)"}`);

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
    } catch (e) { line(false, "proxy connectivity", String(e)); }
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

function main() {
  const [cmd, ...rest] = process.argv.slice(2);
  const f = parseFlags(rest);

  if (cmd === "setup") process.exit(cmdSetup(f.proxy as string | undefined));
  if (cmd === "doctor") process.exit(cmdDoctor(f.proxy as string | undefined));

  const noProxy = f["no-proxy"] === true;
  const [proxy, source] = noProxy ? [null, null] : resolveProxy(f.proxy as string | undefined);
  console.error(proxy
    ? `[reddit-miner] proxy from ${source}: ${mask(proxy)}`
    : "[reddit-miner] no proxy — connecting direct (works only from a clean/residential IP)");
  const topicRx = f["topic-keywords"] ? new RegExp(f["topic-keywords"] as string, "i") : null;
  const keepOpen = !!f["keep-open"];

  const rb = new RedditBrowser(proxy);
  let res: any;
  try {
    if (cmd === "posts" || cmd === "mine") rb.clear(f.subreddit as string);
    else if (cmd === "thread") {
      const mt = (f.url as string).match(/\/r\/([^/]+)\//);
      rb.clear(mt ? mt[1] : "all");
    }
    if (cmd === "posts") {
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

main();
