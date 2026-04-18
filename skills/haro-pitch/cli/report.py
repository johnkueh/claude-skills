#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["click>=8.0"]
# ///
"""Monthly metrics report for HARO/Qwoted pitch activity.

Reads all drafts in queue_dir, aggregates by month + status, emits a markdown
report.

Usage:
    uv run report.py --queue-dir /path/to/queue --month 2026-04
    uv run report.py --queue-dir /path/to/queue --all
"""

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import click


def parse_frontmatter(content: str) -> dict:
    if not content.startswith("---\n"):
        return {}
    end = content.find("\n---\n", 4)
    if end == -1:
        return {}
    fm = {}
    for line in content[4:end].splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm


def load_drafts(queue_dir: Path) -> list[dict]:
    if not queue_dir.exists():
        return []
    drafts = []
    for p in sorted(queue_dir.glob("*.md")):
        fm = parse_frontmatter(p.read_text())
        drafts.append({"slug": p.stem, **fm})
    return drafts


def month_of(iso_str: str) -> str | None:
    if not iso_str:
        return None
    m = re.match(r"(\d{4}-\d{2})", iso_str)
    return m.group(1) if m else None


def summarize(drafts: list[dict], month: str | None) -> dict:
    buckets = {s: 0 for s in ["queued", "sent", "landed", "skipped", "needs_revision"]}
    outlet_tier_counts = Counter()
    landed_outlets = []
    sent_outlets = []
    matched_keyword_counter = Counter()
    placements = []

    for d in drafts:
        drafted = d.get("drafted_at", "")
        d_month = month_of(drafted)
        if month and d_month != month:
            continue
        status = d.get("status", "queued")
        buckets[status] = buckets.get(status, 0) + 1
        outlet_tier_counts[d.get("outlet_tier", "UNKNOWN")] += 1
        if status == "sent" or status == "landed":
            sent_outlets.append(d.get("outlet", "?"))
        if status == "landed":
            landed_outlets.append({
                "outlet": d.get("outlet"),
                "outlet_tier": d.get("outlet_tier"),
                "placement_url": d.get("placement_url"),
                "landed_at": d.get("landed_at"),
            })
            placements.append(d.get("placement_url", ""))
        for kw in (d.get("matched_keywords") or "").split(","):
            kw = kw.strip()
            if kw:
                matched_keyword_counter[kw] += 1

    sent_total = buckets["sent"] + buckets["landed"]
    conversion = (buckets["landed"] / sent_total) if sent_total else 0

    return {
        "period": month or "all-time",
        "total_drafts": sum(buckets.values()),
        "by_status": buckets,
        "outlet_tier_mix": dict(outlet_tier_counts),
        "sent_outlets": sent_outlets,
        "landed": landed_outlets,
        "conversion_rate_sent_to_landed": round(conversion, 3),
        "top_matched_keywords": matched_keyword_counter.most_common(10),
    }


def render_markdown(summary: dict) -> str:
    lines = [f"# HARO/Qwoted Pitch Report — {summary['period']}"]
    lines.append("")
    lines.append(f"- Total drafts: **{summary['total_drafts']}**")
    lines.append("")
    lines.append("## Status breakdown")
    for status, count in summary["by_status"].items():
        if count:
            lines.append(f"- {status}: **{count}**")
    lines.append("")
    lines.append("## Outlet tier mix")
    for tier, count in summary["outlet_tier_mix"].items():
        lines.append(f"- {tier}: {count}")
    lines.append("")
    sent_n = summary["by_status"].get("sent", 0) + summary["by_status"].get("landed", 0)
    landed_n = summary["by_status"].get("landed", 0)
    lines.append("## Outcomes")
    lines.append(f"- Sent: {sent_n}")
    lines.append(f"- Landed: {landed_n}")
    lines.append(f"- Conversion (landed/sent): {summary['conversion_rate_sent_to_landed'] * 100:.1f}%")
    lines.append("")
    if summary["landed"]:
        lines.append("## Placements earned")
        for p in summary["landed"]:
            lines.append(f"- **{p['outlet']}** ({p['outlet_tier']}) — {p.get('placement_url', '?')}")
        lines.append("")
    if summary["top_matched_keywords"]:
        lines.append("## Top matched topic keywords")
        for kw, count in summary["top_matched_keywords"]:
            lines.append(f"- `{kw}`: {count}")
        lines.append("")
    return "\n".join(lines)


@click.command()
@click.option("--queue-dir", required=True, type=click.Path(exists=True, file_okay=False))
@click.option("--month", default=None, help="YYYY-MM; omit for all-time")
@click.option("--all", "all_time", is_flag=True, help="All-time report")
@click.option("--format", "output_format", default="markdown", type=click.Choice(["markdown", "json"]))
@click.option("--output", default=None, type=click.Path(), help="Write to file instead of stdout")
def cli(queue_dir, month, all_time, output_format, output):
    """Generate a monthly/all-time pitch activity report."""
    if all_time:
        month = None
    elif month is None:
        month = datetime.now().strftime("%Y-%m")

    drafts = load_drafts(Path(queue_dir))
    summary = summarize(drafts, month)

    out = json.dumps(summary, indent=2) if output_format == "json" else render_markdown(summary)

    if output:
        Path(output).write_text(out)
        click.echo(f"Wrote report: {output}", err=True)
    else:
        click.echo(out)


if __name__ == "__main__":
    cli()
