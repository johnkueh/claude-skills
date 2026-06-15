// SQLite schema + query helpers. Data lives in <project>/.aeo/runs.sqlite.

import Database from "better-sqlite3";
import { mkdirSync, statSync, existsSync } from "node:fs";
import { join, resolve } from "node:path";

export const SCHEMA_VERSION = 1;

const SCHEMA = `
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE IF NOT EXISTS queries (
  id INTEGER PRIMARY KEY,
  text TEXT NOT NULL UNIQUE,
  added_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS domains (
  id INTEGER PRIMARY KEY,
  domain TEXT NOT NULL UNIQUE,
  label TEXT,
  added_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY,
  ts INTEGER NOT NULL,
  query_text TEXT NOT NULL,
  platform TEXT NOT NULL,
  response_text TEXT,
  ai_used_web_search INTEGER,
  response_structure TEXT,
  raw_scrape_path TEXT,
  status TEXT NOT NULL,
  error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_query_ts ON runs(query_text, ts);
CREATE INDEX IF NOT EXISTS idx_runs_ts ON runs(ts);
CREATE INDEX IF NOT EXISTS idx_runs_platform ON runs(platform);

CREATE TABLE IF NOT EXISTS citations (
  id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL,
  url TEXT NOT NULL,
  domain TEXT NOT NULL,
  anchor_text TEXT,
  position INTEGER,
  FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_citations_domain ON citations(domain);
CREATE INDEX IF NOT EXISTS idx_citations_run ON citations(run_id);

CREATE TABLE IF NOT EXISTS cost_events (
  id INTEGER PRIMARY KEY,
  ts INTEGER NOT NULL,
  run_id INTEGER,
  provider TEXT NOT NULL,
  operation TEXT NOT NULL,
  cost_cents REAL NOT NULL,
  input_tokens INTEGER,
  output_tokens INTEGER,
  credits INTEGER,
  metadata TEXT,
  FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_cost_ts ON cost_events(ts);
CREATE INDEX IF NOT EXISTS idx_cost_provider ON cost_events(provider);
`;

export type DB = Database.Database;

export function aeoDir(cwd: string = process.cwd()): string {
  return resolve(cwd, ".aeo");
}

export function dbPath(cwd: string = process.cwd()): string {
  return join(aeoDir(cwd), "runs.sqlite");
}

export function connect(cwd: string = process.cwd()): DB {
  const dir = aeoDir(cwd);
  mkdirSync(dir, { recursive: true });
  const db = new Database(dbPath(cwd));
  db.pragma("foreign_keys = ON");
  db.exec(SCHEMA);
  setMeta(db, "schema_version", String(SCHEMA_VERSION));
  return db;
}

export function dbSizeBytes(cwd: string = process.cwd()): number {
  const p = dbPath(cwd);
  if (!existsSync(p)) return 0;
  return statSync(p).size;
}

// --- meta ---

export function getMeta(db: DB, key: string, defaultValue?: string): string | undefined {
  const row = db.prepare("SELECT value FROM meta WHERE key = ?").get(key) as { value: string } | undefined;
  return row?.value ?? defaultValue;
}

export function setMeta(db: DB, key: string, value: string): void {
  db.prepare(
    "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
  ).run(key, value);
}

export function deleteMeta(db: DB, key: string): void {
  db.prepare("DELETE FROM meta WHERE key = ?").run(key);
}

export function listMeta(db: DB): Array<{ key: string; value: string }> {
  return db.prepare("SELECT key, value FROM meta ORDER BY key").all() as Array<{ key: string; value: string }>;
}

// --- queries ---

export interface QueryRow {
  id: number;
  text: string;
  added_at: number;
}

export function addQuery(db: DB, text: string): number {
  const result = db.prepare(
    "INSERT OR IGNORE INTO queries(text, added_at) VALUES(?, ?)",
  ).run(text, Math.floor(Date.now() / 1000));
  return Number(result.lastInsertRowid);
}

export function listQueries(db: DB): QueryRow[] {
  return db.prepare("SELECT id, text, added_at FROM queries ORDER BY id").all() as QueryRow[];
}

export function removeQuery(db: DB, id: number): number {
  return db.prepare("DELETE FROM queries WHERE id = ?").run(id).changes;
}

// --- domains ---

export interface DomainRow {
  id: number;
  domain: string;
  label: string | null;
  added_at: number;
}

