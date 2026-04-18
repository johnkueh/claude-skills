#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["click>=8.0"]
# ///
"""Topic-keyword filter + outlet tier classifier for journalist queries.

Scores queries against a topic-keyword list, classifies outlets by DA tier,
and emits a sorted list of pitch-worthy candidates.

Usage:
    uv run filter.py score --queries fixtures/sample-queries.json --keywords retatrutide,GLP-1,tirzepatide
    uv run filter.py score --queries queries.json --config /path/to/project-config.json
"""

import json
import re
import sys
from pathlib import Path

import click

SKILL_DIR = Path(__file__).resolve().parent.parent

OUTLET_TIERS = {
    "HIGH": {
        "wall street journal", "wsj", "new york times", "nyt",
        "washington post", "bloomberg", "bloomberg businessweek",
        "everyday health", "healthline", "webmd",
        "bbc", "reuters", "associated press", "ap news",
        "cnbc", "cnn", "forbes", "time",
        "the atlantic", "the economist", "nature",
    },
    "MED": {
        "yahoo health", "yahoo life", "vox", "wired", "fast company",
        "well+good", "mindbodygreen", "men's health", "women's health",
        "self", "shape", "prevention", "eat this not that",
        "cnet", "the verge", "techcrunch", "engadget",
        "krazy coupon lady", "thekrazycouponlady",
        "cnbc make it", "marketwatch",
    },
    "LOW_HEALTH": {
        "real simple", "parade", "martha stewart",
    },
}


def classify_outlet(outlet: str) -> str:
    """Return HIGH / MED / LOW / UNKNOWN tier for a given outlet name."""
    if not outlet:
        return "UNKNOWN"
    key = outlet.lower().strip()
    for tier, names in OUTLET_TIERS.items():
        for name in names:
            if name in key:
                return tier
    return "UNKNOWN"


def topic_score(text: str, keywords: list[str]) -> tuple[float, list[str]]:
    """Return (score, matched_keywords). Score is fraction of keywords matched, capped at 1.0."""
    if not keywords:
        return 0.0, []
    text_lower = text.lower()
    matched = []
    for kw in keywords:
        pattern = r"\b" + re.escape(kw.lower()) + r"\b"
        if re.search(pattern, text_lower):
            matched.append(kw)
    if not matched:
        return 0.0, []
    base = min(len(matched) / 3, 1.0)
    boost = 0.1 if len(matched) >= 2 else 0.0
    return min(base + boost, 1.0), matched


def score_query(query: dict, keywords: list[str]) -> dict:
    """Attach relevance + outlet tier + matched keywords to a query dict."""
    text = f"{query.get('subject', '')} {query.get('query', '')}"
    relevance, matched = topic_score(text, keywords)
    outlet_tier = classify_outlet(query.get("outlet", ""))
    return {
        **query,
        "relevance": round(relevance, 2),
        "matched_keywords": matched,
        "outlet_tier": outlet_tier,
    }


@click.group()
def cli():
    """Topic filter + outlet classifier."""
    pass


@cli.command()
@click.option("--queries", "queries_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--keywords", default="", help="Comma-separated keyword list (overrides --config)")
@click.option("--config", "config_path", default=None, type=click.Path(exists=True, dir_okay=False),
              help="Project config JSON containing topic_keywords")
@click.option("--min-relevance", default=0.5, type=float, help="Minimum relevance to include (0-1)")
@click.option("--format", "output_format", default="json", type=click.Choice(["json", "table"]))
def score(queries_path: str, keywords: str, config_path: str | None, min_relevance: float, output_format: str):
    """Score queries by relevance + outlet tier, filter to pitch-worthy."""
    data = json.loads(Path(queries_path).read_text())
    queries = data.get("queries", data) if isinstance(data, dict) else data

    if keywords:
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    elif config_path:
        cfg = json.loads(Path(config_path).read_text())
        kw_list = cfg.get("topic_keywords", [])
    else:
        click.echo("Error: must pass --keywords or --config", err=True)
        sys.exit(1)

    scored = [score_query(q, kw_list) for q in queries]
    scored.sort(key=lambda q: (-q["relevance"], q["outlet_tier"] != "HIGH"))

    passed = [q for q in scored if q["relevance"] >= min_relevance]
    rejected = [q for q in scored if q["relevance"] < min_relevance]

    if output_format == "json":
        click.echo(json.dumps({"passed": passed, "rejected": rejected, "keywords": kw_list}, indent=2))
    else:
        click.echo(f"\n{'ID':<16} {'REL':<5} {'TIER':<8} {'OUTLET':<32} {'SUBJECT'}", err=False)
        click.echo("-" * 120)
        for q in scored:
            mark = "✓" if q["relevance"] >= min_relevance else "✗"
            subj = (q.get("subject", "") or "")[:50]
            click.echo(f"{mark} {q['id']:<14} {q['relevance']:<5} {q['outlet_tier']:<8} {q.get('outlet', '')[:30]:<32} {subj}")
        click.echo(f"\n{len(passed)}/{len(scored)} passed filter (min_relevance={min_relevance})", err=True)


if __name__ == "__main__":
    cli()
