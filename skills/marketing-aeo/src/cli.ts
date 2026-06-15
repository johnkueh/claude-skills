#!/usr/bin/env node
// AEO Monitor — track AI chatbot citations across ChatGPT, Perplexity, Google AI Overview, Claude.

import { Command } from "commander";
import { mkdirSync, writeFileSync } from "node:fs";
import { join, basename } from "node:path";
import * as db from "./db.ts";
import { scrape, SUPPORTED_PLATFORMS, type Platform } from "./scrapers.ts";
import { extract } from "./extract.ts";
import { firecrawlScrapeCents, geminiFlashCents, anthropicHaikuCents } from "./costs.ts";

const program = new Command();
program.name("aeo").description("Track AI chatbot citations for your project. Data lives in <cwd>/.aeo/.").version("0.1.0");

// ---------- helpers ----------

const now = () => Math.floor(Date.now() / 1000);
const since = (days: number) => now() - days * 86400;

function projectName(d: db.DB): string {
  return db.getMeta(d, "project_name") ?? basename(process.cwd());
}

function firecrawlPlan(d: db.DB): string {
  return db.getMeta(d, "firecrawl_plan") ?? "hobby";
}

function budgetCents(d: db.DB): number | null {
  const v = db.getMeta(d, "budget_cents");
  return v ? Number(v) : null;
}

function fmt$(cents: number): string {
  return `$${(cents / 100).toFixed(4)}`;
}

// ---------- init / doctor / config ----------

program
  .command("init")
  .description("Create .aeo/ in the current directory and initialize SQLite.")
  .option("--name <name>", "Project name (defaults to current directory name)")
  .action((opts: { name?: string }) => {
    const d = db.connect();
    const project = opts.name ?? basename(process.cwd());
    db.setMeta(d, "project_name", project);
    db.setMeta(d, "schema_version", String(db.SCHEMA_VERSION));
    console.log(`✓ initialized .aeo/ at ${db.aeoDir()}`);
    console.log(`  project: ${project}`);
    console.log("");
    console.log("Next steps:");
    console.log("  1. Add domains to detect:   aeo domain add <yourdomain.com>");
    console.log("  2. Add queries to monitor:  aeo query add \"...\"");
    console.log("  3. Verify setup:            aeo doctor");
    console.log("  4. Run a check:             aeo run");
  });

program
  .command("doctor")
  .description("Check API keys, account balances, config, and DB stats.")
  .action(async () => {
    const d = db.connect();
    const c = db.counts(d);
    const aeoPath = db.aeoDir();
    const dbBytes = db.dbSizeBytes();

    console.log(`Project:    ${projectName(d)}`);
    console.log(`Data dir:   ${aeoPath}`);
    console.log(`DB:         ${db.dbPath()} (${dbBytes.toLocaleString()} bytes)`);
    console.log(`Queries:    ${c.queries} registered`);
    console.log(`Domains:    ${c.domains} registered`);
    console.log(`Runs:       ${c.runs} total`);
    console.log("");

    const keys: Record<string, [string, string]> = {
      FIRECRAWL_API_KEY:  ["ChatGPT + Perplexity scraping", "https://firecrawl.dev"],
      DATAFORSEO_API_KEY: ["Google AI Overview",            "https://dataforseo.com — set as base64(login:password)"],
      GEMINI_API_KEY:     ["Structured extraction",         "https://aistudio.google.com/apikey"],
      ANTHROPIC_API_KEY:  ["Claude (optional)",             "https://console.anthropic.com"],
    };
    console.log("API Keys:");
    for (const [k, [purpose, src]] of Object.entries(keys)) {
      if (process.env[k]) {
        console.log(`  ✓ ${k.padEnd(24)} set     (${purpose})`);
      } else {
        console.log(`  ✗ ${k.padEnd(24)} missing (${purpose}) — get it: ${src}`);
      }
    }
    console.log("");

    if (process.env.DATAFORSEO_API_KEY) {
      try {
        const res = await fetch("https://api.dataforseo.com/v3/appendix/user_data", {
          headers: { Authorization: `Basic ${process.env.DATAFORSEO_API_KEY}` },
        });
        const data = (await res.json()) as { tasks?: Array<{ result?: Array<{ money?: { balance?: number } }> }> };
        for (const task of data.tasks ?? []) {
          for (const r of task.result ?? []) {
            const bal = r.money?.balance ?? 0;
            console.log(`DataForSEO balance: $${bal.toFixed(2)}`);
          }
        }
      } catch (e) {
        console.log(`DataForSEO balance: error — ${(e as Error).message}`);
      }
    }

    const bud = budgetCents(d);
    const spent = db.monthSpendCents(d);
    if (bud !== null) {
      const pct = bud > 0 ? (spent / bud * 100) : 0;
      console.log(`Budget:     $${(bud / 100).toFixed(2)}/mo, $${(spent / 100).toFixed(2)} spent this month (${pct.toFixed(0)}%)`);
    } else {
      console.log(`Budget:     unset; $${(spent / 100).toFixed(2)} spent this month`);
    }

    const plan = firecrawlPlan(d);
    console.log(`Firecrawl:  ${plan} plan (set via: aeo config set firecrawl_plan <hobby|standard|growth>)`);
  });