export function addDomain(db: DB, domain: string, label?: string): number {
  const normalized = domain.toLowerCase().replace(/^www\./, "");
  const result = db.prepare(
    "INSERT OR IGNORE INTO domains(domain, label, added_at) VALUES(?, ?, ?)",
  ).run(normalized, label ?? null, Math.floor(Date.now() / 1000));
  return Number(result.lastInsertRowid);
}

export function listDomains(db: DB): DomainRow[] {
  return db.prepare("SELECT id, domain, label, added_at FROM domains ORDER BY id").all() as DomainRow[];
}

export function removeDomain(db: DB, id: number): number {
  return db.prepare("DELETE FROM domains WHERE id = ?").run(id).changes;
}

export function ownDomains(db: DB): string[] {
  return (db.prepare("SELECT domain FROM domains").all() as Array<{ domain: string }>).map((r) => r.domain);
}

// --- runs ---

export interface InsertRunInput {
  queryText: string;
  platform: string;
  responseText: string;
  aiUsedWebSearch: boolean;
  responseStructure: string;
  rawScrapePath: string;
  status: "ok" | "empty" | "error";
  errorMessage?: string;
}

export function insertRun(db: DB, input: InsertRunInput): number {
  const result = db.prepare(
    `INSERT INTO runs(ts, query_text, platform, response_text, ai_used_web_search, response_structure, raw_scrape_path, status, error_message)
     VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  ).run(
    Math.floor(Date.now() / 1000),
    input.queryText,
    input.platform,
    input.responseText,
    input.aiUsedWebSearch ? 1 : 0,
    input.responseStructure,
    input.rawScrapePath,
    input.status,
    input.errorMessage ?? null,
  );
  return Number(result.lastInsertRowid);
}

export interface CitationInput {
  url: string;
  domain: string;
  anchor_text?: string | null;
  position?: number | null;
}

export function insertCitations(db: DB, runId: number, citations: CitationInput[]): void {
  if (citations.length === 0) return;
  const stmt = db.prepare(
    "INSERT INTO citations(run_id, url, domain, anchor_text, position) VALUES(?, ?, ?, ?, ?)",
  );
  const tx = db.transaction((rows: CitationInput[]) => {
    for (const c of rows) {
      stmt.run(runId, c.url, c.domain, c.anchor_text ?? null, c.position ?? null);
    }
  });
  tx(citations);
}

// --- cost events ---

export interface CostEventInput {
  runId?: number | null;
  provider: string;
  operation: string;
  costCents: number;
  inputTokens?: number | null;
  outputTokens?: number | null;
  credits?: number | null;
  metadata?: Record<string, unknown> | null;
}

export function recordCost(db: DB, input: CostEventInput): void {
  db.prepare(
    `INSERT INTO cost_events(ts, run_id, provider, operation, cost_cents, input_tokens, output_tokens, credits, metadata)
     VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  ).run(
    Math.floor(Date.now() / 1000),
    input.runId ?? null,
    input.provider,
    input.operation,
    input.costCents,
    input.inputTokens ?? null,
    input.outputTokens ?? null,
    input.credits ?? null,
    input.metadata ? JSON.stringify(input.metadata) : null,
  );
}

// --- reports ---

export interface CitationRateRow {
  query_text: string;
  platform: string;
  total_runs: number;
  cited_count: number;
}

export function citationRateByQueryPlatform(db: DB, sinceTs: number, own: string[]): CitationRateRow[] {
  if (own.length === 0) {
    return db.prepare(
      `SELECT query_text, platform, COUNT(*) AS total_runs, 0 AS cited_count
       FROM runs WHERE ts >= ? AND status = 'ok'
       GROUP BY query_text, platform
       ORDER BY query_text, platform`,
    ).all(sinceTs) as CitationRateRow[];
  }
  const placeholders = own.map(() => "?").join(",");
  return db.prepare(
    `SELECT r.query_text, r.platform, COUNT(*) AS total_runs,
            SUM(CASE WHEN EXISTS (
              SELECT 1 FROM citations c WHERE c.run_id = r.id AND c.domain IN (${placeholders})
            ) THEN 1 ELSE 0 END) AS cited_count
     FROM runs r
     WHERE r.ts >= ? AND r.status = 'ok'
     GROUP BY r.query_text, r.platform
     ORDER BY r.query_text, r.platform`,
  ).all(...own, sinceTs) as CitationRateRow[];
}

export interface DomainMentionRow {
  domain: string;
  mentions: number;
}

