---
name: keyword-data
description: DataForSEO keyword research for SEO and content planning. Get search volume, search intent, keyword difficulty, CPC, and keyword suggestions. Use for keyword research, content planning, and SEO strategy. Supports --dry-run to preview costs before executing. Triggers on "keyword research", "search volume", "keyword difficulty", "CPC for", "keyword ideas for", "keyword suggestions", "long-tail keywords", "what do people search for", "search intent for", or "SEO opportunity for [topic]".
---

# Keyword Data (DataForSEO)

Keyword research CLI using DataForSEO APIs for search volume, search intent, keyword difficulty, and competitive data. `suggestions` and `related` commands use clickstream-refined volumes for more accurate per-keyword data (especially for niche terms). `volume` uses Google Ads for broad coverage.

**Setup:** Set the `DATAFORSEO_API_KEY` environment variable. The value is the base64 encoding of your DataForSEO `login:password` pair (it is sent as an HTTP Basic auth header):

```bash
echo -n 'login:pass' | base64
```

API calls retry automatically on transient errors (HTTP 429/503/504): 3 attempts, 2s/4s backoff. Shared client code is in `dataforseo.py`, synced from `scripts/shared/dataforseo.py` in the repo — edit the canonical copy, not the synced one.

## CLI Location

```
<skill-dir>
```

## Cost-Efficient Research Workflow

**CRITICAL: The `volume` command costs $0.075 FLAT regardless of keyword count (1 to 1000).**

| Approach | Keywords | API Calls | Cost |
|----------|----------|-----------|------|
| ❌ Bad: Individual calls | 50 | 50 | ~$3.75 |
| ✅ Good: Discovery + batch | 500+ | 5 | ~$0.25 |

### Complete Research Session Example

```bash
# 1. Run multiple discovery calls (~$0.02-0.04 each, with clickstream volumes)
cd <skill-dir>
uv run python cli.py suggestions "insolvency" --limit 100
uv run python cli.py suggestions "liquidation" --limit 100
uv run python cli.py suggestions "bankruptcy" --limit 100
uv run python cli.py related "voluntary administration" --limit 50

# 2. Combine all discovered keywords
uv run python analyze.py combine > /tmp/all_keywords.txt

# 3. Find keywords we don't have volume for yet
uv run python analyze.py find-new /tmp/all_keywords.txt

# 4. Batch volume lookup (ONE call for all keywords = $0.075)
cat /tmp/all_keywords.txt | tr '\n' '\0' | xargs -0 uv run python cli.py volume

# 5. Generate report
uv run python analyze.py report results/volume_*.csv -o report.md
```

**Estimated cost for 500+ keywords: ~$0.25-0.50**

---

## Commands

### Research Commands (cli.py)

#### Check balance (FREE)
```bash
cd <skill-dir> && uv run python cli.py balance
```

#### Show cost estimates
```bash
cd <skill-dir> && uv run python cli.py costs
```

#### Get search volume + intent + CPC (~$0.077 for up to 1000 keywords)
```bash
cd <skill-dir> && uv run python cli.py volume "keyword1" "keyword2" "keyword3"
cd <skill-dir> && uv run python cli.py volume -d "keyword1"  # with difficulty
cd <skill-dir> && uv run python cli.py volume --no-intent "keyword1"  # skip intent
```

Search intent is included by default (informational, transactional, commercial, navigational).

#### Get keyword suggestions (~$0.02-0.04, includes clickstream-refined volumes)
```bash
cd <skill-dir> && uv run python cli.py suggestions "seed keyword" --limit 100
```

#### Get related keywords (~$0.02-0.04, includes clickstream-refined volumes)
```bash
cd <skill-dir> && uv run python cli.py related "keyword"
```

### Analysis Commands (analyze.py)

#### List result files
```bash
cd <skill-dir> && uv run python analyze.py list-files
```

#### Summarize volume results
```bash
cd <skill-dir> && uv run python analyze.py summary results/volume_*.csv --min-volume 10
```

#### Combine suggestion files
```bash
cd <skill-dir> && uv run python analyze.py combine
```

#### Find new keywords not in existing data
```bash
cd <skill-dir> && uv run python analyze.py find-new new_keywords.txt -e results/volume_existing.csv
```

#### Generate markdown report
```bash
cd <skill-dir> && uv run python analyze.py report results/volume_*.csv -o report.md
```

---

## Auto-Save

All results are automatically saved to:
```
<skill-dir>/results/
```

Filenames: `{command}_{seed}_{timestamp}.csv`

Examples:
- `volume_liquidator_2026-02-05_112358.csv`
- `suggestions_insolvency_2026-02-05_113045.csv`
- `related_voluntary-administration_2026-02-05_114522.csv`

This ensures data is never lost if the chat session ends.