// ---------- config ----------

const config = program.command("config").description("Get/set per-project config.");
config
  .command("set")
  .argument("<key>")
  .argument("<value>")
  .action((key: string, value: string) => {
    const d = db.connect();
    db.setMeta(d, key, value);
    console.log(`set ${key} = ${value}`);
  });
config
  .command("show")
  .action(() => {
    const d = db.connect();
    const rows = db.listMeta(d);
    if (rows.length === 0) {
      console.log("(empty)");
      return;
    }
    for (const r of rows) console.log(`${r.key.padEnd(20)} = ${r.value}`);
  });

// ---------- queries ----------

const queryCmd = program.command("query").description("Manage tracked queries.");
queryCmd
  .command("add")
  .argument("<text...>")
  .action((text: string[]) => {
    const d = db.connect();
    const q = text.join(" ");
    const id = db.addQuery(d, q);
    if (id) console.log(`+ ${id}: ${q}`);
    else console.log(`(already registered) ${q}`);
  });
queryCmd
  .command("list")
  .action(() => {
    const d = db.connect();
    for (const r of db.listQueries(d)) {
      console.log(`${String(r.id).padStart(4)}  ${r.text}`);
    }
  });
queryCmd
  .command("remove")
  .argument("<id>")
  .action((id: string) => {
    const d = db.connect();
    const n = db.removeQuery(d, Number(id));
    console.log(`removed ${n} row(s)`);
  });

// ---------- domains ----------

const domainCmd = program.command("domain").description("Manage domains to detect in citations.");
domainCmd
  .command("add")
  .argument("<domain>")
  .option("--label <label>", "Optional tag (e.g. 'own', 'competitor')")
  .action((domain: string, opts: { label?: string }) => {
    const d = db.connect();
    const id = db.addDomain(d, domain, opts.label);
    console.log(`+ ${id}: ${domain}${opts.label ? `  [${opts.label}]` : ""}`);
  });
domainCmd
  .command("list")
  .action(() => {
    const d = db.connect();
    for (const r of db.listDomains(d)) {
      console.log(`${String(r.id).padStart(4)}  ${r.domain}${r.label ? `  [${r.label}]` : ""}`);
    }
  });
domainCmd
  .command("remove")
  .argument("<id>")
  .action((id: string) => {
    const d = db.connect();
    const n = db.removeDomain(d, Number(id));
    console.log(`removed ${n} row(s)`);
  });

// ---------- budget ----------

const budgetCmd = program.command("budget").description("Set/show monthly cost budget (warning only, never blocks).");
budgetCmd
  .command("set")
  .argument("<cents>")
  .action((cents: string) => {
    const d = db.connect();
    db.setMeta(d, "budget_cents", cents);
    console.log(`budget set to $${(Number(cents) / 100).toFixed(2)}/month`);
  });
budgetCmd
  .command("clear")
  .action(() => {
    const d = db.connect();
    db.deleteMeta(d, "budget_cents");
    console.log("budget cleared");
  });
budgetCmd
  .command("show")
  .action(() => {
    const d = db.connect();
    const bud = budgetCents(d);
    const spent = db.monthSpendCents(d);
    if (bud === null) {
      console.log(`No budget set. $${(spent / 100).toFixed(2)} spent this month.`);
    } else {
      const pct = bud > 0 ? (spent / bud * 100) : 0;
      console.log(`$${(spent / 100).toFixed(2)} / $${(bud / 100).toFixed(2)} this month (${pct.toFixed(0)}%)`);
    }
  });

// ---------- run ----------

