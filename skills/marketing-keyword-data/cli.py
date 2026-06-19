#!/usr/bin/env python3
"""DataForSEO keyword research CLI for SEO and content planning."""

import csv
import sys

import click
import requests

from dataforseo import api_get, api_post, auto_save, confirm_cost

# Cost estimates per endpoint
COSTS = {
    "google_ads_volume": 0.075,  # per request (up to 1000 keywords)
    "bulk_keyword_difficulty": 0.01,  # base + 0.0001 per keyword
    "search_intent": 0.001,  # base + 0.0001 per keyword (very cheap)
    "keyword_suggestions": 0.02,  # base + 0.0002 per result (2x with clickstream)
    "related_keywords": 0.02,  # base + 0.0002 per result (2x with clickstream)
}


@click.group()
def cli():
    """DataForSEO keyword research CLI."""
    pass


@cli.command()
@click.argument("keywords", nargs=-1, required=True)
@click.option("--location", default="2036", help="Location code (default: 2036 = Australia)")
@click.option("--language", default="en", help="Language code (default: en)")
@click.option("--output", "-o", help="Output CSV file path")
@click.option("--with-difficulty", "-d", is_flag=True, help="Also fetch keyword difficulty (extra API call)")
@click.option("--no-intent", is_flag=True, help="Skip search intent classification (on by default)")
@click.option("--dry-run", is_flag=True, help="Show cost estimate and ask for confirmation")
def volume(keywords: tuple, location: str, language: str, output: str, with_difficulty: bool, no_intent: bool, dry_run: bool):
    """Get search volume, CPC, competition, and search intent for keywords.

    Uses Google Ads API for search volume and advertising metrics.
    Search intent is included by default (very cheap: ~$0.001 per 1000 keywords).
    Add -d flag to also get keyword difficulty scores.
    Add --dry-run to preview cost before executing.

    Example: uv run python cli.py volume "insolvency practitioner" "liquidator"
    Example: uv run python cli.py volume --dry-run "keyword1" "keyword2"
    """
    keyword_list = list(keywords)
    with_intent = not no_intent

    # Calculate estimated cost
    estimated_cost = COSTS["google_ads_volume"]
    if with_intent:
        estimated_cost += COSTS["search_intent"] + (len(keyword_list) * 0.0001)
    if with_difficulty:
        estimated_cost += COSTS["bulk_keyword_difficulty"] + (len(keyword_list) * 0.0001)

    if dry_run:
        details = [
            f"Keywords: {len(keyword_list)}",
            f"Location: {location}",
            f"Language: {language}",
            f"With intent: {with_intent} (default)",
            f"With difficulty: {with_difficulty}",
            f"Output: {output or 'terminal'}",
        ]
        if not confirm_cost("Get search volume data", details, estimated_cost):
            click.echo("❌ Cancelled", err=True)
            return

    click.echo(f"📊 Fetching data for {len(keyword_list)} keywords...", err=True)

    # Get search volume from Google Ads API
    data = [{
        "keywords": keyword_list,
        "location_code": int(location),
        "language_code": language,
    }]

    try:
        result = api_post("keywords_data/google_ads/search_volume/live", data)
    except requests.exceptions.HTTPError as e:
        click.echo(f"❌ API Error: {e}", err=True)
        click.echo(f"Response: {e.response.text}", err=True)
        sys.exit(1)

    if result.get("status_code") != 20000:
        click.echo(f"❌ API Error: {result.get('status_message')}", err=True)
        sys.exit(1)

    tasks = result.get("tasks", [])
    if not tasks or not tasks[0].get("result"):
        click.echo("❌ No results returned", err=True)
        sys.exit(1)

    items = tasks[0]["result"]
    cost = result.get("cost", 0.075)

    # Get keyword difficulty if requested
    kd_map = {}
    if with_difficulty:
        click.echo("📈 Fetching keyword difficulty...", err=True)
        try:
            kd_result = api_post("dataforseo_labs/google/bulk_keyword_difficulty/live", data)
            if kd_result.get("status_code") == 20000:
                kd_tasks = kd_result.get("tasks", [])
                if kd_tasks and kd_tasks[0].get("result"):
                    kd_items = kd_tasks[0]["result"][0].get("items", [])
                    for kd_item in kd_items:
                        kd_map[kd_item.get("keyword", "")] = kd_item.get("keyword_difficulty")
                cost += kd_result.get("cost", 0.01)
        except Exception as e:
            click.echo(f"⚠️ Could not fetch difficulty: {e}", err=True)

    # Get search intent (on by default - very cheap)
    intent_map = {}
    if with_intent:
        click.echo("🎯 Fetching search intent...", err=True)
        try:
            intent_data = [{"keywords": keyword_list, "language_code": language}]
            intent_result = api_post("dataforseo_labs/google/search_intent/live", intent_data)
            if intent_result.get("status_code") == 20000:
                intent_tasks = intent_result.get("tasks", [])
                if intent_tasks and intent_tasks[0].get("result"):
                    intent_items = intent_tasks[0]["result"][0].get("items", [])
                    for intent_item in intent_items:
                        kw = intent_item.get("keyword", "")
                        intent_info = intent_item.get("keyword_intent", {}) or {}
                        secondary = intent_item.get("secondary_keyword_intents") or []
                        intent_map[kw] = {
                            "intent": intent_info.get("label", ""),
                            "intent_prob": intent_info.get("probability", 0),
                            "secondary_intent": secondary[0].get("label", "") if secondary else "",
                        }
                cost += intent_result.get("cost", 0.001)
        except Exception as e:
            click.echo(f"⚠️ Could not fetch intent: {e}", err=True)

    # Format output
    rows = []
    for item in items:
        keyword = item.get("keyword", "")
        intent_info = intent_map.get(keyword, {})
        rows.append({
            "keyword": keyword,
            "search_volume": item.get("search_volume", 0),
            "keyword_difficulty": kd_map.get(keyword, ""),
            "intent": intent_info.get("intent", ""),
            "intent_prob": intent_info.get("intent_prob", ""),
            "secondary_intent": intent_info.get("secondary_intent", ""),
            "cpc": item.get("cpc", 0),
            "competition": item.get("competition", ""),
            "competition_index": item.get("competition_index", 0),
        })

    # Sort by search volume descending
    rows.sort(key=lambda x: x["search_volume"] or 0, reverse=True)

    # Auto-save results
    auto_path = auto_save(rows, "volume", keyword_list[0] if keyword_list else "")
    click.echo(f"💾 Auto-saved to {auto_path}", err=True)

    if output:
        with open(output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        click.echo(f"✅ Also saved to {output}", err=True)

    # Print table
    click.echo("\n" + "─" * 100)
    # Build header based on options
    header = f"{'Keyword':<35} {'Volume':>8}"
    if with_difficulty:
        header += f" {'KD':>4}"
    if with_intent:
        header += f" {'Intent':<14}"
    header += f" {'CPC':>7} {'Competition':>12}"
    click.echo(header)
    click.echo("─" * 100)

    for row in rows:
        cpc = row["cpc"] or 0
        comp = row["competition"] or "N/A"
        line = f"{row['keyword'][:35]:<35} {row['search_volume'] or 0:>8}"

        if with_difficulty:
            kd = row["keyword_difficulty"]
            kd_str = f"{kd:>4.0f}" if isinstance(kd, (int, float)) else f"{'N/A':>4}"
            line += f" {kd_str}"

        if with_intent:
            intent = row["intent"] or ""
            # Abbreviate intent labels
            intent_abbrev = {"informational": "info", "transactional": "trans", "commercial": "comm", "navigational": "nav"}.get(intent, intent)
            prob = row["intent_prob"]
            if prob and isinstance(prob, (int, float)):
                intent_str = f"{intent_abbrev} ({prob:.0%})"
            else:
                intent_str = intent_abbrev or "N/A"
            line += f" {intent_str:<14}"

        line += f" ${cpc:>6.2f} {comp:>12}"
        click.echo(line)
    click.echo("─" * 100)

    click.echo(f"\n💰 Actual Cost: ${cost:.4f}", err=True)


def parse_filter(filter_args: tuple) -> list | None:
    """Parse filter arguments into DataForSEO filter format.

    Filter format: --filter "field" "operator" "value"
    Supported operators: like, regex, <, >, <=, >=, =, <>, in, not_in, contains

    Examples:
        --filter "keyword_data.keyword" "like" "%software%"
        --filter "keyword_info.search_volume" ">" "100"
    """
    if not filter_args or len(filter_args) != 3:
        return None

    field, operator, value = filter_args

    # Convert numeric values
    if operator in ("<", ">", "<=", ">=", "=", "<>") and value.isdigit():
        value = int(value)

    return [field, operator, value]


@cli.command()
@click.argument("keyword")
@click.option("--location", default="2036", help="Location code (default: 2036 = Australia)")
@click.option("--language", default="en", help="Language code (default: en)")
@click.option("--limit", default=100, help="Max suggestions to return (default: 100)")
@click.option("--output", "-o", help="Output CSV file path")
@click.option("--filter", "filter_args", nargs=3, help="Filter: field operator value (e.g., 'keyword_data.keyword' 'like' '%%software%%')")
@click.option("--dry-run", is_flag=True, help="Show cost estimate and ask for confirmation")
def suggestions(keyword: str, location: str, language: str, limit: int, output: str, filter_args: tuple, dry_run: bool):
    """Get keyword suggestions/ideas for a seed keyword.

    Example: uv run python cli.py suggestions "insolvency software"
    Example: uv run python cli.py suggestions --dry-run "insolvency"
    Example: uv run python cli.py suggestions "insolvency" --filter "keyword_data.keyword" "like" "%software%"
    """
    estimated_cost = COSTS["keyword_suggestions"] + (limit * 0.0002)

    if dry_run:
        details = [
            f"Seed keyword: {keyword}",
            f"Max results: {limit}",
            f"Location: {location}",
            f"Language: {language}",
            f"Filter: {parse_filter(filter_args) if filter_args else 'none'}",
            f"Output: {output or 'terminal'}",
        ]
        if not confirm_cost("Get keyword suggestions", details, estimated_cost):
            click.echo("❌ Cancelled", err=True)
            return

    click.echo(f"🔍 Finding keyword suggestions for '{keyword}'...", err=True)

    data = [{
        "keyword": keyword,
        "location_code": int(location),
        "language_code": language,
        "limit": limit,
        "include_seed_keyword": True,
        "include_serp_info": True,
        "include_clickstream_data": True,
    }]

    # Add filter if provided
    api_filter = parse_filter(filter_args)
    if api_filter:
        data[0]["filters"] = api_filter
        click.echo(f"🔎 Filter: {api_filter}", err=True)

    try:
        result = api_post("dataforseo_labs/google/keyword_suggestions/live", data)
    except requests.exceptions.HTTPError as e:
        click.echo(f"❌ API Error: {e}", err=True)
        click.echo(f"Response: {e.response.text}", err=True)
        sys.exit(1)

    if result.get("status_code") != 20000:
        click.echo(f"❌ API Error: {result.get('status_message')}", err=True)
        sys.exit(1)

    tasks = result.get("tasks", [])
    if not tasks or not tasks[0].get("result"):
        click.echo("❌ No results returned", err=True)
        sys.exit(1)

    items = tasks[0]["result"][0].get("items", [])
    cost = result.get("cost", estimated_cost)

    rows = []
    for item in items:
        kw_info = item.get("keyword_info", {}) or {}
        cs_info = item.get("keyword_info_normalized_with_clickstream", {}) or {}
        kw_props = item.get("keyword_properties", {}) or {}
        # Prefer clickstream-refined volume, fall back to Google Ads
        volume = cs_info.get("search_volume") or kw_info.get("search_volume", 0)
        rows.append({
            "keyword": item.get("keyword", ""),
            "search_volume": volume,
            "keyword_difficulty": kw_props.get("keyword_difficulty", 0),
            "cpc": kw_info.get("cpc", 0),
            "competition": kw_info.get("competition", 0),
        })

    rows.sort(key=lambda x: x["search_volume"] or 0, reverse=True)

    # Auto-save results
    auto_path = auto_save(rows, "suggestions", keyword)
    click.echo(f"💾 Auto-saved to {auto_path}", err=True)

    if output:
        with open(output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        click.echo(f"✅ Also saved to {output}", err=True)

    # Print table
    click.echo("\n" + "─" * 80)
    click.echo(f"{'Keyword':<45} {'Volume':>10} {'KD':>6} {'CPC':>8}")
    click.echo("─" * 80)
    for row in rows[:20]:
        kd = row["keyword_difficulty"] or 0
        cpc = row["cpc"] or 0
        click.echo(f"{row['keyword'][:45]:<45} {row['search_volume'] or 0:>10} {kd:>6.0f} ${cpc:>7.2f}")
    if len(rows) > 20:
        click.echo(f"... and {len(rows) - 20} more")
    click.echo("─" * 80)

    click.echo(f"\n💰 Actual Cost: ${cost:.4f}", err=True)


@cli.command()
@click.argument("keyword")
@click.option("--location", default="2036", help="Location code (default: 2036 = Australia)")
@click.option("--language", default="en", help="Language code (default: en)")
@click.option("--limit", default=100, help="Max related keywords (default: 100)")
@click.option("--output", "-o", help="Output CSV file path")
@click.option("--filter", "filter_args", nargs=3, help="Filter: field operator value (e.g., 'keyword_data.keyword' 'like' '%%software%%')")
@click.option("--dry-run", is_flag=True, help="Show cost estimate and ask for confirmation")
def related(keyword: str, location: str, language: str, limit: int, output: str, filter_args: tuple, dry_run: bool):
    """Get related keywords from SERP data.

    Example: uv run python cli.py related "bank statement analysis"
    Example: uv run python cli.py related --dry-run "insolvency"
    Example: uv run python cli.py related "insolvency" --filter "keyword_data.keyword" "like" "%app%"
    """
    estimated_cost = COSTS["related_keywords"] + (limit * 0.0002)

    if dry_run:
        details = [
            f"Seed keyword: {keyword}",
            f"Max results: {limit}",
            f"Location: {location}",
            f"Language: {language}",
            f"Filter: {parse_filter(filter_args) if filter_args else 'none'}",
            f"Output: {output or 'terminal'}",
        ]
        if not confirm_cost("Get related keywords", details, estimated_cost):
            click.echo("❌ Cancelled", err=True)
            return

    click.echo(f"🔗 Finding related keywords for '{keyword}'...", err=True)

    data = [{
        "keyword": keyword,
        "location_code": int(location),
        "language_code": language,
        "limit": limit,
        "include_seed_keyword": True,
        "include_clickstream_data": True,
    }]

    # Add filter if provided
    api_filter = parse_filter(filter_args)
    if api_filter:
        data[0]["filters"] = api_filter
        click.echo(f"🔎 Filter: {api_filter}", err=True)

    try:
        result = api_post("dataforseo_labs/google/related_keywords/live", data)
    except requests.exceptions.HTTPError as e:
        click.echo(f"❌ API Error: {e}", err=True)
        click.echo(f"Response: {e.response.text}", err=True)
        sys.exit(1)

    if result.get("status_code") != 20000:
        click.echo(f"❌ API Error: {result.get('status_message')}", err=True)
        sys.exit(1)

    tasks = result.get("tasks", [])
    if not tasks or not tasks[0].get("result"):
        click.echo("❌ No results returned", err=True)
        sys.exit(1)

    items = tasks[0]["result"][0].get("items", [])
    cost = result.get("cost", estimated_cost)

    rows = []
    for item in items:
        kw_data = item.get("keyword_data", {}) or {}
        kw_info = kw_data.get("keyword_info", {}) or {}
        cs_info = kw_data.get("keyword_info_normalized_with_clickstream", {}) or {}
        # Prefer clickstream-refined volume, fall back to Google Ads
        volume = cs_info.get("search_volume") or kw_info.get("search_volume", 0)
        rows.append({
            "keyword": kw_data.get("keyword", ""),
            "search_volume": volume,
            "cpc": kw_info.get("cpc", 0),
            "competition": kw_info.get("competition", 0),
        })

    rows.sort(key=lambda x: x["search_volume"] or 0, reverse=True)

    # Auto-save results
    auto_path = auto_save(rows, "related", keyword)
    click.echo(f"💾 Auto-saved to {auto_path}", err=True)

    if output:
        with open(output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        click.echo(f"✅ Also saved to {output}", err=True)

    # Print table
    click.echo("\n" + "─" * 70)
    click.echo(f"{'Keyword':<45} {'Volume':>10} {'CPC':>8}")
    click.echo("─" * 70)
    for row in rows[:20]:
        cpc = row["cpc"] or 0
        click.echo(f"{row['keyword'][:45]:<45} {row['search_volume'] or 0:>10} ${cpc:>7.2f}")
    if len(rows) > 20:
        click.echo(f"... and {len(rows) - 20} more")
    click.echo("─" * 70)

    click.echo(f"\n💰 Actual Cost: ${cost:.4f}", err=True)


@cli.command()
def locations():
    """List common location codes for targeting."""
    common = [
        ("2036", "Australia"),
        ("2840", "United States"),
        ("2826", "United Kingdom"),
        ("2124", "Canada"),
        ("2554", "New Zealand"),
        ("2356", "India"),
        ("2702", "Singapore"),
        ("2344", "Hong Kong"),
    ]
    click.echo("\n📍 Common Location Codes:")
    click.echo("─" * 30)
    for code, name in common:
        click.echo(f"  {code}: {name}")
    click.echo("\nFull list: https://docs.dataforseo.com/v3/appendix/locations/")


@cli.command()
def balance():
    """Check your DataForSEO account balance."""
    try:
        result = api_get("appendix/user_data")
    except requests.exceptions.HTTPError as e:
        click.echo(f"❌ API Error: {e}", err=True)
        sys.exit(1)

    if result.get("status_code") != 20000:
        click.echo(f"❌ API Error: {result.get('status_message')}", err=True)
        sys.exit(1)

    tasks = result.get("tasks", [])
    if tasks and tasks[0].get("result"):
        data = tasks[0]["result"][0]
        bal = data.get("money", {}).get("balance", 0)
        click.echo(f"\n💵 Account Balance: ${bal:.2f}")
    else:
        click.echo("❌ Could not fetch balance", err=True)


@cli.command()
def costs():
    """Show cost estimates for each command."""
    click.echo("\n💰 DataForSEO API Cost Estimates")
    click.echo("═" * 50)
    click.echo("\nPer-request costs:")
    click.echo(f"  volume (Google Ads)      : $0.075 per request")
    click.echo(f"                             (up to 1000 keywords)")
    click.echo(f"  + search intent (default): +$0.001 + $0.0001/keyword")
    click.echo(f"  + difficulty (-d flag)   : +$0.01 + $0.0001/keyword")
    click.echo(f"  suggestions (+ clickstream): $0.02 + $0.0002/result")
    click.echo(f"  related (+ clickstream)    : $0.02 + $0.0002/result")
    click.echo(f"  balance                  : FREE")
    click.echo("\nExamples:")
    click.echo(f"  10 keywords volume       : ~$0.077 (includes intent)")
    click.echo(f"  10 keywords + difficulty : ~$0.088")
    click.echo(f"  100 suggestions          : ~$0.02")
    click.echo(f"  Full research session    : ~$0.25-0.50")
    click.echo("\nOptions:")
    click.echo(f"  --no-intent              : Skip search intent (saves ~$0.001)")
    click.echo(f"  --dry-run                : Preview cost before running")


# ─────────────────────────────────────────────────────────────────────────────
# DataForSEO Labs — competitor reverse-engineering
# Discover what a *competitor domain* actually ranks for, instead of guessing
# seed keywords. All take --location (default 2036 = Australia; 2840 = US).
# ─────────────────────────────────────────────────────────────────────────────

def _labs_first_result(resp: dict) -> dict:
    task = (resp.get("tasks") or [{}])[0]
    return (task.get("result") or [{}])[0] or {}


def _labs_print(rows: list, cols: list, limit: int) -> None:
    for row in rows[:limit]:
        click.echo("  " + "  ".join(str(row.get(c, "")) for c in cols))


@cli.command("ranked-keywords")
@click.argument("domain")
@click.option("--location", default="2036", help="Location code (default: 2036 = Australia)")
@click.option("--language", default="en", help="Language code (default: en)")
@click.option("--limit", default=200, help="Max keywords to return (default: 200)")
@click.option("--max-pos", default=20, help="Only keywords ranking in top N positions (default: 20)")
@click.option("--min-vol", default=0, help="Minimum search volume (default: 0)")
@click.option("--output", "-o", help="Output CSV file path")
def ranked_keywords(domain, location, language, limit, max_pos, min_vol, output):
    """Every keyword a DOMAIN ranks for (position + volume + cpc). ~$0.02-0.05."""
    payload = [{
        "target": domain, "language_code": language, "location_code": int(location),
        "limit": limit, "order_by": ["keyword_data.keyword_info.search_volume,desc"],
        "filters": [
            ["ranked_serp_element.serp_item.rank_absolute", "<=", max_pos],
            "and", ["keyword_data.keyword_info.search_volume", ">=", min_vol],
        ],
    }]
    click.echo(f"🔍 Pulling keywords {domain} ranks for (top-{max_pos})...")
    resp = api_post("dataforseo_labs/google/ranked_keywords/live", payload)
    res = _labs_first_result(resp)
    rows = []
    for it in res.get("items") or []:
        kd = it.get("keyword_data", {})
        ki = kd.get("keyword_info", {}) or {}
        se = (it.get("ranked_serp_element") or {}).get("serp_item", {}) or {}
        rows.append({
            "keyword": kd.get("keyword"),
            "search_volume": ki.get("search_volume") or 0,
            "cpc": round(ki.get("cpc") or 0, 2),
            "position": se.get("rank_absolute"),
            "etv": round(se.get("etv") or 0, 1),
            "url": se.get("url"),
        })
    rows.sort(key=lambda x: -x["search_volume"])
    if output and rows:
        with open(output, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
        path = output
    else:
        path = auto_save(rows, "ranked", domain)
    click.echo(f"💾 Saved to {path}")
    click.echo(f"\n{domain}: {res.get('total_count')} ranked keywords (top-{max_pos}), "
               f"showing {len(rows)} | 💰 ${resp.get('cost')}")
    _labs_print(rows, ["search_volume", "cpc", "position", "keyword"], min(40, len(rows)))


@cli.command("domain-overview")
@click.argument("domains", nargs=-1, required=True)
@click.option("--location", default="2036", help="Location code (default: 2036 = Australia)")
@click.option("--language", default="en", help="Language code (default: en)")
def domain_overview(domains, location, language):
    """Organic footprint per domain: kw count, est traffic/mo, $ value. ~$0.01/domain."""
    for d in domains:
        resp = api_post("dataforseo_labs/google/domain_rank_overview/live",
                        [{"target": d, "language_code": language, "location_code": int(location)}])
        items = _labs_first_result(resp).get("items") or []
        if not items:
            click.echo(f"  {d}: no data"); continue
        m = items[0].get("metrics", {}).get("organic", {})
        click.echo(f"  {d:<22} kws:{m.get('count', 0):>7} | est traffic/mo:{m.get('etv', 0):>11,.0f} | "
                   f"traffic value: ${m.get('estimated_paid_traffic_cost', 0):>11,.0f}")


@cli.command("intersection")
@click.argument("domain_a")
@click.argument("domain_b")
@click.option("--location", default="2036", help="Location code (default: 2036 = Australia)")
@click.option("--language", default="en", help="Language code (default: en)")
@click.option("--limit", default=100, help="Max keywords (default: 100)")
@click.option("--min-vol", default=40, help="Minimum search volume (default: 40)")
@click.option("--output", "-o", help="Output CSV file path")
def intersection(domain_a, domain_b, location, language, limit, min_vol, output):
    """Keywords BOTH domains rank for — gap analysis. ~$0.02."""
    payload = [{
        "target1": domain_a, "target2": domain_b, "language_code": language,
        "location_code": int(location), "intersections": True, "limit": limit,
        "order_by": ["keyword_data.keyword_info.search_volume,desc"],
        "filters": [["keyword_data.keyword_info.search_volume", ">", min_vol]],
    }]
    click.echo(f"🔍 Keywords both {domain_a} and {domain_b} rank for...")
    resp = api_post("dataforseo_labs/google/domain_intersection/live", payload)
    res = _labs_first_result(resp)
    rows = []
    for it in res.get("items") or []:
        kd = it.get("keyword_data", {})
        ki = kd.get("keyword_info", {}) or {}
        rows.append({
            "keyword": kd.get("keyword"),
            "search_volume": ki.get("search_volume") or 0,
            "cpc": round(ki.get("cpc") or 0, 2),
            "pos_a": (it.get("first_domain_serp_element") or {}).get("rank_absolute"),
            "pos_b": (it.get("second_domain_serp_element") or {}).get("rank_absolute"),
        })
    rows.sort(key=lambda x: -x["search_volume"])
    if output and rows:
        with open(output, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
        path = output
    else:
        path = auto_save(rows, "intersection", f"{domain_a}-{domain_b}")
    click.echo(f"💾 Saved to {path}")
    click.echo(f"\n{domain_a} ∩ {domain_b}: {res.get('total_count')} shared keywords | 💰 ${resp.get('cost')}")
    _labs_print(rows, ["search_volume", "cpc", "keyword"], min(40, len(rows)))


@cli.command("competitors")
@click.argument("domain")
@click.option("--location", default="2036", help="Location code (default: 2036 = Australia)")
@click.option("--language", default="en", help="Language code (default: en)")
@click.option("--limit", default=25, help="Max competitor domains (default: 25)")
@click.option("--min-intersections", default=10, help="Min shared keywords (default: 10)")
def competitors(domain, location, language, limit, min_intersections):
    """Auto-discover competitor domains + their organic traffic. ~$0.01."""
    payload = [{
        "target": domain, "language_code": language, "location_code": int(location),
        "limit": limit, "order_by": ["intersections,desc"],
        "filters": [["intersections", ">", min_intersections]],
    }]
    click.echo(f"🔍 Discovering competitors of {domain}...")
    resp = api_post("dataforseo_labs/google/competitors_domain/live", payload)
    res = _labs_first_result(resp)
    rows = []
    for it in res.get("items") or []:
        m = it.get("metrics", {}).get("organic", {})
        rows.append({
            "domain": it.get("domain"),
            "shared_kws": it.get("intersections"),
            "total_kws": m.get("count", 0),
            "est_traffic": round(m.get("etv", 0)),
        })
    auto_save(rows, "competitors", domain)
    click.echo(f"\ncompetitors of {domain} | 💰 ${resp.get('cost')}")
    _labs_print(rows, ["shared_kws", "total_kws", "est_traffic", "domain"], len(rows))


@cli.command("keywords-for-site")
@click.argument("domain")
@click.option("--location", default="2036", help="Location code (default: 2036 = Australia)")
@click.option("--language", default="en", help="Language code (default: en)")
@click.option("--limit", default=200, help="Max keywords (default: 200)")
@click.option("--output", "-o", help="Output CSV file path")
def keywords_for_site(domain, location, language, limit, output):
    """Keywords a domain ranks AND bids on (reveals paid-search spend). ~$0.02."""
    payload = [{
        "target": domain, "language_code": language, "location_code": int(location),
        "limit": limit, "order_by": ["keyword_info.search_volume,desc"],
    }]
    click.echo(f"🔍 Keywords {domain} ranks and bids on...")
    resp = api_post("dataforseo_labs/google/keywords_for_site/live", payload)
    res = _labs_first_result(resp)
    rows = []
    for it in res.get("items") or []:
        ki = it.get("keyword_info", {}) or {}
        rows.append({
            "keyword": it.get("keyword"),
            "search_volume": ki.get("search_volume") or 0,
            "cpc": round(ki.get("cpc") or 0, 2),
            "competition": ki.get("competition_level"),
        })
    rows.sort(key=lambda x: -x["search_volume"])
    if output and rows:
        with open(output, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
        path = output
    else:
        path = auto_save(rows, "keywords-for-site", domain)
    click.echo(f"💾 Saved to {path}")
    click.echo(f"\n{domain}: {len(rows)} keywords | 💰 ${resp.get('cost')}")
    _labs_print(rows, ["search_volume", "cpc", "competition", "keyword"], min(40, len(rows)))


if __name__ == "__main__":
    cli()
