// Gemini 2.5 Flash structured extraction. Falls back to regex URL extraction if no key.

import { geminiFlashCents } from "./costs.ts";

export interface Extracted {
  responseText: string;
  aiUsedWebSearch: boolean;
  responseStructure: "list" | "paragraphs" | "table" | "mixed";
  citations: Array<{ url: string; domain: string; anchor_text?: string | null; position?: number | null }>;
  inputTokens: number;
  outputTokens: number;
  costCents: number;
  error?: string;
}

const SCHEMA = {
  type: "object",
  properties: {
    response_text: { type: "string", description: "The actual AI response answer, cleaned of UI chrome." },
    ai_used_web_search: { type: "boolean", description: "True if the AI cited sources or appears to have used web search." },
    response_structure: {
      type: "string",
      enum: ["list", "paragraphs", "table", "mixed"],
      description: "Dominant structure of the answer.",
    },
    citations: {
      type: "array",
      items: {
        type: "object",
        properties: {
          url: { type: "string" },
          domain: { type: "string", description: "Bare domain, e.g. 'glp3.wiki' — strip www. and protocol." },
          anchor_text: { type: "string", description: "Text near the citation (link title or first ~60 chars of the cited claim)." },
          position: { type: "integer", description: "1-indexed order of citation in the response." },
        },
        required: ["url", "domain", "position"],
      },
    },
  },
  required: ["response_text", "ai_used_web_search", "response_structure", "citations"],
};

const PROMPT = `Extract structured information from this scraped AI chatbot response.

The scrape may include UI chrome (cookie banners, navigation, share buttons, "ChatGPT can make mistakes" warnings). Focus on the actual answer content.

Extract:
1. The clean response text (just the AI's answer — strip UI chrome).
2. Whether the AI used web search (true if it cited URLs/sources, false if it answered from training alone).
3. The dominant response structure (list, paragraphs, table, or mixed).
4. Every URL citation in the response, with the domain (bare, no www. or protocol) and position (1-indexed order).

For domain: 'https://www.example.com/path?utm=x' → 'example.com'.
If no citations are present, return citations: [].
If the scrape is empty or just chrome, set response_text to "" and ai_used_web_search to false.`;

function normalizeDomain(d: string | undefined | null): string {
  if (!d) return "";
  let s = d.toLowerCase().replace(/^https?:\/\//, "").replace(/^www\./, "");
  s = s.split("/")[0] ?? "";
  return s;
}

function fallbackExtract(rawText: string, error?: string): Extracted {
  const urls = rawText.match(/https?:\/\/[^\s\)\]"'<>]+/g) ?? [];
  const seen = new Set<string>();
  const citations: Extracted["citations"] = [];
  for (const u of urls) {
    const cleaned = u.replace(/[.,;:\]\)]+$/, "");
    if (/chatgpt\.com\/|perplexity\.ai\/|openai\.com\/|edge\.perplexity|gstatic\.com|googleapis\.com/.test(cleaned)) continue;
    const m = cleaned.match(/https?:\/\/([^\/]+)/);
    if (!m) continue;
    const domain = normalizeDomain(m[1]);
    const key = `${domain}|${cleaned}`;
    if (seen.has(key)) continue;
    seen.add(key);
    citations.push({ url: cleaned, domain, anchor_text: null, position: citations.length + 1 });
  }
  return {
    responseText: rawText.slice(0, 5000),
    aiUsedWebSearch: citations.length > 0,
    responseStructure: "paragraphs",
    citations,
    inputTokens: 0,
    outputTokens: 0,
    costCents: 0,
    error,
  };
}

export async function extract(rawText: string, platform: string): Promise<Extracted> {
  if (!rawText.trim()) {
    return {
      responseText: "",
      aiUsedWebSearch: false,
      responseStructure: "paragraphs",
      citations: [],
      inputTokens: 0,
      outputTokens: 0,
      costCents: 0,
    };
  }

  const key = process.env.GEMINI_API_KEY;
  if (!key) return fallbackExtract(rawText, "GEMINI_API_KEY not set");

  let GoogleGenAI: typeof import("@google/genai").GoogleGenAI;
  try {
    ({ GoogleGenAI } = await import("@google/genai"));
  } catch (e) {
    return fallbackExtract(rawText, `@google/genai not installed: ${(e as Error).message}`);
  }

  const client = new GoogleGenAI({ apiKey: key });

  try {
    const response = await client.models.generateContent({
      model: "gemini-2.5-flash",
      contents: [{
        role: "user",
        parts: [{
          text: `${PROMPT}\n\nPlatform: ${platform}\n\n--- BEGIN SCRAPE ---\n${rawText.slice(0, 60000)}\n--- END SCRAPE ---`,
        }],
      }],
      config: {
        responseMimeType: "application/json",
        responseSchema: SCHEMA as never,
      },
    });
    const text = response.text ?? "";
    const data = JSON.parse(text) as {
      response_text?: string;
      ai_used_web_search?: boolean;
      response_structure?: Extracted["responseStructure"];
      citations?: Array<{ url?: string; domain?: string; anchor_text?: string; position?: number }>;
    };
    const usage = response.usageMetadata;
    const inputTokens = usage?.promptTokenCount ?? 0;
    const outputTokens = usage?.candidatesTokenCount ?? 0;
    const citations = (data.citations ?? []).map((c) => ({
      url: c.url ?? "",
      domain: normalizeDomain(c.domain),
      anchor_text: c.anchor_text ?? null,
      position: c.position ?? null,
    }));
    return {
      responseText: data.response_text ?? "",
      aiUsedWebSearch: Boolean(data.ai_used_web_search),
      responseStructure: data.response_structure ?? "paragraphs",
      citations,
      inputTokens,
      outputTokens,
      costCents: geminiFlashCents(inputTokens, outputTokens),
    };
  } catch (e) {
    return fallbackExtract(rawText, `gemini: ${(e as Error).message}`);
  }
}