program
  .command("run")
  .description("Execute all (query × platform) checks and store results.")
  .option("-p, --platform <platforms...>", "Limit to specific platform(s)")
  .option("-q, --query <text>", "Run a single query (not from DB)")
  .option("--dry-run", "Print estimated cost without running")
  .option("--serial", "Run platforms serially instead of in parallel")
  .action(async (opts: { platform?: string[]; query?: string; dryRun?: boolean; serial?: boolean }) => {
    const d = db.connect();
    const queries = opts.query ? [opts.query] : db.listQueries(d).map((q) => q.text);
    if (queries.length === 0) {
      console.log("No queries registered. Use `aeo query add \"...\"` first.");
      return;
    }

    let platforms = (opts.platform && opts.platform.length > 0)
      ? opts.platform.filter((p) => SUPPORTED_PLATFORMS.includes(p as Platform)) as Platform[]
      : [...SUPPORTED_PLATFORMS];

    if (platforms.includes("claude") && !process.env.ANTHROPIC_API_KEY) {
      console.log("note: skipping claude (ANTHROPIC_API_KEY not set)");
      platforms = platforms.filter((p) => p !== "claude");
    }

    const totalJobs = queries.length * platforms.length;
    if (totalJobs === 0) {
      console.log("Nothing to run.");
      return;
    }

    if (opts.dryRun) {
      const plan = firecrawlPlan(d);
      const perPlatform: Record<Platform, number> = {
        chatgpt:    firecrawlScrapeCents(plan) + geminiFlashCents(8000, 1000),
        perplexity: firecrawlScrapeCents(plan) + geminiFlashCents(8000, 1000),
        "google-ai": 0.2 + geminiFlashCents(5000, 1000),
        claude:     anthropicHaikuCents(1000, 800, 1) + geminiFlashCents(3000, 800),
      };
      const total = platforms.reduce((acc, p) => acc + perPlatform[p], 0) * queries.length;
      console.log(`Dry run: ${totalJobs} jobs (${queries.length} queries × ${platforms.length} platforms)`);
      for (const p of platforms) {
        console.log(`  ${p.padEnd(15)} ~${fmt$(perPlatform[p])}/query`);
      }
      console.log(`Estimated total: ${fmt$(total)}`);
      return;
    }

    const bud = budgetCents(d);
    if (bud !== null) {
      const spent = db.monthSpendCents(d);
      if (spent >= bud) {
        console.log(`⚠ over budget: $${(spent / 100).toFixed(2)} / $${(bud / 100).toFixed(2)} this month — continuing anyway`);
      } else if (spent >= bud * 0.8) {
        console.log(`⚠ ${(spent / bud * 100).toFixed(0)}% of monthly budget used ($${(spent / 100).toFixed(2)} / $${(bud / 100).toFixed(2)})`);
      }
    }

    const own = db.ownDomains(d);
    const plan = firecrawlPlan(d);
    const rawDir = join(db.aeoDir(), "raw");
    mkdirSync(rawDir, { recursive: true });

    console.log(`Running ${totalJobs} jobs across ${platforms.length} platform(s)...`);
    const t0 = Date.now();
    let citedCount = 0;
    let errorCount = 0;
    let totalCostCents = 0;

    const jobs: Array<{ query: string; platform: Platform }> = [];
    for (const q of queries) for (const p of platforms) jobs.push({ query: q, platform: p });

    const runOne = async (query: string, platform: Platform) => {
      const scrapeRes = await scrape(platform, query, plan);
      const safeQ = query.replace(/[^a-zA-Z0-9]/g, "_").slice(0, 40);
      const rawPath = join(rawDir, `${Math.floor(Date.now() / 1000)}_${platform}_${safeQ}.txt`);
      writeFileSync(rawPath, scrapeRes.text || (scrapeRes.error ?? ""));

      if (scrapeRes.error) {
        const runId = db.insertRun(d, {
          queryText: query, platform, responseText: "", aiUsedWebSearch: false,
          responseStructure: "", rawScrapePath: rawPath, status: "error", errorMessage: scrapeRes.error,
        });
        db.recordCost(d, {
          provider: scrapeRes.provider, operation: scrapeRes.operation, costCents: scrapeRes.costCents,
          runId, inputTokens: scrapeRes.inputTokens, outputTokens: scrapeRes.outputTokens,
          credits: scrapeRes.credits, metadata: scrapeRes.metadata,
        });
        errorCount += 1;
        totalCostCents += scrapeRes.costCents;
        console.log(`  ✗ ${platform.padEnd(15)} ${query.slice(0, 50).padEnd(50)}  ERROR: ${scrapeRes.error}`);
        return;
      }

      const extracted = await extract(scrapeRes.text, platform);
      const status = (extracted.responseText || extracted.citations.length > 0) ? "ok" : "empty";

      const runId = db.insertRun(d, {
        queryText: query, platform,
        responseText: extracted.responseText, aiUsedWebSearch: extracted.aiUsedWebSearch,
        responseStructure: extracted.responseStructure, rawScrapePath: rawPath, status,
      });
      db.insertCitations(d, runId, extracted.citations);
      db.recordCost(d, {
        provider: scrapeRes.provider, operation: scrapeRes.operation, costCents: scrapeRes.costCents,
        runId, inputTokens: scrapeRes.inputTokens, outputTokens: scrapeRes.outputTokens,
        credits: scrapeRes.credits, metadata: scrapeRes.metadata,
      });
      if (extracted.inputTokens || extracted.outputTokens) {
        db.recordCost(d, {
          provider: "gemini", operation: "extract", costCents: extracted.costCents, runId,
          inputTokens: extracted.inputTokens, outputTokens: extracted.outputTokens,
          metadata: { platform },
        });
      }

      const citedDomains = new Set(extracted.citations.map((c) => c.domain));
      const citedOwn = own.some((d) => citedDomains.has(d));
      const marker = citedOwn ? "✓ CITED" : "      ";
      const cost = scrapeRes.costCents + extracted.costCents;
      totalCostCents += cost;
      if (citedOwn) citedCount += 1;
      console.log(`  ${marker} ${platform.padEnd(15)} ${query.slice(0, 50).padEnd(50)}  ${fmt$(cost)}  (${extracted.citations.length} citations)`);
    };

    if (opts.serial) {
      for (const j of jobs) await runOne(j.query, j.platform);
    } else {
      // Bounded concurrency. Unbounded Promise.all fires every job at once, which
      // saturates the Firecrawl hobby plan's concurrency limit → server-side
      // SCRAPE_TIMEOUTs on ChatGPT/Perplexity (a single scrape succeeds in ~15s).
      // Default 3; tune with AEO_CONCURRENCY, or --serial for one at a time.
      const limit = Math.max(1, Number(process.env.AEO_CONCURRENCY ?? 3));
      let next = 0;
      await Promise.all(
        Array.from({ length: Math.min(limit, jobs.length) }, async () => {
          while (next < jobs.length) { const j = jobs[next++]; await runOne(j.query, j.platform); }
        }),
      );
    }

    const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
    console.log("");
    console.log(`Done in ${elapsed}s`);
    console.log(`Cited: ${citedCount}/${totalJobs}   Errors: ${errorCount}`);
    console.log(`Cost:  ${fmt$(totalCostCents)}`);
  });

