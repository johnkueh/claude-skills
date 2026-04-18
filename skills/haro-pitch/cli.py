#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["click>=8.0", "python-dateutil>=2.8"]
# ///
"""Unified CLI for the haro-pitch skill — filter, queue, report.

This skill is designed to be USED BY CLAUDE CODE as the drafter.
The Python CLI handles mechanical bits (filter, queue CRUD, reporting).
Draft creation is handled by Claude Code reading the query + corpus and
writing the pitch directly.

Subcommands:
    filter     Score queries by relevance + outlet tier
    queue      Manage draft queue (new/list/mark-sent/mark-landed/mark-skipped/mark-revision)
    report     Monthly pitch activity report

Typical flow:
    1. User pastes a HARO/Qwoted query email
    2. Claude Code runs: uv run cli.py filter score --queries <pasted-json> --config <project-config>
    3. For each query that passes, Claude Code reads the project's article corpus,
       drafts a pitch in-chat, then runs: uv run cli.py queue new --queue-dir ... (with draft text)
    4. User reviews drafts in queue_dir, sends manually via HARO/Qwoted web interface
    5. User runs: uv run cli.py queue mark-sent --slug ...
    6. If placement lands: uv run cli.py queue mark-landed --slug ... --url ...
    7. Monthly: uv run cli.py report --queue-dir ... --month YYYY-MM
"""

import subprocess
import sys
from pathlib import Path

import click

SKILL_DIR = Path(__file__).resolve().parent
CLI_DIR = SKILL_DIR / "cli"


def run(cmd: list[str]) -> None:
    click.echo(f"$ {' '.join(str(c) for c in cmd)}", err=True)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(result.returncode)


PASSTHROUGH_CTX = {"ignore_unknown_options": True, "allow_extra_args": True}


@click.group()
def cli():
    """HARO/Qwoted pitch-drafter skill."""
    pass


@cli.command(context_settings=PASSTHROUGH_CTX)
@click.pass_context
def filter(ctx):
    """Topic + outlet tier filtering (passes args to cli/filter.py)."""
    run(["uv", "run", str(CLI_DIR / "filter.py"), *ctx.args])


@cli.command(context_settings=PASSTHROUGH_CTX)
@click.pass_context
def queue(ctx):
    """Queue CRUD (passes args to cli/queue.py)."""
    run(["uv", "run", str(CLI_DIR / "queue.py"), *ctx.args])


@cli.command(context_settings=PASSTHROUGH_CTX)
@click.pass_context
def report(ctx):
    """Monthly report (passes args to cli/report.py)."""
    run(["uv", "run", str(CLI_DIR / "report.py"), *ctx.args])


if __name__ == "__main__":
    cli()
