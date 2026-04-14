#!/usr/bin/env python3
"""Analysis utilities for keyword research results.

This module provides tools for analyzing, combining, and filtering
keyword research data from DataForSEO API results.
"""

import csv
import re
from datetime import datetime
from pathlib import Path

import click

# Results directory
RESULTS_DIR = Path(__file__).parent / "results"


def extract_keywords(csv_path: Path | str) -> list[str]:
    """Extract keyword column from a CSV file.

    Args:
        csv_path: Path to CSV file with 'keyword' column

    Returns:
        List of unique keywords (lowercased, stripped)
    """
    csv_path = Path(csv_path)
    keywords = set()

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            kw = row.get("keyword", "").strip().lower()
            if kw:
                keywords.add(kw)

    return sorted(keywords)


def combine_suggestion_files(pattern: str = "suggestions_*.csv") -> list[str]:
    """Combine all suggestion files into a unique keyword list.

    Args:
        pattern: Glob pattern for files to combine

    Returns:
        Sorted list of unique keywords
    """
    keywords = set()

    for filepath in RESULTS_DIR.glob(pattern):
        keywords.update(extract_keywords(filepath))

    return sorted(keywords)


def get_existing_volume_keywords(volume_file: Path | str = None) -> set[str]:
    """Get keywords we already have volume data for.

    Args:
        volume_file: Specific file to read, or None for latest

    Returns:
        Set of keywords with existing volume data
    """
    if volume_file is None:
        # Find the latest/largest volume file
        volume_files = sorted(
            RESULTS_DIR.glob("volume_*.csv"),
            key=lambda p: p.stat().st_size,
            reverse=True
        )
        if not volume_files:
            return set()
        volume_file = volume_files[0]

    return set(extract_keywords(volume_file))


def find_new_keywords(
    discovered: list[str],
    existing_file: Path | str = None
) -> list[str]:
    """Find keywords not already in existing volume data.

    Args:
        discovered: List of newly discovered keywords
        existing_file: Volume file with existing data

    Returns:
        Keywords that need volume lookup
    """
    existing = get_existing_volume_keywords(existing_file)
    discovered_set = set(k.lower().strip() for k in discovered)

    new_keywords = discovered_set - existing
    return sorted(new_keywords)


def filter_keywords(
    keywords: list[str],
    exclude_patterns: list[str] = None,
    include_patterns: list[str] = None
) -> list[str]:
    """Filter keywords by inclusion/exclusion patterns.

    Args:
        keywords: List of keywords to filter
        exclude_patterns: Regex patterns to exclude (case-insensitive)
        include_patterns: Regex patterns to require (case-insensitive)

    Returns:
        Filtered keyword list
    """
    # Default exclusions for Australian insolvency research
    if exclude_patterns is None:
        exclude_patterns = [
            r"phoenix|arizona|california|texas|florida|alabama",
            r"movie|film|tv series|cast|season \d",
            r"hong kong|singapore|malaysia|india|canada|nz|new zealand|uk",
            r"united kingdom|2024|2025|hindi|exam|notary|licensure",
            r"certified public accountant",
        ]

    result = []
    for kw in keywords:
        kw_lower = kw.lower()

        # Check exclusions
        excluded = False
        for pattern in exclude_patterns:
            if re.search(pattern, kw_lower, re.IGNORECASE):
                excluded = True
                break

        if excluded:
            continue

        # Check inclusions (if specified)
        if include_patterns:
            included = False
            for pattern in include_patterns:
                if re.search(pattern, kw_lower, re.IGNORECASE):
                    included = True
                    break
            if not included:
                continue

        result.append(kw)

    return result