// ---------- reports ----------

program
  .command("report")
  .description("Citation rate per query per platform.")
  .option("--days <n>", "Window size in days", "7")
  .option("--json", "Output JSON")
  .action((opts: { days: string; json?: boolean }) => {
    const d = db.connect();
    const own = db.ownDomains(d);
    const days = Number(opts.days);
    const rows = db.citationRateByQueryPlatform(d, since(days), own);

    if (opts.json) {
      console.log(JSON.stringify(rows, null, 2));
      return;
    }
    if (rows.length === 0) {
      console.log(`No runs in the last ${days} days.`);
      return;
    }
    console.log(`Citation rate — last ${days} days (own: ${own.join(", ") || "none"})`);
    console.log("");
    let currentQ = "";
    for (const r of rows) {
      if (r.query_text !== currentQ) {
        console.log(`\n  ${r.query_text}`);
        currentQ = r.query_text;
      }
      const pct = r.total_runs > 0 ? (100 * r.cited_count / r.total_runs) : 0;
      console.log(`    ${r.platform.padEnd(15)}  ${r.cited_count}/${r.total_runs} (${pct.toFixed(0)}%)`);
    }
  });

program
  .command("competitors")
  .description("Top cited domains across all your queries.")
  .option("--days <n>", "Window in days", "30")
  .option("--limit <n>", "Top N", "30")
  .option("--json", "Output JSON")
  .action((opts: { days: string; limit: string; json?: boolean }) => {
    const d = db.connect();
    const rows = db.topCitedDomains(d, since(Number(opts.days)), Number(opts.limit));
    const own = new Set(db.ownDomains(d));
    if (opts.json) {
      console.log(JSON.stringify(rows, null, 2));
      return;
    }
    if (rows.length === 0) {
      console.log("No citations yet.");
      return;
    }
    console.log(`Top ${opts.limit} cited domains — last ${opts.days} days`);
    console.log("");
    for (const r of rows) {
      const marker = own.has(r.domain) ? "★" : " ";
      console.log(`  ${marker} ${String(r.mentions).padStart(4)}  ${r.domain}`);
    }
  });

