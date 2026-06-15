// Per-platform scraping. Each returns raw text + cost record.

import { firecrawlScrapeCents, anthropicHaikuCents } from "./costs.ts";

export interface ScrapeResult {
  text: string;
  platform: string;
  costCents: number;
  provider: "firecrawl" | "dataforseo" | "anthropic" | string;
  operation: string;
  inputTokens?: number;
  outputTokens?: number;
  credits?: number;
  webSearchCalls?: number;
  error?: string;
  metadata?: Record<string, unknown>;
}

const FIRECRAWL_API = "https://api.firecrawl.dev/v1/scrape";
const DATAFORSEO_API = "https://api.dataforseo.com/v3/serp/google/organic/live/advanced";

async function firecrawlScrape(url: string, waitForMs: number): Promise<{ text: string; error?: string }> {
  const key = process.env.FIRECRAWL_API_KEY;
  if (!key) return { text: "", error: "FIRECRAWL_API_KEY not set" };
  // Firecrawl requires timeout >= 2 * waitFor — allow generous headroom.
  const timeoutMs = Math.max(waitForMs * 3, 45000);
  try {
    const res = await fetch(FIRECRAWL_API, {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify({ url, formats: ["markdown"], onlyMainContent: true, waitFor: waitForMs, timeout: timeoutMs }),
    });
    if (!res.ok) {
      return { text: "", error: `firecrawl: HTTP ${res.status} ${await res.text().catch(() => "")}` };
    }
    const data = (await res.json()) as { data?: { markdown?: string } };
    return { text: data.data?.markdown ?? "" };
  } catch (e) {
    return { text: "", error: `firecrawl: ${(e as Error).message}` };
  }
}

// Firecrawl frequently times out rendering the ChatGPT/Perplexity chat UIs, which
// would zero out a run. When that happens, fall back to the reliable DataForSEO
// Google AI Overview citation set for the same query so the run still yields an
// AI-citation signal. Labelled as a fallback (different surface — Google's AI
// answer, not the native chatbot) so it isn't mistaken for a true ChatGPT cite.
// Disable with AEO_DISABLE_DATAFORSEO_FALLBACK=1.
async function dataForSeoFallback(platform: string, query: string, firecrawlError: string): Promise<ScrapeResult> {
  const aio = await scrapeGoogleAIOverview(query);
  return {
    ...aio,
    platform,
    operation: "ai_overview_fallback",
    metadata: { platform, fallback_provider: "dataforseo-google-ai", firecrawl_error: firecrawlError },
  };
}

export async function scrapeChatGPT(query: string, plan = "hobby"): Promise<ScrapeResult> {
  const url = `https://chatgpt.com/?q=${encodeURIComponent(query)}`;
  const { text, error } = await firecrawlScrape(url, 18000);
  if ((error || !text.trim()) && process.env.AEO_DISABLE_DATAFORSEO_FALLBACK !== "1") {
    return dataForSeoFallback("chatgpt", query, error ?? "empty result");
  }
  return {
    text,
    platform: "chatgpt",
    costCents: firecrawlScrapeCents(plan),
    provider: "firecrawl",
    operation: "scrape",
    credits: 1,
    error,
    metadata: { platform: "chatgpt" },
  };
}

export async function scrapePerplexity(query: string, plan = "hobby"): Promise<ScrapeResult> {
  const url = `https://www.perplexity.ai/search?q=${encodeURIComponent(query)}`;
  const { text, error } = await firecrawlScrape(url, 12000);
  if ((error || !text.trim()) && process.env.AEO_DISABLE_DATAFORSEO_FALLBACK !== "1") {
    return dataForSeoFallback("perplexity", query, error ?? "empty result");
  }
  return {
    text,
    platform: "perplexity",
    costCents: firecrawlScrapeCents(plan),
    provider: "firecrawl",
    operation: "scrape",
    credits: 1,
    error,
    metadata: { platform: "perplexity" },
  };
}

interface DataForSeoItem {
  type?: string;
  markdown?: string;
  references?: Array<{ domain?: string; url?: string; title?: string }>;
}