def summarize_volume(
    csv_path: Path | str,
    min_volume: int = 0
) -> list[dict]:
    """Summarize keywords with volume from a batch result.

    Args:
        csv_path: Path to volume CSV file
        min_volume: Minimum volume to include

    Returns:
        List of dicts with keyword, volume, cpc, competition
    """
    csv_path = Path(csv_path)
    results = []

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            volume = int(row.get("search_volume", 0) or 0)
            if volume >= min_volume:
                results.append({
                    "keyword": row.get("keyword", ""),
                    "volume": volume,
                    "cpc": float(row.get("cpc", 0) or 0),
                    "competition": row.get("competition", ""),
                })

    # Sort by volume descending
    results.sort(key=lambda x: x["volume"], reverse=True)
    return results


def get_high_volume_keywords(
    csv_path: Path | str,
    min_volume: int = 10
) -> list[tuple[str, int]]:
    """Get keywords with volume >= threshold.

    Args:
        csv_path: Path to volume CSV file
        min_volume: Minimum volume threshold

    Returns:
        List of (keyword, volume) tuples sorted by volume
    """
    summary = summarize_volume(csv_path, min_volume)
    return [(s["keyword"], s["volume"]) for s in summary]


def categorize_keywords(keywords_with_volume: list[tuple[str, int]]) -> dict:
    """Categorize keywords by topic based on patterns.

    Args:
        keywords_with_volume: List of (keyword, volume) tuples

    Returns:
        Dict mapping category to list of (keyword, volume) tuples
    """
    categories = {
        "forms": [],
        "definitions": [],
        "comparisons": [],
        "procedures": [],
        "practitioners": [],
        "legal_terms": [],
        "other": [],
    }

    patterns = {
        "forms": r"form \d|asic form|afsa form|template|download",
        "definitions": r"meaning|definition|what is|define|def$",
        "comparisons": r" vs | versus |difference between|compared to",
        "procedures": r"how to|process|procedure|steps|checklist",
        "practitioners": r"liquidator|administrator|trustee|practitioner|receiver",
        "legal_terms": r"section \d|act |corporations|insolvency|bankruptcy",
    }

    for kw, vol in keywords_with_volume:
        kw_lower = kw.lower()
        categorized = False

        for category, pattern in patterns.items():
            if re.search(pattern, kw_lower, re.IGNORECASE):
                categories[category].append((kw, vol))
                categorized = True
                break

        if not categorized:
            categories["other"].append((kw, vol))

    return categories


def generate_report(csv_path: Path | str, output_path: Path | str = None) -> str:
    """Generate a markdown report from volume data.

    Args:
        csv_path: Path to volume CSV file
        output_path: Optional path to save report

    Returns:
        Markdown report string
    """
    csv_path = Path(csv_path)

    # Get summary data
    all_keywords = summarize_volume(csv_path, min_volume=0)
    with_volume = [k for k in all_keywords if k["volume"] > 0]

    # Categorize
    kw_tuples = [(k["keyword"], k["volume"]) for k in with_volume]
    categories = categorize_keywords(kw_tuples)

    # Build report
    lines = [
        f"# Keyword Research Report",
        f"",
        f"**Source:** `{csv_path.name}`",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"",
        f"## Summary",
        f"",
        f"- **Total keywords researched:** {len(all_keywords)}",
        f"- **Keywords with volume > 0:** {len(with_volume)}",
        f"- **Keywords with volume = 0:** {len(all_keywords) - len(with_volume)}",
        f"",
    ]

    # Top keywords table
    lines.extend([
        f"## Top Keywords by Volume",
        f"",
        f"| Keyword | Volume | CPC |",
        f"|---------|--------|-----|",
    ])
    for kw in with_volume[:30]:
        lines.append(f"| {kw['keyword']} | {kw['volume']:,} | ${kw['cpc']:.2f} |")

    lines.append("")

    # Category breakdown
    lines.extend([
        f"## Keywords by Category",
        f"",
    ])

    for category, items in categories.items():
        if items:
            total_vol = sum(v for _, v in items)
            lines.extend([
                f"### {category.replace('_', ' ').title()} ({len(items)} keywords, {total_vol:,} total volume)",
                f"",
            ])
            for kw, vol in items[:10]:
                lines.append(f"- {kw} ({vol:,})")
            if len(items) > 10:
                lines.append(f"- *...and {len(items) - 10} more*")
            lines.append("")

    report = "\n".join(lines)

    if output_path:
        output_path = Path(output_path)
        output_path.write_text(report)

    return report