program
  .command("history")
  .description("Full citation history for a single query.")
  .requiredOption("-q, --query <text>")
  .option("--days <n>", "Window in days", "30")
  .option("--json", "Output JSON")
  .action((opts: { query: string; days: string; json?: boolean }) => {
    const d = db.connect();
    const own = db.ownDomains(d);
    const rows = db.historyForQuery(d, opts.query, since(Number(opts.days)), own);
    if (opts.json) {
      console.log(JSON.stringify(rows, null, 2));
      return;
    }
    if (rows.length === 0) {
      console.log(`No runs for '${opts.query}' in last ${opts.days} days.`);
      return;
    }
    console.log(`History — '${opts.query}' — last ${opts.days} days`);
    for (const r of rows) {
      const dt = new Date(r.ts * 1000).toISOString().replace("T", " ").slice(0, 16);
      const marker = r.cited_own ? "✓" : " ";
      const doms = r.all_domains.slice(0, 5).join(", ") || "(no citations)";
      console.log(`  ${marker} ${dt}  ${r.platform.padEnd(15)}  ${doms}`);
    }
  });

// ---------- cost ----------

program
  .command("cost")
  .description("Show actual spend breakdown.")
  .option("--days <n>", "Window in days (default: current month)")
  .option("--by <dimension>", "provider | platform | query", "provider")
  .option("--month <ym>", "Specific month YYYY-MM")
  .option("--json", "Output JSON")
  .action((opts: { days?: string; by: string; month?: string; json?: boolean }) => {
    const d = db.connect();
    let sinceTs: number;
    let label: string;
    if (opts.month) {
      const m = opts.month.match(/^(\d{4})-(\d{2})$/);
      if (!m) {
        console.log("Bad month format. Use YYYY-MM.");
        return;
      }
      const y = Number(m[1]); const mo = Number(m[2]);
      sinceTs = Math.floor(new Date(Date.UTC(y, mo - 1, 1)).getTime() / 1000);
      label = opts.month;
    } else if (opts.days !== undefined) {
      sinceTs = since(Number(opts.days));
      label = `last ${opts.days} days`;
    } else {
      const n = new Date();
      sinceTs = Math.floor(new Date(Date.UTC(n.getUTCFullYear(), n.getUTCMonth(), 1)).getTime() / 1000);
      label = n.toISOString().slice(0, 7);
    }

    const summary = db.costSummary(d, sinceTs);
    if (opts.json) {
      if (opts.by === "provider") console.log(JSON.stringify(summary, null, 2));
      else if (opts.by === "platform") console.log(JSON.stringify(db.costByPlatform(d, sinceTs), null, 2));
      else console.log(JSON.stringify(db.costByQuery(d, sinceTs), null, 2));
      return;
    }

    console.log(`Cost — ${label}  ·  ${fmt$(summary.total_cents)} total`);
    console.log("");

    if (opts.by === "provider") {
      console.log("By provider:");
      for (const r of summary.by_provider) {
        console.log(`  ${r.provider.padEnd(15)}  ${fmt$(r.cents ?? 0)}  (${r.calls} calls)`);
      }
    } else if (opts.by === "platform") {
      const rows = db.costByPlatform(d, sinceTs);
      console.log("By platform:");
      for (const r of rows) {
        console.log(`  ${(r.platform ?? "?").padEnd(15)}  ${fmt$(r.cents ?? 0)}  (${r.calls} calls)`);
      }
    } else if (opts.by === "query") {
      const rows = db.costByQuery(d, sinceTs);
      console.log("By query:");
      for (const r of rows) {
        console.log(`  ${fmt$(r.cents ?? 0)}  ${r.query.slice(0, 70)}`);
      }
    }
  });

// ---------- export ----------

program
  .command("export")
  .description("Dump all runs + citations for external analysis.")
  .option("--format <fmt>", "json | csv", "json")
  .option("-o, --output <path>")
  .action((opts: { format: string; output?: string }) => {
    const d = db.connect();
    const rows = db.exportRuns(d);
    let text: string;
    if (opts.format === "csv") {
      const headers = ["id", "ts", "query_text", "platform", "status", "cited_domains"];
      const escape = (v: unknown) => {
        const s = v == null ? "" : String(v);
        return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
      };
      text = [headers.join(","), ...rows.map((r) => headers.map((h) => escape((r as Record<string, unknown>)[h])).join(","))].join("\n");
    } else {
      text = JSON.stringify(rows, null, 2);
    }
    if (opts.output) {
      writeFileSync(opts.output, text);
      console.log(`wrote ${rows.length} rows to ${opts.output}`);
    } else {
      console.log(text);
    }
  });

program.parseAsync().catch((e) => {
  console.error(e);
  process.exit(1);
});