export function topCitedDomains(db: DB, sinceTs: number, limit = 30): DomainMentionRow[] {
  return db.prepare(
    `SELECT domain, COUNT(*) AS mentions
     FROM citations c
     JOIN runs r ON r.id = c.run_id
     WHERE r.ts >= ?
     GROUP BY domain
     ORDER BY mentions DESC
     LIMIT ?`,
  ).all(sinceTs, limit) as DomainMentionRow[];
}

export interface HistoryEntry {
  ts: number;
  platform: string;
  status: string;
  cited_own: boolean;
  all_domains: string[];
}

export function historyForQuery(db: DB, queryText: string, sinceTs: number, own: string[]): HistoryEntry[] {
  const rows = db.prepare(
    "SELECT id, ts, platform, status FROM runs WHERE query_text = ? AND ts >= ? ORDER BY ts DESC",
  ).all(queryText, sinceTs) as Array<{ id: number; ts: number; platform: string; status: string }>;
  const ownSet = new Set(own);
  return rows.map((r) => {
    const cites = db.prepare("SELECT domain FROM citations WHERE run_id = ?").all(r.id) as Array<{ domain: string }>;
    const domains = cites.map((c) => c.domain);
    return {
      ts: r.ts,
      platform: r.platform,
      status: r.status,
      cited_own: domains.some((d) => ownSet.has(d)),
      all_domains: domains,
    };
  });
}

export function costSummary(db: DB, sinceTs: number): { total_cents: number; by_provider: Array<{ provider: string; cents: number; calls: number }> } {
  const byProvider = db.prepare(
    `SELECT provider, COALESCE(SUM(cost_cents), 0) AS cents, COUNT(*) AS calls
     FROM cost_events WHERE ts >= ?
     GROUP BY provider
     ORDER BY cents DESC`,
  ).all(sinceTs) as Array<{ provider: string; cents: number; calls: number }>;
  const total = byProvider.reduce((acc, r) => acc + (r.cents ?? 0), 0);
  return { total_cents: total, by_provider: byProvider };
}

export function costByPlatform(db: DB, sinceTs: number): Array<{ platform: string | null; cents: number; calls: number }> {
  return db.prepare(
    `SELECT json_extract(metadata, '$.platform') AS platform,
            COALESCE(SUM(cost_cents), 0) AS cents,
            COUNT(*) AS calls
     FROM cost_events
     WHERE ts >= ? AND metadata IS NOT NULL
     GROUP BY platform
     ORDER BY cents DESC`,
  ).all(sinceTs) as Array<{ platform: string | null; cents: number; calls: number }>;
}

export function costByQuery(db: DB, sinceTs: number): Array<{ query: string; cents: number; calls: number }> {
  return db.prepare(
    `SELECT r.query_text AS query,
            COALESCE(SUM(c.cost_cents), 0) AS cents,
            COUNT(*) AS calls
     FROM cost_events c
     JOIN runs r ON r.id = c.run_id
     WHERE c.ts >= ?
     GROUP BY r.query_text
     ORDER BY cents DESC`,
  ).all(sinceTs) as Array<{ query: string; cents: number; calls: number }>;
}

export function exportRuns(db: DB): Array<{ id: number; ts: number; query_text: string; platform: string; status: string; cited_domains: string | null }> {
  return db.prepare(
    `SELECT r.id, r.ts, r.query_text, r.platform, r.status,
            (SELECT GROUP_CONCAT(c.domain, ', ') FROM citations c WHERE c.run_id = r.id) AS cited_domains
     FROM runs r
     ORDER BY r.ts DESC`,
  ).all() as Array<{ id: number; ts: number; query_text: string; platform: string; status: string; cited_domains: string | null }>;
}

export function counts(db: DB): { queries: number; domains: number; runs: number } {
  return {
    queries: (db.prepare("SELECT COUNT(*) AS n FROM queries").get() as { n: number }).n,
    domains: (db.prepare("SELECT COUNT(*) AS n FROM domains").get() as { n: number }).n,
    runs: (db.prepare("SELECT COUNT(*) AS n FROM runs").get() as { n: number }).n,
  };
}

export function monthSpendCents(db: DB): number {
  const now = new Date();
  const start = Math.floor(new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1)).getTime() / 1000);
  const row = db.prepare("SELECT COALESCE(SUM(cost_cents), 0) AS c FROM cost_events WHERE ts >= ?").get(start) as { c: number };
  return row.c ?? 0;
}
