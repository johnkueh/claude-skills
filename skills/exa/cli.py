#!/usr/bin/env python3
"""Exa content scraping CLI. Extracts clean text, highlights, and summaries from URLs."""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import click
import requests

API_KEY = os.environ.get("EXA_API_KEY", "")
API_BASE = "https://api.exa.ai"

RESULTS_DIR = Path(__file__).parent / "results"

HEADERS = {
    "x-api-key": API_KEY,
    "Content-Type": "application/json",
}

COST_PER_PAGE = 0.001

# Exponential backoff: retry only transient statuses, 3 attempts, 2^attempt seconds.
RETRY_STATUSES = {429, 503, 504}
MAX_ATTEMPTS = 3


def api_post(endpoint: str, data: dict) -> dict:
    """Make a POST request to Exa API with retry on 429/503/504."""
    if not API_KEY:
        click.echo("Error: EXA_API_KEY environment variable is not set", err=True)
        sys.exit(1)
    url = f"{API_BASE}/{endpoint}"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        resp = requests.post(url, headers=HEADERS, json=data, timeout=30)
        if resp.status_code in RETRY_STATUSES and attempt < MAX_ATTEMPTS:
            delay = 2 ** attempt
            click.echo(
                f"HTTP {resp.status_code} from Exa — retrying in {delay}s "
                f"(attempt {attempt}/{MAX_ATTEMPTS})...",
                err=True,
            )
            time.sleep(delay)
            continue
        resp.raise_for_status()
        return resp.json()


def auto_save(data: dict, label: str = "") -> Path:
    """Auto-save results to timestamped JSON file."""
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    label_part = f"_{label[:30]}" if label else ""
    filename = f"scrape{label_part}_{timestamp}.json"
    filepath = RESULTS_DIR / filename

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    return filepath


def domain_from_url(url: str) -> str:
    """Extract domain from URL for display."""
    parsed = urlparse(url)
    return parsed.netloc.replace("www.", "")


@click.group()
def cli():
    """Exa content scraping CLI."""
    pass


@cli.command()
@click.argument("urls", nargs=-1, required=True)
@click.option("--highlights", is_flag=True, help="Extract key snippets from each page")
@click.option("--query", default=None, help="Guide highlight/summary extraction")
@click.option("--summary", default=None, help="Get a summary with this prompt")
@click.option("--max-chars", default=None, type=int, help="Limit text length per page")
@click.option("--fresh", is_flag=True, help="Force live crawl, bypass cache")
@click.option("--no-text", is_flag=True, help="Exclude full text (useful with --highlights or --summary)")
@click.option("--output", "-o", help="Save results to specific file")
@click.option("--dry-run", is_flag=True, help="Preview cost before executing")
def scrape(urls: tuple, highlights: bool, query: str, summary: str, max_chars: int, fresh: bool, no_text: bool, output: str, dry_run: bool):
    """Scrape content from one or more URLs.

    Examples:
        uv run python cli.py scrape "https://example.com"
        uv run python cli.py scrape "https://url1.com" "https://url2.com" --highlights
        uv run python cli.py scrape "https://example.com" --summary "Extract the key ruling"
        uv run python cli.py scrape --dry-run "https://example.com"
    """
    url_list = list(urls)
    features = []
    if not no_text:
        features.append("text")
    if highlights:
        features.append("highlights")
    if summary:
        features.append("summary")

    cost_per_page = len(features) * COST_PER_PAGE if features else COST_PER_PAGE
    estimated_cost = len(url_list) * cost_per_page

    if dry_run:
        click.echo("\n" + "=" * 60, err=True)
        click.echo("DRY RUN - Action Preview", err=True)
        click.echo("=" * 60, err=True)
        click.echo(f"\n  URLs: {len(url_list)}", err=True)
        click.echo(f"  Features: {', '.join(features) or 'text'}", err=True)
        click.echo(f"  Fresh crawl: {fresh}", err=True)
        click.echo(f"  Estimated Cost: ${estimated_cost:.4f}", err=True)
        click.echo("\n" + "=" * 60, err=True)
        if not click.confirm("Proceed?", err=True):
            click.echo("Cancelled", err=True)
            return

    click.echo(f"Fetching {len(url_list)} page(s)...", err=True)

    payload = {"urls": url_list}

    if not no_text:
        text_opts = {}
        if max_chars:
            text_opts["maxCharacters"] = max_chars
        payload["text"] = text_opts if text_opts else True

    if highlights:
        highlight_opts = {"highlightsPerUrl": 5}
        if query:
            highlight_opts["query"] = query
        payload["highlights"] = highlight_opts

    if summary:
        payload["summary"] = {"query": summary}

    if fresh:
        payload["maxAgeHours"] = 0

    try:
        result = api_post("contents", payload)
    except requests.exceptions.HTTPError as e:
        click.echo(f"API Error: {e}", err=True)
        if e.response is not None:
            click.echo(f"Response: {e.response.text}", err=True)
        sys.exit(1)

    results = result.get("results", [])
    actual_cost = result.get("costDollars", {})

    output_data = {
        "results": [],
        "cost": actual_cost,
        "pages": len(results),
    }

    for item in results:
        entry = {
            "url": item.get("url", ""),
            "title": item.get("title", ""),
            "author": item.get("author", ""),
            "publishedDate": item.get("publishedDate", ""),
        }
        if not no_text:
            entry["text"] = item.get("text", "")
        if highlights:
            entry["highlights"] = item.get("highlights", [])
            entry["highlightScores"] = item.get("highlightScores", [])
        if summary:
            entry["summary"] = item.get("summary", "")
        output_data["results"].append(entry)

    # Auto-save
    first_domain = domain_from_url(url_list[0]) if url_list else ""
    auto_path = auto_save(output_data, first_domain)
    click.echo(f"Saved to {auto_path}", err=True)

    if output:
        with open(output, "w") as f:
            json.dump(output_data, f, indent=2)
        click.echo(f"Also saved to {output}", err=True)

    # Print results
    print(json.dumps(output_data, indent=2))

    # Print summary to stderr
    statuses = result.get("statuses", [])
    errors = [s for s in statuses if s.get("error")]
    if errors:
        click.echo(f"\nErrors ({len(errors)}):", err=True)
        for err in errors:
            click.echo(f"  {err.get('url', 'unknown')}: {err.get('error', 'unknown error')}", err=True)

    click.echo(f"\nCost: {actual_cost}", err=True)


