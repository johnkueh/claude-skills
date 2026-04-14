---
name: exa
description: Search the web and scrape page contents using Exa API. Find URLs via neural/keyword search, then extract clean text, highlights, and summaries. Use when the user wants to search the web, find pages, scrape content, extract text, or fetch articles. Triggers on "search for", "find pages about", "scrape", "extract content", "get page text", "fetch article", or "pull content from URL".
---

# Exa

Search the web and scrape pages using the Exa API. Neural search finds relevant URLs; scrape extracts clean content. Pay-per-use at $0.001/result — no subscription.

**Setup:** Set `EXA_API_KEY` environment variable with your Exa API key.

**Fallback:** If Exa scrape returns thin/incomplete content (especially paywalled journals like NEJM or JS-heavy SPAs like ClinicalTrials.gov), use the `firecrawl` skill instead.

## Commands

Run all commands from this skill's base directory (shown above).

### Search the web

```bash
uv run python cli.py search "insolvency case law Australia"
```

### Search with filters

```bash
uv run python cli.py search "voidable transactions" --category news -n 20
uv run python cli.py search "s588FF" --include-domains jade.io,austlii.edu.au
uv run python cli.py search "bankruptcy reform" --start-date 2024-01-01
```

### Search and fetch content in one call

```bash
uv run python cli.py search "liquidator duties" --text
uv run python cli.py search "preference claims" --text --highlights
uv run python cli.py search "public examination" --summary "Extract the key legal ruling"
```

### Search dry run

```bash
uv run python cli.py search --dry-run "insolvency law" -n 20
```

### Scrape page text

```bash
uv run python cli.py scrape "https://example.com/page"
```

### Scrape multiple URLs

```bash
uv run python cli.py scrape "https://url1.com" "https://url2.com" "https://url3.com"
```

### Get highlights (key snippets)

```bash
uv run python cli.py scrape "https://example.com" --highlights
uv run python cli.py scrape "https://example.com" --highlights --query "key financial details"
```

### Get structured summary

```bash
uv run python cli.py scrape "https://example.com" --summary "Extract the main argument"
```

### Limit text length

```bash
uv run python cli.py scrape "https://example.com" --max-chars 5000
```

### Force fresh crawl (bypass cache)

```bash
uv run python cli.py scrape "https://example.com" --fresh
```

### Batch scrape from file

```bash
uv run python cli.py batch urls.txt
uv run python cli.py batch urls.txt --highlights --query "case law details"
uv run python cli.py batch urls.txt --summary "Summarize the legal ruling"
```

### Dry run (preview cost)

```bash
uv run python cli.py scrape --dry-run "https://url1.com" "https://url2.com"
```

---

## Auto-Save

All results are automatically saved to `results/` within this skill's directory.

Filenames: `scrape_{domain}_{timestamp}.json`

---

## Output

Returns JSON with full page content:

```json
{
  "results": [
    {
      "url": "https://example.com/page",
      "title": "Page Title",
      "author": "Author Name",
      "publishedDate": "2024-01-15",
      "text": "Full page text content...",
      "highlights": ["Key snippet 1", "Key snippet 2"],
      "summary": "Structured summary if requested"
    }
  ],
  "cost": 0.001,
  "pages": 1
}
```

---

## Cost Reference

| Feature | Cost per result |
|---------|----------------|
| Search (URLs only) | $0.001 |
| Text content | $0.001 |
| Highlights | +$0.001 |
| Summary | +$0.001 |
| Search + Text + Highlights + Summary | $0.004 |

**Examples:**
- Search 10 results, URLs only: $0.01
- Search 10 results + text: $0.02
- Scrape 100 pages, text only: $0.10
- Scrape 50 pages, text + highlights: $0.10

---

## Search Options

| Option | Description |
|--------|-------------|
| `-n` / `--num-results` | Number of results (default: 10, max: 100) |
| `--type` | Search type: `auto`, `neural`, `keyword` |
| `--category` | Focus: `company`, `research paper`, `news`, `tweet`, `personal site`, `financial report`, `people` |
| `--include-domains` | Comma-separated domains to include |
| `--exclude-domains` | Comma-separated domains to exclude |
| `--start-date` | Min publish date (YYYY-MM-DD) |
| `--end-date` | Max publish date (YYYY-MM-DD) |
| `--include-text` | Comma-separated strings that must appear in results |
| `--exclude-text` | Comma-separated strings that must not appear in results |
| `--text` | Also fetch page text content |
| `--highlights` | Also fetch key snippets |
| `--summary` | Also fetch summary with this prompt |
| `--max-chars` | Limit text length per result |
| `--dry-run` | Preview cost before executing |
| `--output` / `-o` | Save results to specific file |

## Scrape Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview cost before executing |
| `--highlights` | Extract key snippets from each page |
| `--query` | Guide highlight/summary extraction (e.g., "financial details") |
| `--summary` | Get a summary with this prompt |
| `--max-chars` | Limit text length per page |
| `--fresh` | Force live crawl, bypass cache |
| `--output` / `-o` | Save results to specific file |
| `--no-text` | Exclude full text (useful with --highlights or --summary) |
