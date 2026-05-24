#!/usr/bin/env python3
"""DataForSEO SERP analysis CLI for geo-targeted search result analysis."""

import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import click
import requests

API_AUTH = os.environ.get("DATAFORSEO_API_KEY", "")
API_BASE = "https://api.dataforseo.com/v3"

# Results directory
RESULTS_DIR = Path(__file__).parent / "results"

HEADERS = {
    "Authorization": f"Basic {API_AUTH}",
    "Content-Type": "application/json",
}

# Cost estimates per endpoint
COSTS = {
    "serp_live_regular": 0.003,  # per 10 results
    "serp_live_advanced": 0.004,  # per 10 results (includes all SERP features)
}

# Common locations
LOCATIONS = {
    "au": 2036,  # Australia
    "us": 2840,  # United States
    "uk": 2826,  # United Kingdom
    "ca": 2124,  # Canada
    "nz": 2554,  # New Zealand
}


def api_post(endpoint: str, data: list) -> dict:
    """Make a POST request to DataForSEO API."""
    url = f"{API_BASE}/{endpoint}"
    resp = requests.post(url, headers=HEADERS, json=data, timeout=120)
    resp.raise_for_status()
    return resp.json()


def api_get(endpoint: str) -> dict:
    """Make a GET request to DataForSEO API."""
    url = f"{API_BASE}/{endpoint}"
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.json()


def auto_save(rows: list, command: str, seed: str = "", location: str = "au") -> Path:
    """Auto-save results to timestamped CSV file."""
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    seed_part = f"_{seed.replace(' ', '-')[:30]}" if seed else ""
    filename = f"{command}{seed_part}_{location}_{timestamp}.csv"
    filepath = RESULTS_DIR / filename

    with open(filepath, "w", newline="") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    return filepath


def save_json(data: dict, command: str, seed: str = "", location: str = "au") -> Path:
    """Save raw JSON response for detailed analysis."""
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    seed_part = f"_{seed.replace(' ', '-')[:30]}" if seed else ""
    filename = f"{command}{seed_part}_{location}_{timestamp}.json"
    filepath = RESULTS_DIR / filename

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    return filepath


def confirm_cost(action: str, details: list, estimated_cost: float) -> bool:
    """Show action details and cost, ask for confirmation."""
    click.echo("\n" + "═" * 60, err=True)
    click.echo("📋 DRY RUN - Action Preview", err=True)
    click.echo("═" * 60, err=True)
    click.echo(f"\n🎯 Action: {action}", err=True)
    click.echo("\n📝 Details:", err=True)
    for detail in details:
        click.echo(f"   • {detail}", err=True)
    click.echo(f"\n💰 Estimated Cost: ${estimated_cost:.4f}", err=True)

    try:
        result = api_get("appendix/user_data")
        if result.get("status_code") == 20000:
            tasks = result.get("tasks", [])
            if tasks and tasks[0].get("result"):
                balance = tasks[0]["result"][0].get("money", {}).get("balance", 0)
                remaining = balance - estimated_cost
                click.echo(f"💵 Current Balance: ${balance:.2f}", err=True)
                click.echo(f"💵 After This Call: ${remaining:.2f}", err=True)
    except Exception:
        pass

    click.echo("\n" + "═" * 60, err=True)
    return click.confirm("Proceed with this API call?", err=True)


@click.group()
def cli():
    """DataForSEO SERP analysis CLI for geo-targeted search results."""
    pass