@cli.command()
@click.argument("query")
@click.option("--num-results", "-n", default=10, help="Number of results (max 100)")
@click.option("--type", "search_type", type=click.Choice(["auto", "neural", "keyword"]), default="auto", help="Search type")
@click.option("--category", type=click.Choice(["company", "research paper", "news", "tweet", "personal site", "financial report", "people"]), default=None, help="Focus on a content category")
@click.option("--include-domains", default=None, help="Comma-separated domains to include")
@click.option("--exclude-domains", default=None, help="Comma-separated domains to exclude")
@click.option("--start-date", default=None, help="Min publish date (YYYY-MM-DD)")
@click.option("--end-date", default=None, help="Max publish date (YYYY-MM-DD)")
@click.option("--include-text", default=None, help="Comma-separated strings that must appear in results")
@click.option("--exclude-text", default=None, help="Comma-separated strings that must not appear in results")
@click.option("--text", "include_content", is_flag=True, help="Also fetch page text content")
@click.option("--highlights", is_flag=True, help="Also fetch key snippets")
@click.option("--summary", default=None, help="Also fetch summary with this prompt")
@click.option("--max-chars", default=None, type=int, help="Limit text length per result")
@click.option("--output", "-o", help="Save results to specific file")
@click.option("--dry-run", is_flag=True, help="Preview cost before executing")
def search(query: str, num_results: int, search_type: str, category: str, include_domains: str, exclude_domains: str, start_date: str, end_date: str, include_text: str, exclude_text: str, include_content: bool, highlights: bool, summary: str, max_chars: int, output: str, dry_run: bool):
    """Search the web using Exa's neural/keyword search.

    Examples:
        uv run python cli.py search "insolvency case law Australia"
        uv run python cli.py search "voidable transactions" --category news --num-results 20
        uv run python cli.py search "s588FF Corporations Act" --include-domains jade.io,austlii.edu.au
        uv run python cli.py search "bankruptcy reform" --start-date 2024-01-01 --text
        uv run python cli.py search --dry-run "liquidator duties" -n 5
    """
    content_features = []
    if include_content:
        content_features.append("text")
    if highlights:
        content_features.append("highlights")
    if summary:
        content_features.append("summary")

    search_cost = 0.001 * num_results
    content_cost = len(content_features) * COST_PER_PAGE * num_results if content_features else 0
    estimated_cost = search_cost + content_cost

    if dry_run:
        click.echo("\n" + "=" * 60, err=True)
        click.echo("DRY RUN - Search Preview", err=True)
        click.echo("=" * 60, err=True)
        click.echo(f"\n  Query: {query}", err=True)
        click.echo(f"  Results: {num_results}", err=True)
        click.echo(f"  Type: {search_type}", err=True)
        if category:
            click.echo(f"  Category: {category}", err=True)
        if content_features:
            click.echo(f"  Content: {', '.join(content_features)}", err=True)
        click.echo(f"  Estimated Cost: ${estimated_cost:.4f}", err=True)
        click.echo("\n" + "=" * 60, err=True)
        if not click.confirm("Proceed?", err=True):
            click.echo("Cancelled", err=True)
            return

    click.echo(f"Searching for: {query} ({num_results} results)...", err=True)

    payload = {
        "query": query,
        "type": search_type,
        "numResults": num_results,
    }

    if category:
        payload["category"] = category
    if include_domains:
        payload["includeDomains"] = [d.strip() for d in include_domains.split(",")]
    if exclude_domains:
        payload["excludeDomains"] = [d.strip() for d in exclude_domains.split(",")]
    if start_date:
        payload["startPublishedDate"] = f"{start_date}T00:00:00.000Z"
    if end_date:
        payload["endPublishedDate"] = f"{end_date}T00:00:00.000Z"
    if include_text:
        payload["includeText"] = [t.strip() for t in include_text.split(",")]
    if exclude_text:
        payload["excludeText"] = [t.strip() for t in exclude_text.split(",")]

    if content_features:
        contents = {}
        if include_content:
            text_opts = {}
            if max_chars:
                text_opts["maxCharacters"] = max_chars
            contents["text"] = text_opts if text_opts else True
        if highlights:
            contents["highlights"] = {"highlightsPerUrl": 5, "query": query}
        if summary:
            contents["summary"] = {"query": summary}
        payload["contents"] = contents

    try:
        result = api_post("search", payload)
    except requests.exceptions.HTTPError as e:
        click.echo(f"API Error: {e}", err=True)
        if e.response is not None:
            click.echo(f"Response: {e.response.text}", err=True)
        sys.exit(1)

    results = result.get("results", [])
    actual_cost = result.get("costDollars", {})

    output_data = {
        "query": query,
        "searchType": result.get("searchType", search_type),
        "results": [],
        "cost": actual_cost,
        "total": len(results),
    }

    for item in results:
        entry = {
            "url": item.get("url", ""),
            "title": item.get("title", ""),
            "author": item.get("author", ""),
            "publishedDate": item.get("publishedDate", ""),
            "score": item.get("score", 0),
        }
        if include_content:
            entry["text"] = item.get("text", "")
        if highlights:
            entry["highlights"] = item.get("highlights", [])
        if summary:
            entry["summary"] = item.get("summary", "")
        output_data["results"].append(entry)

    # Auto-save
    label = query[:30].replace(" ", "-")
    auto_path = auto_save(output_data, f"search_{label}")
    click.echo(f"Saved to {auto_path}", err=True)

    if output:
        with open(output, "w") as f:
            json.dump(output_data, f, indent=2)
        click.echo(f"Also saved to {output}", err=True)

    print(json.dumps(output_data, indent=2))
    click.echo(f"\nFound {len(results)} results", err=True)
    click.echo(f"Cost: {actual_cost}", err=True)


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--highlights", is_flag=True, help="Extract key snippets from each page")
@click.option("--query", default=None, help="Guide highlight/summary extraction")
@click.option("--summary", default=None, help="Get a summary with this prompt")
@click.option("--max-chars", default=None, type=int, help="Limit text length per page")
@click.option("--fresh", is_flag=True, help="Force live crawl, bypass cache")
@click.option("--no-text", is_flag=True, help="Exclude full text")
@click.option("--output", "-o", help="Save results to specific file")
@click.option("--batch-size", default=50, help="URLs per API call (default: 50)")
@click.option("--dry-run", is_flag=True, help="Preview cost before executing")
def batch(file: str, highlights: bool, query: str, summary: str, max_chars: int, fresh: bool, no_text: bool, output: str, batch_size: int, dry_run: bool):
    """Batch scrape URLs from a text file (one URL per line).

    Examples:
        uv run python cli.py batch urls.txt
        uv run python cli.py batch urls.txt --highlights --query "key details"
        uv run python cli.py batch urls.txt --dry-run
    """
    with open(file) as f:
        url_list = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if not url_list:
        click.echo("No URLs found in file", err=True)
        sys.exit(1)

    features = []
    if not no_text:
        features.append("text")
    if highlights:
        features.append("highlights")
    if summary:
        features.append("summary")

    cost_per_page = len(features) * COST_PER_PAGE if features else COST_PER_PAGE
    estimated_cost = len(url_list) * cost_per_page

    if dry_run:
        click.echo("\n" + "=" * 60, err=True)
        click.echo("DRY RUN - Batch Preview", err=True)
        click.echo("=" * 60, err=True)
        click.echo(f"\n  URLs: {len(url_list)}", err=True)
        click.echo(f"  Batches: {(len(url_list) + batch_size - 1) // batch_size}", err=True)
        click.echo(f"  Features: {', '.join(features) or 'text'}", err=True)
        click.echo(f"  Estimated Cost: ${estimated_cost:.4f}", err=True)
        click.echo("\n" + "=" * 60, err=True)
        if not click.confirm("Proceed?", err=True):
            click.echo("Cancelled", err=True)
            return

    all_results = []
    total_cost = {}

    # Process in batches
    for i in range(0, len(url_list), batch_size):
        chunk = url_list[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(url_list) + batch_size - 1) // batch_size
        click.echo(f"Batch {batch_num}/{total_batches}: {len(chunk)} URLs...", err=True)

        payload = {"urls": chunk}

        if not no_text:
            text_opts = {}
            if max_chars:
                text_opts["maxCharacters"] = max_chars
            payload["text"] = text_opts if text_opts else True

        if highlights:
            highlight_opts = {"highlightsPerUrl": 5}
            if query:
                highlight_opts["query"] = query
            payload["highlights"] = highlight_opts

        if summary:
            payload["summary"] = {"query": summary}

        if fresh:
            payload["maxAgeHours"] = 0

        try:
            result = api_post("contents", payload)
            batch_results = result.get("results", [])
            batch_cost = result.get("costDollars", {})

            for item in batch_results:
                entry = {
                    "url": item.get("url", ""),
                    "title": item.get("title", ""),
                    "author": item.get("author", ""),
                    "publishedDate": item.get("publishedDate", ""),
                }
                if not no_text:
                    entry["text"] = item.get("text", "")
                if highlights:
                    entry["highlights"] = item.get("highlights", [])
                if summary:
                    entry["summary"] = item.get("summary", "")
                all_results.append(entry)

            # Accumulate cost
            if isinstance(batch_cost, dict):
                for k, v in batch_cost.items():
                    total_cost[k] = total_cost.get(k, 0) + v
            else:
                total_cost["total"] = total_cost.get("total", 0) + (batch_cost or 0)

            # Report errors
            statuses = result.get("statuses", [])
            errors = [s for s in statuses if s.get("error")]
            if errors:
                for err in errors:
                    click.echo(f"  Error: {err.get('url', '?')}: {err.get('error', '?')}", err=True)

        except requests.exceptions.HTTPError as e:
            click.echo(f"Batch {batch_num} failed: {e}", err=True)
            if e.response is not None:
                click.echo(f"Response: {e.response.text}", err=True)

    output_data = {
        "results": all_results,
        "cost": total_cost,
        "pages": len(all_results),
    }

    # Auto-save
    auto_path = auto_save(output_data, f"batch_{len(all_results)}")
    click.echo(f"\nSaved to {auto_path}", err=True)

    if output:
        with open(output, "w") as f:
            json.dump(output_data, f, indent=2)
        click.echo(f"Also saved to {output}", err=True)

    print(json.dumps(output_data, indent=2))
    click.echo(f"\nTotal: {len(all_results)} pages scraped", err=True)
    click.echo(f"Cost: {total_cost}", err=True)


if __name__ == "__main__":
    cli()
