---
name: marketing-serp
description: DataForSEO SERP analysis for geo-targeted search result analysis. See who ranks for keywords in specific locations (Australia, US, UK, etc.), identify content gaps, analyze SERP features (featured snippets, PAA), and find competitor domains. Supports --dry-run to preview costs. Triggers on "who ranks for", "SERP analysis", "search results for", "Google results for [keyword]", "competitors for [keyword]", "featured snippet", "people also ask", "ranking domains", "top 10 for", or "SERP features".
---

# SERP Data (DataForSEO)

Geo-targeted SERP analysis CLI using DataForSEO APIs. Unlike WebFetch, this provides accurate local search results (e.g., Australia-specific rankings).

**Setup:** Set the `DATAFORSEO_API_KEY` environment variable. The value is the base64 encoding of your DataForSEO `login:password` pair (it is sent as an HTTP Basic auth header):

```bash
echo -n 'login:pass' | base64
```

API calls retry automatically on transient errors (HTTP 429/503/504): 3 attempts, 2s/4s backoff. Shared client code is in `dataforseo.py`, synced from `scripts/shared/dataforseo.py` in the repo — edit the canonical copy, not the synced one.

## CLI Location

```
<skill-dir>
```

## Why This Skill?

WebFetch cannot search by local geography. This skill solves that by using DataForSEO's SERP API to:
- Get accurate Australian SERP rankings
- See who ranks for target keywords
- Identify content gaps and opportunities
- Analyze SERP features (featured snippets, PAA)

---

## Quick Start

```bash
cd <skill-dir>

# Check balance first
uv run python cli.py balance

# See who ranks for a keyword in Australia
uv run python cli.py serp "voidable transaction australia" --location au

# Analyze multiple keywords to find top competitors
uv run python cli.py bulk "liquidator" "doca" "voluntary administration"

# Find SERP feature opportunities
uv run python cli.py features "what is voluntary administration"

# Find content gaps (where you don't rank)
uv run python cli.py gaps example-site.com "liquidator" "rocap form" "form 507"
```

---

## Commands

### 1. `serp` - Single keyword SERP analysis

Get organic rankings and SERP features for one keyword.

```bash
cd <skill-dir>

# Basic usage (Australia default)
uv run python cli.py serp "rocap form"

# Specify location
uv run python cli.py serp "liquidator" --location au
uv run python cli.py serp "liquidator" --location us

# Get more results
uv run python cli.py serp "voluntary administration" --depth 20

# Include all SERP features (advanced)
uv run python cli.py serp "unfair preference" -a

# Save raw JSON for detailed analysis
uv run python cli.py serp "form 507" -j
```

**Cost:** ~$0.003 per 10 results

---

### 2. `bulk` - Multi-keyword competitor analysis

Analyze multiple keywords and identify which domains rank across them.

```bash
cd <skill-dir>

# Analyze competitor landscape
uv run python cli.py bulk "liquidator" "voluntary administration" "doca" "winding up"

# Check form-related keywords
uv run python cli.py bulk "form 507" "rocap form" "asic forms" "form 505"
```

**Output:** Competitor ranking summary showing domains that rank for multiple keywords.

**Cost:** ~$0.003 per keyword

---

### 3. `features` - SERP feature opportunities

Deep analysis of SERP features including featured snippets, People Also Ask, related searches.

```bash
cd <skill-dir>

# Analyze SERP features
uv run python cli.py features "what is voluntary administration"

# Find PAA questions to target
uv run python cli.py features "voidable transaction australia"

# Check for featured snippet opportunity
uv run python cli.py features "relation back day meaning"
```

**Output:**
- Featured snippet holder (if any)
- People Also Ask questions
- Related searches
- Knowledge graph presence
- Optimization recommendations

**Cost:** ~$0.004 per 10 results

---

### 4. `gaps` - Content gap analysis

Find keywords where a target domain doesn't rank but competitors do.

```bash
cd <skill-dir>

# Find where example-site doesn't rank
uv run python cli.py gaps example-site.com "liquidator" "doca" "form 507" "rocap"

# Analyze competitor's gaps
uv run python cli.py gaps svpartners.com.au "voidable transaction" "unfair preference"
```

**Output:**
- Keywords where domain doesn't rank in top 20
- Current rankings for keywords where domain does rank
- Top competitor for each gap keyword

**Cost:** ~$0.003 per keyword

---

### 5. `balance` - Check account balance (FREE)

```bash
cd <skill-dir> && uv run python cli.py balance
```

### 6. `costs` - Show cost estimates (FREE)

```bash
cd <skill-dir> && uv run python cli.py costs
```

### 7. `locations` - List location shortcuts (FREE)

```bash
cd <skill-dir> && uv run python cli.py locations
```

---

## Options