---

## Dry Run Mode

**Use `--dry-run` to preview costs before executing:**

```bash
cd <skill-dir> && uv run python cli.py volume --dry-run "keyword1" "keyword2"
```

This shows:
- Action being taken
- Request details
- Estimated cost
- Current balance
- Balance after call
- Confirmation prompt

---

## Filtering Results

Filter `suggestions` and `related` results server-side:

```bash
# Keywords containing "definition"
uv run python cli.py suggestions "insolvency" --filter "keyword" "like" "%definition%"

# Question keywords
uv run python cli.py suggestions "insolvency" --filter "keyword" "regex" "(how|what|when)"

# Volume > 100
uv run python cli.py suggestions "software" --location 2840 --filter "keyword_info.search_volume" ">" "100"
```

### Filter Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `like` | SQL LIKE pattern | `%software%` |
| `regex` | Regular expression | `(how\|what)` |
| `>`, `<`, `>=`, `<=` | Numeric comparison | `100` |
| `=`, `<>` | Equals / not equals | `LOW` |

---

## Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview cost before executing |
| `--location` | Location code (default: 2036 = Australia) |
| `--language` | Language code (default: en) |
| `--output` / `-o` | Save results to CSV file |
| `--limit` | Max results for suggestions/related |
| `--filter` | Server-side filter (field operator value) |
| `-d` / `--with-difficulty` | Include keyword difficulty scores |
| `--no-intent` | Skip search intent classification (saves ~$0.001) |

---

## Cost Reference

| Command | Cost |
|---------|------|
| `volume` (up to 1000 keywords) | $0.075 + $0.001 (intent) |
| `volume -d` | +$0.01 + $0.0001/keyword |
| `volume --no-intent` | $0.075 (skip intent) |
| `suggestions` (+ clickstream) | $0.02 + $0.0002/result |
| `related` (+ clickstream) | $0.02 + $0.0002/result |
| `balance` | FREE |
| `costs` | FREE |
| `analyze.py *` | FREE (local) |

---

## Common Locations

| Code | Country |
|------|---------|
| 2036 | Australia |
| 2840 | United States |
| 2826 | United Kingdom |
| 2124 | Canada |

---

## Output Fields

| Field | Description |
|-------|-------------|
| keyword | The search term |
| search_volume | Monthly search volume |
| keyword_difficulty | Difficulty to rank (0-100) |
| intent | Primary search intent (informational/transactional/commercial/navigational) |
| intent_prob | Confidence of primary intent (0-1) |
| secondary_intent | Secondary intent if present |
| cpc | Cost per click in Google Ads |
| competition | Competition level (LOW/MEDIUM/HIGH) |

---

## Python API (for custom scripts)

```python
from analyze import (
    extract_keywords,
    combine_suggestion_files,
    find_new_keywords,
    filter_keywords,
    summarize_volume,
    categorize_keywords,
    generate_report,
)

# Extract keywords from CSV
keywords = extract_keywords("results/suggestions_insolvency.csv")

# Combine all suggestion files
all_keywords = combine_suggestion_files("suggestions_*.csv")

# Find keywords not in existing volume data
new_keywords = find_new_keywords(discovered_keywords, "results/volume_existing.csv")

# Filter out irrelevant keywords (default excludes non-AU geographic terms)
filtered = filter_keywords(keywords, exclude_patterns=["phoenix", "california"])

# Get summary with min volume threshold
summary = summarize_volume("results/volume_batch.csv", min_volume=10)

# Categorize by topic
categories = categorize_keywords([(kw, vol) for kw, vol in keywords_with_volume])

# Generate markdown report
report = generate_report("results/volume_batch.csv", "report.md")
```

---

## Example: Full Research Session

Research Australian insolvency keywords efficiently:

```bash
cd <skill-dir>

# Check balance first
uv run python cli.py balance

# Discovery phase (~$0.40 for 10 calls, with clickstream volumes)
for seed in "insolvency" "liquidation" "bankruptcy" "voluntary administration" \
            "deed of company arrangement" "winding up" "receiver" "safe harbour" \
            "director penalty notice" "proof of debt"; do
    uv run python cli.py suggestions "$seed" --limit 100
done

# Combine and deduplicate
uv run python analyze.py combine > /tmp/keywords.txt

# Optional: filter irrelevant terms
# (analyze.py has default filters for non-AU geographic terms)

# Batch volume lookup ($0.075)
cat /tmp/keywords.txt | tr '\n' '\0' | xargs -0 uv run python cli.py volume

# Generate report
uv run python analyze.py report results/volume_*.csv -o keyword_report.md
uv run python analyze.py summary results/volume_*.csv --min-volume 50
```

**Total cost: ~$0.50 for 1000+ keywords**
