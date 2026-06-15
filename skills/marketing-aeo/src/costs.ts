// Provider rate tables. Update when prices change.

export const FIRECRAWL_PLANS: Record<string, { monthlyUsd: number; credits: number }> = {
  hobby: { monthlyUsd: 30, credits: 3000 }, // ~$0.0100/credit
  standard: { monthlyUsd: 100, credits: 100000 }, // ~$0.0010/credit
  growth: { monthlyUsd: 500, credits: 500000 },
};

// Gemini 2.5 Flash (2026-05 rates).
export const GEMINI_FLASH_INPUT_PER_M = 0.075;
export const GEMINI_FLASH_OUTPUT_PER_M = 0.30;

// Anthropic Haiku 4.5.
export const ANTHROPIC_HAIKU_INPUT_PER_M = 1.00;
export const ANTHROPIC_HAIKU_OUTPUT_PER_M = 5.00;
// Web search: charged per search performed by the model.
export const ANTHROPIC_WEB_SEARCH_PER_CALL = 0.01; // $10 per 1k

export function firecrawlCreditCents(plan = "hobby"): number {
  const p = FIRECRAWL_PLANS[plan] ?? FIRECRAWL_PLANS.hobby!;
  return (p.monthlyUsd / p.credits) * 100;
}

export function firecrawlScrapeCents(plan = "hobby"): number {
  return firecrawlCreditCents(plan) * 1; // 1 credit per basic scrape
}

export function geminiFlashCents(inputTokens: number, outputTokens: number): number {
  const dollars =
    (inputTokens / 1_000_000) * GEMINI_FLASH_INPUT_PER_M +
    (outputTokens / 1_000_000) * GEMINI_FLASH_OUTPUT_PER_M;
  return dollars * 100;
}

export function anthropicHaikuCents(
  inputTokens: number,
  outputTokens: number,
  webSearchCalls = 0,
): number {
  const dollars =
    (inputTokens / 1_000_000) * ANTHROPIC_HAIKU_INPUT_PER_M +
    (outputTokens / 1_000_000) * ANTHROPIC_HAIKU_OUTPUT_PER_M +
    webSearchCalls * ANTHROPIC_WEB_SEARCH_PER_CALL;
  return dollars * 100;
}