| Option | Description |
|--------|-------------|
| `--location`, `-l` | Location shortcut (au, us, uk, ca, nz) or code |
| `--depth`, `-d` | Number of results (default: 10 or 20) |
| `--device` | desktop or mobile (default: desktop) |
| `--advanced`, `-a` | Include all SERP features |
| `--output`, `-o` | Save results to CSV file |
| `--json-output`, `-j` | Also save raw JSON response |
| `--dry-run` | Preview cost before executing |

---

## Location Shortcuts

| Shortcut | Code | Country |
|----------|------|---------|
| au | 2036 | Australia |
| us | 2840 | United States |
| uk | 2826 | United Kingdom |
| ca | 2124 | Canada |
| nz | 2554 | New Zealand |

---

## Cost Reference

| Command | Cost |
|---------|------|
| `serp` (regular) | $0.003 per 10 results |
| `serp -a` (advanced) | $0.004 per 10 results |
| `bulk` | $0.003 per keyword (10 results) |
| `features` | $0.004 per 10 results |
| `gaps` | $0.003 per keyword |
| `balance`, `costs`, `locations` | FREE |

**Example session costs:**
- Single keyword analysis: ~$0.003
- 10 keyword competitor scan: ~$0.03
- 50 keyword gap analysis: ~$0.15

---

## Auto-Save

All results are automatically saved to:
```
<skill-dir>/results/
```

Filenames: `{command}_{keyword}_{location}_{timestamp}.csv`

Examples:
- `serp_voidable-transaction-australia_au_2026-02-05_143022.csv`
- `bulk_liquidator_au_2026-02-05_144155.csv`
- `gaps_example-site.com_au_2026-02-05_145230.csv`

---

## Example: Australian Insolvency SERP Research

```bash
cd <skill-dir>

# 1. Check balance
uv run python cli.py balance

# 2. Scan competitor landscape for high-volume terms (~$0.03)
uv run python cli.py bulk "liquidator" "voluntary administration" "doca" "winding up" "insolvent trading"

# 3. Check specific keyword SERPs (~$0.01)
uv run python cli.py serp "rocap form" --location au -a
uv run python cli.py serp "form 507 asic" --location au -a

# 4. Find SERP feature opportunities (~$0.01)
uv run python cli.py features "what is a voidable transaction"
uv run python cli.py features "voluntary administration meaning"

# 5. Analyze content gaps (~$0.06)
uv run python cli.py gaps example-site.com \
  "liquidator" "doca" "voluntary administration" \
  "form 507" "rocap form" "unfair preference" \
  "insolvent trading" "winding up" "relation back day"

# Total: ~$0.11 for comprehensive SERP analysis
```

---

## Workflow: SERP Analysis for Content Strategy

### Step 1: Competitor Discovery
```bash
# Find who dominates your target keywords
uv run python cli.py bulk "liquidator" "voluntary administration" "doca" \
  "winding up" "insolvent trading" "rocap form" "form 507"
```

### Step 2: SERP Feature Opportunities
```bash
# Check for featured snippet opportunities on question keywords
uv run python cli.py features "what is voluntary administration"
uv run python cli.py features "what is a voidable transaction"
uv run python cli.py features "how to fill form 507"
```

### Step 3: Gap Analysis
```bash
# Find keywords where you don't rank
uv run python cli.py gaps yourdomain.com [list of target keywords]
```

### Step 4: Update Strategy Document
Use results to update SERP Analysis section in STRATEGY.md with actual Australian ranking data.

---

## Integration with marketing-keyword-data Skill

Use both skills together for complete SEO research:

```bash
# 1. Discover keywords (marketing-keyword-data skill)
cd <marketing-keyword-data-skill-dir>
uv run python cli.py suggestions "insolvency" --limit 100

# 2. Get volume data (marketing-keyword-data skill)
uv run python cli.py volume "liquidator" "doca" "voluntary administration"

# 3. Analyze SERPs for high-volume terms (serp-data skill)
cd <skill-dir>
uv run python cli.py bulk "liquidator" "doca" "voluntary administration"

# 4. Deep-dive on opportunities
uv run python cli.py features "liquidator"
uv run python cli.py gaps example-site.com "liquidator" "doca"
```

---

## Output Fields

### serp/bulk
| Field | Description |
|-------|-------------|
| rank | Position in SERP (1 = top) |
| domain | Ranking domain |
| title | Page title |
| url | Full URL |
| description | Meta description snippet |

### features
Returns structured data for:
- Featured snippets (domain, title, content)
- People Also Ask questions
- Related searches
- Knowledge graph
- Organic rankings

### gaps
| Field | Description |
|-------|-------------|
| keyword | Search term |
| domain_rank | Your rank (null if not ranking) |
| top_competitor | Domain ranking #1 |
| top_rank | Competitor's rank |
