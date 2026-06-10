# GENERATED FILE — synced from scripts/shared/dataforseo.py by scripts/build-marketplace.ts.
# Do not edit here: edit the canonical file, then run `bun scripts/build-marketplace.ts`.
"""Shared DataForSEO API client used by the keyword-data and serp-data skills.

CANONICAL COPY. The build script (scripts/build-marketplace.ts) syncs this file
into skills/keyword-data/dataforseo.py and skills/serp-data/dataforseo.py so
each skill stays self-contained when distributed as a single plugin.
Edit THIS file, then run `bun scripts/build-marketplace.ts` to propagate.

Auth: DATAFORSEO_API_KEY is the base64 of "login:password"
(generate with: echo -n 'login:pass' | base64).
"""

import csv
import os
import time
from datetime import datetime
from pathlib import Path

import click
import requests

API_AUTH = os.environ.get("DATAFORSEO_API_KEY", "")
API_BASE = "https://api.dataforseo.com/v3"

HEADERS = {
    "Authorization": f"Basic {API_AUTH}",
    "Content-Type": "application/json",
}

# Results directory — resolves to the directory of the skill this copy lives in.
RESULTS_DIR = Path(__file__).parent / "results"

# Exponential backoff: retry only transient statuses, 3 attempts, 2^attempt seconds.
RETRY_STATUSES = {429, 503, 504}
MAX_ATTEMPTS = 3


def _request_json(method: str, endpoint: str, json_data=None, timeout: int = 60) -> dict:
    """Make a request to the DataForSEO API with retry on 429/503/504."""
    url = f"{API_BASE}/{endpoint}"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        resp = requests.request(
            method, url, headers=HEADERS, json=json_data, timeout=timeout
        )
        if resp.status_code in RETRY_STATUSES and attempt < MAX_ATTEMPTS:
            delay = 2 ** attempt
            click.echo(
                f"⏳ HTTP {resp.status_code} from DataForSEO — "
                f"retrying in {delay}s (attempt {attempt}/{MAX_ATTEMPTS})...",
                err=True,
            )
            time.sleep(delay)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("unreachable")  # pragma: no cover


def api_post(endpoint: str, data: list, timeout: int = 60) -> dict:
    """Make a POST request to DataForSEO API."""
    return _request_json("POST", endpoint, json_data=data, timeout=timeout)


def api_get(endpoint: str, timeout: int = 60) -> dict:
    """Make a GET request to DataForSEO API."""
    return _request_json("GET", endpoint, timeout=timeout)


def auto_save(rows: list, command: str, seed: str = "", tag: str = "") -> Path:
    """Auto-save results to a timestamped CSV file in the skill's results/ dir.

    `tag` is an optional extra filename segment (e.g. a location shortcut).
    """
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    seed_part = f"_{seed.replace(' ', '-')[:30]}" if seed else ""
    tag_part = f"_{tag}" if tag else ""
    filename = f"{command}{seed_part}{tag_part}_{timestamp}.csv"
    filepath = RESULTS_DIR / filename

    with open(filepath, "w", newline="") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

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

    # Get current balance
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