# CLI commands
@click.group()
def cli():
    """Analyze keyword research results."""
    pass


@cli.command()
@click.argument("csv_path", type=click.Path(exists=True))
@click.option("--min-volume", "-m", default=0, help="Minimum volume threshold")
def summary(csv_path: str, min_volume: int):
    """Summarize a volume CSV file.

    Example: uv run python analyze.py summary results/volume_*.csv
    """
    results = summarize_volume(csv_path, min_volume)

    click.echo(f"\n📊 Volume Summary: {Path(csv_path).name}")
    click.echo("=" * 60)
    click.echo(f"Keywords with volume >= {min_volume}: {len(results)}")
    click.echo("")

    if results:
        click.echo("Top 30 keywords:")
        click.echo("-" * 60)
        for r in results[:30]:
            click.echo(f"  {r['volume']:>6,}  {r['keyword']}")


@cli.command()
@click.option("--pattern", "-p", default="suggestions_*.csv", help="File pattern")
def combine(pattern: str):
    """Combine suggestion files into unique keyword list.

    Example: uv run python analyze.py combine
    """
    keywords = combine_suggestion_files(pattern)

    click.echo(f"\n📋 Combined Keywords from {pattern}")
    click.echo("=" * 60)
    click.echo(f"Unique keywords: {len(keywords)}")
    click.echo("")

    # Output to stdout for piping
    for kw in keywords:
        click.echo(kw)


@cli.command()
@click.argument("csv_path", type=click.Path(exists=True))
@click.option("--output", "-o", help="Output markdown file")
def report(csv_path: str, output: str):
    """Generate markdown report from volume data.

    Example: uv run python analyze.py report results/volume_*.csv -o report.md
    """
    report_text = generate_report(csv_path, output)

    if output:
        click.echo(f"✅ Report saved to {output}")
    else:
        click.echo(report_text)


@cli.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--existing", "-e", type=click.Path(exists=True), help="Existing volume file")
def find_new(input_file: str, existing: str):
    """Find keywords not in existing volume data.

    Example: uv run python analyze.py find-new new_keywords.txt -e results/volume_*.csv
    """
    # Read input file (one keyword per line or CSV)
    input_path = Path(input_file)
    if input_path.suffix == ".csv":
        new_keywords = extract_keywords(input_path)
    else:
        new_keywords = [
            line.strip().lower()
            for line in input_path.read_text().splitlines()
            if line.strip()
        ]

    new_only = find_new_keywords(new_keywords, existing)

    click.echo(f"\n🔍 New Keywords (not in existing data)")
    click.echo("=" * 60)
    click.echo(f"Input keywords: {len(new_keywords)}")
    click.echo(f"New keywords: {len(new_only)}")
    click.echo("")

    for kw in new_only:
        click.echo(kw)


@cli.command()
def list_files():
    """List all result files with stats.

    Example: uv run python analyze.py list-files
    """
    click.echo(f"\n📁 Result Files in {RESULTS_DIR}")
    click.echo("=" * 80)

    for pattern, label in [
        ("volume_*.csv", "Volume"),
        ("suggestions_*.csv", "Suggestions"),
        ("related_*.csv", "Related"),
    ]:
        files = sorted(RESULTS_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            click.echo(f"\n{label} files ({len(files)}):")
            for f in files[:5]:
                size = f.stat().st_size
                # Count rows
                with open(f) as fp:
                    rows = sum(1 for _ in fp) - 1  # Subtract header
                click.echo(f"  {f.name:<50} {rows:>6} keywords  {size:>8} bytes")
            if len(files) > 5:
                click.echo(f"  ... and {len(files) - 5} more")


if __name__ == "__main__":
    cli()