export async function scrapeGoogleAIOverview(query: string, locationCode = 2840): Promise<ScrapeResult> {
  const key = process.env.DATAFORSEO_API_KEY;
  if (!key) {
    return {
      text: "",
      platform: "google-ai",
      costCents: 0,
      provider: "dataforseo",
      operation: "ai_overview",
      error: "DATAFORSEO_API_KEY not set",
      metadata: { platform: "google-ai" },
    };
  }
  try {
    const res = await fetch(DATAFORSEO_API, {
      method: "POST",
      headers: { Authorization: `Basic ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify([{
        keyword: query,
        location_code: locationCode,
        language_code: "en",
        device: "desktop",
        load_async_ai_overview: true,
      }]),
    });
    if (!res.ok) {
      return {
        text: "",
        platform: "google-ai",
        costCents: 0,
        provider: "dataforseo",
        operation: "ai_overview",
        error: `dataforseo: HTTP ${res.status}`,
        metadata: { platform: "google-ai" },
      };
    }
    const data = (await res.json()) as {
      cost?: number;
      tasks?: Array<{ result?: Array<{ items?: DataForSeoItem[] }> }>;
    };
    const costDollars = data.cost ?? 0;
    let text = "";
    let aiPresent = false;
    for (const task of data.tasks ?? []) {
      for (const result of task.result ?? []) {
        for (const item of result.items ?? []) {
          if (item.type === "ai_overview") {
            aiPresent = true;
            if (item.markdown) text += item.markdown + "\n\n";
            for (const ref of item.references ?? []) {
              text += `- ${ref.title ?? ""} — ${ref.url ?? ""}\n`;
            }
          }
        }
      }
    }
    return {
      text,
      platform: "google-ai",
      costCents: costDollars * 100,
      provider: "dataforseo",
      operation: "ai_overview",
      metadata: { platform: "google-ai", ai_overview_present: aiPresent },
    };
  } catch (e) {
    return {
      text: "",
      platform: "google-ai",
      costCents: 0,
      provider: "dataforseo",
      operation: "ai_overview",
      error: `dataforseo: ${(e as Error).message}`,
      metadata: { platform: "google-ai" },
    };
  }
}

export async function scrapeClaude(query: string, model = "claude-haiku-4-5"): Promise<ScrapeResult> {
  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) {
    return {
      text: "",
      platform: "claude",
      costCents: 0,
      provider: "anthropic",
      operation: "web_search",
      error: "ANTHROPIC_API_KEY not set",
      metadata: { platform: "claude" },
    };
  }
  try {
    const { default: Anthropic } = await import("@anthropic-ai/sdk");
    const client = new Anthropic({ apiKey: key });
    const response = await client.messages.create({
      model,
      max_tokens: 2048,
      tools: [{ type: "web_search_20250305", name: "web_search" } as never],
      messages: [{ role: "user", content: query }],
    });
    const parts: string[] = [];
    let webSearchCalls = 0;
    for (const block of response.content) {
      const btype = (block as { type?: string }).type;
      if (btype === "text") {
        parts.push((block as { text?: string }).text ?? "");
      } else if (btype === "web_search_tool_result") {
        webSearchCalls += 1;
        const results = (block as { content?: Array<{ type?: string; title?: string; url?: string }> }).content ?? [];
        for (const r of results) {
          if (r.type === "web_search_result") {
            parts.push(`\n- [${r.title ?? ""}](${r.url ?? ""})`);
          }
        }
      }
    }
    const text = parts.join("\n");
    const inputTokens = response.usage?.input_tokens ?? 0;
    const outputTokens = response.usage?.output_tokens ?? 0;
    const cents = anthropicHaikuCents(inputTokens, outputTokens, webSearchCalls);
    return {
      text,
      platform: "claude",
      costCents: cents,
      provider: "anthropic",
      operation: "web_search",
      inputTokens,
      outputTokens,
      webSearchCalls,
      metadata: { platform: "claude", model, web_search_calls: webSearchCalls },
    };
  } catch (e) {
    return {
      text: "",
      platform: "claude",
      costCents: 0,
      provider: "anthropic",
      operation: "web_search",
      error: `anthropic: ${(e as Error).message}`,
      metadata: { platform: "claude" },
    };
  }
}

export const SUPPORTED_PLATFORMS = ["chatgpt", "perplexity", "google-ai", "claude"] as const;
export type Platform = (typeof SUPPORTED_PLATFORMS)[number];

export async function scrape(platform: Platform, query: string, firecrawlPlan = "hobby"): Promise<ScrapeResult> {
  switch (platform) {
    case "chatgpt": return scrapeChatGPT(query, firecrawlPlan);
    case "perplexity": return scrapePerplexity(query, firecrawlPlan);
    case "google-ai": return scrapeGoogleAIOverview(query);
    case "claude": return scrapeClaude(query);
  }
}
