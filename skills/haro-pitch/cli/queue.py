#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["click>=8.0", "python-dateutil>=2.8"]
# ///
"""File-based queue manager for HARO/Qwoted pitch drafts.

Each draft is a markdown file with frontmatter in {queue_dir}/{slug}.md.
This CLI lists drafts, transitions status (queued → sent → landed | skipped),
and produces monthly metrics reports.

Usage:
    uv run queue.py new --queue-dir /path/to/queue --id FIXTURE-001 --outlet Healthline --deadline 2026-04-22 --query-text "..." --draft "..."
    uv run queue.py list --queue-dir /path/to/queue
    uv run queue.py list --queue-dir /path/to/queue --status queued
    uv run queue.py mark-sent --queue-dir /path/to/queue --slug 2026-04-18-healthline-food-noise
    uv run queue.py mark-landed --queue-dir /path/to/queue --slug 2026-04-18-healthline-food-noise --url https://...
    uv run queue.py mark-skipped --queue-dir /path/to/queue --slug ... --reason "outlet too low tier"
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import click


STATUS_CHOICES = ["queued", "sent", "landed", "skipped", "needs_revision"]


def slugify(text: str, max_len: int = 60) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:max_len].rstrip("-")


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body)."""
    if not content.startswith("---\n"):
        return {}, content
    end = content.find("\n---\n", 4)
    if end == -1:
        return {}, content
    raw = content[4:end]
    body = content[end + 5:]
    fm = {}
    for line in raw.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm, body


def render_frontmatter(fm: dict) -> str:
    lines = ["---"]
    for k, v in fm.items():
        val = v if isinstance(v, str) else json.dumps(v)
        lines.append(f"{k}: {val}")
    lines.append("---")
    return "\n".join(lines)


def load_draft(path: Path) -> dict:
    fm, body = parse_frontmatter(path.read_text())
    return {"path": str(path), "slug": path.stem, **fm, "_body": body}


def list_queue(queue_dir: Path, status: str | None = None) -> list[dict]:
    if not queue_dir.exists():
        return []
    drafts = [load_draft(p) for p in sorted(queue_dir.glob("*.md"))]
    if status:
        drafts = [d for d in drafts if d.get("status") == status]
    return drafts


@click.group()
def cli():
    """Pitch-draft queue manager."""
    pass


@cli.command()
@click.option("--queue-dir", required=True, type=click.Path())
@click.option("--source", default="haro", type=click.Choice(["haro", "qwoted", "other"]))
@click.option("--query-id", required=True)
@click.option("--outlet", required=True)
@click.option("--outlet-tier", default="UNKNOWN")
@click.option("--deadline", default="")
@click.option("--journalist", default="")
@click.option("--relevance", default=0.0, type=float)
@click.option("--matched-keywords", default="", help="Comma-separated list")
@click.option("--target-article", default="", help="Most-relevant corpus article slug")
@click.option("--query-text", required=True, help="Original journalist query")
@click.option("--draft", "draft_text", required=True, help="Drafted pitch response")
@click.option("--why", default="", help="One-line justification for pitching")
@click.option("--slug", default=None, help="Override slug (default: {date}-{outlet}-{subject})")
@click.option("--subject", default="", help="Used in slug generation")
def new(queue_dir, source, query_id, outlet, outlet_tier, deadline, journalist, relevance,
        matched_keywords, target_article, query_text, draft_text, why, slug, subject):
    """Add a new draft to the queue."""
    qdir = Path(queue_dir)
    qdir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not slug:
        slug_basis = subject or query_text[:60]
        slug = f"{today}-{slugify(outlet)[:20]}-{slugify(slug_basis)[:40]}"

    path = qdir / f"{slug}.md"
    if path.exists():
        click.echo(f"Error: {path} already exists", err=True)
        sys.exit(1)

    fm = {
        "source": source,
        "query_id": query_id,
        "outlet": outlet,
        "outlet_tier": outlet_tier,
        "journalist": journalist,
        "deadline": deadline,
        "relevance": str(relevance),
        "matched_keywords": matched_keywords,
        "target_article": target_article,
        "status": "queued",
        "drafted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    body = f"""
## Query

{query_text.strip()}

## Draft response

{draft_text.strip()}
"""
    if why:
        body += f"\n## Why this pitch\n\n{why.strip()}\n"

    path.write_text(render_frontmatter(fm) + body)
    click.echo(f"Created: {path}")


@cli.command()
@click.option("--queue-dir", required=True, type=click.Path())
@click.option("--status", default=None, type=click.Choice(STATUS_CHOICES))
@click.option("--format", "output_format", default="table", type=click.Choice(["table", "json"]))
def list(queue_dir, status, output_format):
    """List drafts in the queue."""
    drafts = list_queue(Path(queue_dir), status)

    if output_format == "json":
        click.echo(json.dumps([{k: v for k, v in d.items() if not k.startswith("_")} for d in drafts], indent=2))
        return

    if not drafts:
        click.echo("(empty queue)")
        return

    click.echo(f"\n{'STATUS':<16} {'TIER':<8} {'OUTLET':<28} {'DEADLINE':<22} {'SLUG'}")
    click.echo("-" * 140)
    for d in drafts:
        click.echo(
            f"{d.get('status', '?'):<16} "
            f"{d.get('outlet_tier', '?'):<8} "
            f"{(d.get('outlet', '?') or '')[:26]:<28} "
            f"{(d.get('deadline', '') or '')[:20]:<22} "
            f"{d['slug']}"
        )
    click.echo(f"\n{len(drafts)} drafts")


def _update_status(queue_dir: str, slug: str, new_status: str, extra: dict = None):
    path = Path(queue_dir) / f"{slug}.md"
    if not path.exists():
        click.echo(f"Error: {path} not found", err=True)
        sys.exit(1)
    fm, body = parse_frontmatter(path.read_text())
    fm["status"] = new_status
    fm[f"{new_status}_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if extra:
        fm.update({k: str(v) for k, v in extra.items()})
    path.write_text(render_frontmatter(fm) + body)
    click.echo(f"Updated {slug} → {new_status}")


@cli.command(name="mark-sent")
@click.option("--queue-dir", required=True, type=click.Path())
@click.option("--slug", required=True)
def mark_sent(queue_dir, slug):
    """Mark a draft as sent."""
    _update_status(queue_dir, slug, "sent")


@cli.command(name="mark-landed")
@click.option("--queue-dir", required=True, type=click.Path())
@click.option("--slug", required=True)
@click.option("--url", required=True, help="URL of the published placement")
def mark_landed(queue_dir, slug, url):
    """Mark a pitch as having landed a placement."""
    _update_status(queue_dir, slug, "landed", {"placement_url": url})


@cli.command(name="mark-skipped")
@click.option("--queue-dir", required=True, type=click.Path())
@click.option("--slug", required=True)
@click.option("--reason", required=True)
def mark_skipped(queue_dir, slug, reason):
    """Mark a draft as skipped (not sent)."""
    _update_status(queue_dir, slug, "skipped", {"skip_reason": reason})


@cli.command(name="mark-revision")
@click.option("--queue-dir", required=True, type=click.Path())
@click.option("--slug", required=True)
@click.option("--notes", required=True)
def mark_revision(queue_dir, slug, notes):
    """Flag a draft as needing revision before send."""
    _update_status(queue_dir, slug, "needs_revision", {"revision_notes": notes})


if __name__ == "__main__":
    cli()