@cli.command()
@click.argument("keyword")
@click.option("--location", "-l", default="au", help="Location: au, us, uk, ca, nz or code (default: au)")
@click.option("--depth", "-d", default=10, help="Number of results (default: 10, max: 100)")
@click.option("--device", default="desktop", help="Device: desktop or mobile (default: desktop)")
@click.option("--advanced", "-a", is_flag=True, help="Use advanced endpoint (includes all SERP features)")
@click.option("--output", "-o", help="Output CSV file path")
@click.option("--json-output", "-j", is_flag=True, help="Also save raw JSON response")
@click.option("--dry-run", is_flag=True, help="Show cost estimate and ask for confirmation")
def serp(keyword: str, location: str, depth: int, device: str, advanced: bool, output: str, json_output: bool, dry_run: bool):
    """Get SERP results for a keyword with geo targeting.

    Shows organic rankings, domains, and SERP features for a search query.

    Examples:
        uv run python cli.py serp "voidable transaction australia"
        uv run python cli.py serp "rocap form" --location au --depth 20
        uv run python cli.py serp "liquidator" -l au -a  # with SERP features
    """
    loc_code = LOCATIONS.get(location.lower(), int(location) if location.isdigit() else 2036)
    loc_name = next((k for k, v in LOCATIONS.items() if v == loc_code), location)

    cost_per = COSTS["serp_live_advanced"] if advanced else COSTS["serp_live_regular"]
    estimated_cost = cost_per * (depth / 10)

    if dry_run:
        details = [
            f"Keyword: {keyword}",
            f"Location: {loc_name} ({loc_code})",
            f"Depth: {depth} results",
            f"Device: {device}",
            f"Advanced: {advanced}",
        ]
        if not confirm_cost("Get SERP results", details, estimated_cost):
            click.echo("❌ Cancelled", err=True)
            return

    click.echo(f"🔍 Fetching SERP for '{keyword}' in {loc_name.upper()}...", err=True)

    endpoint = "serp/google/organic/live/advanced" if advanced else "serp/google/organic/live/regular"
    data = [{
        "keyword": keyword,
        "location_code": loc_code,
        "language_code": "en",
        "depth": depth,
        "device": device,
    }]

    try:
        result = api_post(endpoint, data)
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

    task_result = tasks[0]["result"][0]
    items = task_result.get("items", [])
    cost = result.get("cost", estimated_cost)

    # Extract organic results
    rows = []
    serp_features = []

    for item in items:
        item_type = item.get("type", "")

        if item_type == "organic":
            rows.append({
                "rank": item.get("rank_absolute", 0),
                "domain": item.get("domain", ""),
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": (item.get("description") or "")[:200],
            })
        else:
            serp_features.append(item_type)

    # Auto-save results
    if rows:
        auto_path = auto_save(rows, "serp", keyword, loc_name)
        click.echo(f"💾 Auto-saved to {auto_path}", err=True)

    if json_output:
        json_path = save_json(task_result, "serp_raw", keyword, loc_name)
        click.echo(f"💾 JSON saved to {json_path}", err=True)

    if output and rows:
        with open(output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        click.echo(f"✅ Also saved to {output}", err=True)

    # Print SERP features
    if serp_features:
        feature_counts = Counter(serp_features)
        click.echo(f"\n📊 SERP Features Found:")
        for feature, count in feature_counts.most_common():
            click.echo(f"   • {feature}: {count}")

    # Print organic results
    click.echo(f"\n🏆 Organic Results ({len(rows)} found):")
    click.echo("─" * 100)
    click.echo(f"{'#':>3} {'Domain':<35} {'Title':<60}")
    click.echo("─" * 100)
    for row in rows[:20]:
        click.echo(f"{row['rank']:>3} {row['domain'][:35]:<35} {row['title'][:60]:<60}")
    if len(rows) > 20:
        click.echo(f"... and {len(rows) - 20} more")
    click.echo("─" * 100)

    # Summary stats
    total_results = task_result.get("se_results_count", 0)
    click.echo(f"\n📈 Total search results: {total_results:,}", err=True)
    click.echo(f"💰 Actual Cost: ${cost:.4f}", err=True)


@cli.command()
@click.argument("keywords", nargs=-1, required=True)
@click.option("--location", "-l", default="au", help="Location: au, us, uk, ca, nz or code (default: au)")
@click.option("--depth", "-d", default=10, help="Number of results per keyword (default: 10)")
@click.option("--output", "-o", help="Output CSV file path")
@click.option("--dry-run", is_flag=True, help="Show cost estimate and ask for confirmation")
def bulk(keywords: tuple, location: str, depth: int, output: str, dry_run: bool):
    """Get SERP results for multiple keywords.

    Analyzes multiple keywords and identifies common domains and ranking patterns.

    Examples:
        uv run python cli.py bulk "liquidator" "voluntary administration" "doca"
        uv run python cli.py bulk "form 507" "rocap form" --location au
    """
    keyword_list = list(keywords)
    loc_code = LOCATIONS.get(location.lower(), int(location) if location.isdigit() else 2036)
    loc_name = next((k for k, v in LOCATIONS.items() if v == loc_code), location)

    estimated_cost = COSTS["serp_live_regular"] * len(keyword_list) * (depth / 10)

    if dry_run:
        details = [
            f"Keywords: {len(keyword_list)}",
            f"Location: {loc_name} ({loc_code})",
            f"Depth: {depth} results per keyword",
        ]
        if not confirm_cost("Bulk SERP analysis", details, estimated_cost):
            click.echo("❌ Cancelled", err=True)
            return

    click.echo(f"🔍 Fetching SERP for {len(keyword_list)} keywords in {loc_name.upper()}...", err=True)

    data = [{
        "keyword": kw,
        "location_code": loc_code,
        "language_code": "en",
        "depth": depth,
    } for kw in keyword_list]

    try:
        result = api_post("serp/google/organic/live/regular", data)
    except requests.exceptions.HTTPError as e:
        click.echo(f"❌ API Error: {e}", err=True)
        sys.exit(1)

    if result.get("status_code") != 20000:
        click.echo(f"❌ API Error: {result.get('status_message')}", err=True)
        sys.exit(1)

    tasks = result.get("tasks", [])
    cost = result.get("cost", estimated_cost)

    # Aggregate results
    all_rows = []
    domain_rankings = {}  # domain -> list of (keyword, rank)

    for task in tasks:
        if not task.get("result"):
            continue
        task_result = task["result"][0]
        keyword = task_result.get("keyword", "")
        items = task_result.get("items", [])

        for item in items:
            if item.get("type") == "organic":
                domain = item.get("domain", "")
                rank = item.get("rank_absolute", 0)

                all_rows.append({
                    "keyword": keyword,
                    "rank": rank,
                    "domain": domain,
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                })

                if domain not in domain_rankings:
                    domain_rankings[domain] = []
                domain_rankings[domain].append((keyword, rank))

    # Auto-save results
    if all_rows:
        auto_path = auto_save(all_rows, "bulk", keyword_list[0] if keyword_list else "", loc_name)
        click.echo(f"💾 Auto-saved to {auto_path}", err=True)

    if output and all_rows:
        with open(output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=all_rows[0].keys())
            writer.writeheader()
            writer.writerows(all_rows)
        click.echo(f"✅ Also saved to {output}", err=True)

    # Competitor analysis - who ranks for most keywords?
    click.echo(f"\n🏆 Top Competitors (domains ranking for multiple keywords):")
    click.echo("─" * 80)
    click.echo(f"{'Domain':<40} {'Keywords':>10} {'Avg Rank':>10} {'Rankings':<20}")
    click.echo("─" * 80)

    sorted_domains = sorted(
        domain_rankings.items(),
        key=lambda x: (len(x[1]), -sum(r for _, r in x[1]) / len(x[1])),
        reverse=True
    )

    for domain, rankings in sorted_domains[:15]:
        avg_rank = sum(r for _, r in rankings) / len(rankings)
        rank_summary = ", ".join(f"#{r}" for _, r in sorted(rankings, key=lambda x: x[1])[:5])
        click.echo(f"{domain[:40]:<40} {len(rankings):>10} {avg_rank:>10.1f} {rank_summary:<20}")

    click.echo("─" * 80)
    click.echo(f"\n💰 Actual Cost: ${cost:.4f}", err=True)


@cli.command()
@click.argument("keyword")
@click.option("--location", "-l", default="au", help="Location: au, us, uk, ca, nz or code (default: au)")
@click.option("--depth", "-d", default=20, help="Number of results to analyze (default: 20)")
@click.option("--dry-run", is_flag=True, help="Show cost estimate and ask for confirmation")
def features(keyword: str, location: str, depth: int, dry_run: bool):
    """Analyze SERP features and opportunities for a keyword.

    Shows all SERP features (featured snippets, PAA, knowledge graph, etc.)
    and identifies optimization opportunities.

    Examples:
        uv run python cli.py features "voidable transaction australia"
        uv run python cli.py features "what is voluntary administration" --location au
    """
    loc_code = LOCATIONS.get(location.lower(), int(location) if location.isdigit() else 2036)
    loc_name = next((k for k, v in LOCATIONS.items() if v == loc_code), location)

    estimated_cost = COSTS["serp_live_advanced"] * (depth / 10)

    if dry_run:
        details = [
            f"Keyword: {keyword}",
            f"Location: {loc_name} ({loc_code})",
            f"Depth: {depth} results",
        ]
        if not confirm_cost("Analyze SERP features", details, estimated_cost):
            click.echo("❌ Cancelled", err=True)
            return

    click.echo(f"🔍 Analyzing SERP features for '{keyword}' in {loc_name.upper()}...", err=True)

    data = [{
        "keyword": keyword,
        "location_code": loc_code,
        "language_code": "en",
        "depth": depth,
    }]

    try:
        result = api_post("serp/google/organic/live/advanced", data)
    except requests.exceptions.HTTPError as e:
        click.echo(f"❌ API Error: {e}", err=True)
        sys.exit(1)

    if result.get("status_code") != 20000:
        click.echo(f"❌ API Error: {result.get('status_message')}", err=True)
        sys.exit(1)

    tasks = result.get("tasks", [])
    if not tasks or not tasks[0].get("result"):
        click.echo("❌ No results returned", err=True)
        sys.exit(1)

    task_result = tasks[0]["result"][0]
    items = task_result.get("items", [])
    cost = result.get("cost", estimated_cost)

    # Categorize SERP features
    feature_data = {
        "featured_snippet": [],
        "people_also_ask": [],
        "related_searches": [],
        "knowledge_graph": [],
        "local_pack": [],
        "organic": [],
        "other": [],
    }

    for item in items:
        item_type = item.get("type", "")

        if item_type == "featured_snippet":
            feature_data["featured_snippet"].append({
                "domain": item.get("domain", ""),
                "title": item.get("title", ""),
                "description": item.get("description", "")[:300],
            })
        elif item_type == "people_also_ask":
            paa_items = item.get("items", [])
            for paa in paa_items:
                feature_data["people_also_ask"].append({
                    "question": paa.get("title", ""),
                    "domain": paa.get("expanded_element", [{}])[0].get("domain", "") if paa.get("expanded_element") else "",
                })
        elif item_type == "related_searches":
            rs_items = item.get("items", [])
            for rs in rs_items:
                if isinstance(rs, dict):
                    feature_data["related_searches"].append(rs.get("title", ""))
                elif isinstance(rs, str):
                    feature_data["related_searches"].append(rs)
        elif item_type == "knowledge_graph":
            feature_data["knowledge_graph"].append({
                "title": item.get("title", ""),
                "description": item.get("description", "")[:200],
            })
        elif item_type == "local_pack":
            feature_data["local_pack"].append(item)
        elif item_type == "organic":
            feature_data["organic"].append({
                "rank": item.get("rank_absolute", 0),
                "domain": item.get("domain", ""),
                "title": item.get("title", ""),
            })
        else:
            feature_data["other"].append(item_type)

    # Print analysis
    click.echo(f"\n" + "═" * 60)
    click.echo(f"📊 SERP FEATURE ANALYSIS: {keyword}")
    click.echo("═" * 60)

    # Featured snippet
    if feature_data["featured_snippet"]:
        click.echo(f"\n✨ FEATURED SNIPPET (Position 0)")
        for fs in feature_data["featured_snippet"]:
            click.echo(f"   Domain: {fs['domain']}")
            click.echo(f"   Title: {fs['title']}")
        click.echo("   💡 Opportunity: Format content for snippet capture (definitions, lists, tables)")
    else:
        click.echo(f"\n✨ FEATURED SNIPPET: None found")
        click.echo("   💡 Opportunity: Add clear definitions and structured content")

    # People Also Ask
    if feature_data["people_also_ask"]:
        click.echo(f"\n❓ PEOPLE ALSO ASK ({len(feature_data['people_also_ask'])} questions)")
        for paa in feature_data["people_also_ask"][:8]:
            click.echo(f"   • {paa['question']}")
        click.echo("   💡 Opportunity: Add FAQ section answering these questions")

    # Related searches
    if feature_data["related_searches"]:
        click.echo(f"\n🔗 RELATED SEARCHES ({len(feature_data['related_searches'])} terms)")
        for rs in feature_data["related_searches"][:10]:
            click.echo(f"   • {rs}")
        click.echo("   💡 Opportunity: Create content targeting these related terms")

    # Knowledge graph
    if feature_data["knowledge_graph"]:
        click.echo(f"\n📚 KNOWLEDGE GRAPH")
        for kg in feature_data["knowledge_graph"]:
            click.echo(f"   Title: {kg['title']}")
        click.echo("   💡 Note: Schema markup may help capture knowledge panel")

    # Top organic
    click.echo(f"\n🏆 TOP ORGANIC ({len(feature_data['organic'])} results)")
    for org in feature_data["organic"][:5]:
        click.echo(f"   #{org['rank']}: {org['domain']} - {org['title'][:50]}")

    # Other features
    if feature_data["other"]:
        other_counts = Counter(feature_data["other"])
        click.echo(f"\n📋 OTHER SERP ELEMENTS")
        for feat, count in other_counts.most_common():
            click.echo(f"   • {feat}: {count}")

    click.echo("\n" + "═" * 60)
    click.echo(f"💰 Actual Cost: ${cost:.4f}", err=True)


@cli.command()
@click.argument("domain")
@click.argument("keywords", nargs=-1, required=True)
@click.option("--location", "-l", default="au", help="Location: au, us, uk, ca, nz or code (default: au)")
@click.option("--depth", "-d", default=20, help="Depth to search for domain (default: 20)")
@click.option("--dry-run", is_flag=True, help="Show cost estimate and ask for confirmation")
def gaps(domain: str, keywords: tuple, location: str, depth: int, dry_run: bool):
    """Find content gaps - keywords where domain doesn't rank well.

    Checks where a domain ranks for each keyword, identifying opportunities
    where competitors rank but the target domain doesn't.

    Examples:
        uv run python cli.py gaps example-site.com "liquidator" "doca" "voluntary administration"
        uv run python cli.py gaps asic.gov.au "rocap form" "form 507" --location au
    """
    keyword_list = list(keywords)
    loc_code = LOCATIONS.get(location.lower(), int(location) if location.isdigit() else 2036)
    loc_name = next((k for k, v in LOCATIONS.items() if v == loc_code), location)

    estimated_cost = COSTS["serp_live_regular"] * len(keyword_list) * (depth / 10)

    if dry_run:
        details = [
            f"Target domain: {domain}",
            f"Keywords: {len(keyword_list)}",
            f"Location: {loc_name} ({loc_code})",
            f"Search depth: {depth}",
        ]
        if not confirm_cost("Content gap analysis", details, estimated_cost):
            click.echo("❌ Cancelled", err=True)
            return

    click.echo(f"🔍 Analyzing content gaps for '{domain}' in {loc_name.upper()}...", err=True)

    data = [{
        "keyword": kw,
        "location_code": loc_code,
        "language_code": "en",
        "depth": depth,
    } for kw in keyword_list]

    try:
        result = api_post("serp/google/organic/live/regular", data)
    except requests.exceptions.HTTPError as e:
        click.echo(f"❌ API Error: {e}", err=True)
        sys.exit(1)

    if result.get("status_code") != 20000:
        click.echo(f"❌ API Error: {result.get('status_message')}", err=True)
        sys.exit(1)

    tasks = result.get("tasks", [])
    cost = result.get("cost", estimated_cost)

    # Analyze gaps
    gaps_found = []
    rankings = []
    domain_lower = domain.lower().replace("www.", "")

    for task in tasks:
        if not task.get("result"):
            continue
        task_result = task["result"][0]
        keyword = task_result.get("keyword", "")
        items = task_result.get("items", [])

        domain_rank = None
        top_competitor = None

        for item in items:
            if item.get("type") == "organic":
                item_domain = item.get("domain", "").lower().replace("www.", "")
                rank = item.get("rank_absolute", 0)

                if domain_lower == item_domain:
                    domain_rank = rank
                elif top_competitor is None:
                    top_competitor = {"domain": item.get("domain"), "rank": rank}

        rankings.append({
            "keyword": keyword,
            "domain_rank": domain_rank,
            "top_competitor": top_competitor["domain"] if top_competitor else "N/A",
            "top_rank": top_competitor["rank"] if top_competitor else 0,
        })

        if domain_rank is None:
            gaps_found.append({
                "keyword": keyword,
                "competitor": top_competitor["domain"] if top_competitor else "N/A",
                "competitor_rank": top_competitor["rank"] if top_competitor else 0,
            })

    # Auto-save
    auto_path = auto_save(rankings, "gaps", domain, loc_name)
    click.echo(f"💾 Auto-saved to {auto_path}", err=True)

    # Print results
    click.echo(f"\n" + "═" * 70)
    click.echo(f"📊 CONTENT GAP ANALYSIS: {domain}")
    click.echo("═" * 70)

    # Gap opportunities
    click.echo(f"\n🎯 CONTENT GAPS ({len(gaps_found)} keywords where {domain} doesn't rank)")
    if gaps_found:
        click.echo("─" * 70)
        click.echo(f"{'Keyword':<40} {'Top Competitor':<20} {'Rank':>6}")
        click.echo("─" * 70)
        for gap in sorted(gaps_found, key=lambda x: x["competitor_rank"]):
            click.echo(f"{gap['keyword'][:40]:<40} {gap['competitor'][:20]:<20} #{gap['competitor_rank']:>5}")
    else:
        click.echo("   ✅ Domain ranks for all keywords!")

    # Current rankings
    ranked = [r for r in rankings if r["domain_rank"] is not None]
    if ranked:
        click.echo(f"\n✅ CURRENT RANKINGS ({len(ranked)} keywords)")
        click.echo("─" * 70)
        click.echo(f"{'Keyword':<40} {'Your Rank':>10} {'Top Competitor':>15}")
        click.echo("─" * 70)
        for r in sorted(ranked, key=lambda x: x["domain_rank"]):
            click.echo(f"{r['keyword'][:40]:<40} #{r['domain_rank']:>9} #{r['top_rank']:>14}")

    click.echo("\n" + "═" * 70)
    click.echo(f"💰 Actual Cost: ${cost:.4f}", err=True)


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
    click.echo("\n💰 DataForSEO SERP API Cost Estimates")
    click.echo("═" * 50)
    click.echo("\nPer-request costs:")
    click.echo(f"  serp (regular)     : $0.003 per 10 results")
    click.echo(f"  serp -a (advanced) : $0.004 per 10 results")
    click.echo(f"  bulk (per keyword) : $0.003 per 10 results")
    click.echo(f"  features           : $0.004 per 10 results")
    click.echo(f"  gaps (per keyword) : $0.003 per 10 results")
    click.echo(f"  balance            : FREE")
    click.echo("\nExamples:")
    click.echo(f"  1 keyword, 10 results       : ~$0.003")
    click.echo(f"  1 keyword, 20 results       : ~$0.006")
    click.echo(f"  10 keywords bulk            : ~$0.03")
    click.echo(f"  50 keyword gap analysis     : ~$0.15")
    click.echo("\nUse --dry-run on any command to preview cost before running.")


@cli.command()
def locations():
    """List common location codes for targeting."""
    click.echo("\n📍 Supported Locations (shortcuts):")
    click.echo("─" * 40)
    for short, code in LOCATIONS.items():
        click.echo(f"  {short:>4}: {code} ({short.upper()})")
    click.echo("\nUsage: --location au  OR  --location 2036")
    click.echo("\nFull list: https://docs.dataforseo.com/v3/appendix/locations/")


if __name__ == "__main__":
    cli()
