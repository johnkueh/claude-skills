#!/usr/bin/env python3
"""AI crawler report — which AI bots crawl your Vercel-hosted sites, and which paths.

Data source (verified 2026-06): Vercel's request-logs backfill endpoint
(https://vercel.com/api/logs/request-logs) — the same endpoint `vercel logs`
uses, authenticated with the Vercel CLI's own token. Unlike the CLI output,
the raw rows include `clientUserAgent`, which is what makes bot attribution
possible. Vercel Observability's bot/crawler insights are dashboard-only on
regular plans (query builder + export need Observability Plus), so this is
the honest programmatic path. The endpoint is internal and may change.

Stdlib only — no dependencies. Run with: python3 cli.py <command>
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

CONFIG_PATH = Path(
    os.environ.get("AI_CRAWLER_REPORT_CONFIG", "~/.config/ai-crawler-report/sites.json")
).expanduser()
RESULTS_DIR = Path(__file__).parent / "results"

VERCEL_AUTH_PATHS = [
    Path.home() / "Library" / "Application Support" / "com.vercel.cli" / "auth.json",
    Path.home() / ".local" / "share" / "com.vercel.cli" / "auth.json",
]

# AI crawler user-agent substrings (case-insensitive), verified 2026-06.
# Note: Google-Extended and Applebot-Extended are robots.txt tokens, not user
# agents — they never appear in logs. Gemini training crawls arrive as
# GoogleOther / Google-CloudVertexBot.
AI_BOTS = {
    "GPTBot": ["gptbot"],
    "ChatGPT-User": ["chatgpt-user"],
    "OAI-SearchBot": ["oai-searchbot"],
    "ClaudeBot": ["claudebot", "anthropic-ai"],
    "Claude-User": ["claude-user"],
    "Claude-SearchBot": ["claude-searchbot", "claude-web"],
    "PerplexityBot": ["perplexitybot"],
    "Perplexity-User": ["perplexity-user"],
    "GoogleOther": ["googleother", "google-cloudvertexbot"],
    "Bytespider": ["bytespider"],
    "CCBot": ["ccbot"],
    "Meta-ExternalAgent": ["meta-externalagent", "meta-externalfetcher", "facebookbot"],
    "Amazonbot": ["amazonbot"],
    "Cohere": ["cohere-ai", "cohere-training-data-crawler"],
    "DuckAssistBot": ["duckassistbot"],
    "MistralAI-User": ["mistralai-user"],
    "YouBot": ["youbot"],
    "AI2Bot": ["ai2bot"],
    "Diffbot": ["diffbot"],
    "Timpibot": ["timpibot"],
}

# Exponential backoff: retry only transient statuses, 3 attempts, 2^attempt seconds.
RETRY_STATUSES = {429, 503, 504}
MAX_ATTEMPTS = 3

PAGE_ROWS = 50  # fixed server-side; page-size params are ignored
MAX_PAGES = 400  # safety cap per project (20k requests)


def fail(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def vercel_token() -> str:
    token = os.environ.get("VERCEL_TOKEN")
    if token:
        return token
    for path in VERCEL_AUTH_PATHS:
        if path.exists():
            try:
                token = json.loads(path.read_text()).get("token")
            except (json.JSONDecodeError, OSError):
                continue
            if token:
                return token
    fail(
        "no Vercel token found. Run `vercel login` (the skill reuses the CLI's "
        "token) or export VERCEL_TOKEN."
    )


def api_get(url: str, token: str) -> dict:
    """GET a Vercel API URL with retry on HTTP 429/503/504."""
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code in RETRY_STATUSES and attempt < MAX_ATTEMPTS:
                delay = 2 ** attempt
                print(
                    f"HTTP {e.code} from Vercel — retrying in {delay}s "
                    f"(attempt {attempt}/{MAX_ATTEMPTS})...",
                    file=sys.stderr,
                )
                time.sleep(delay)
                continue
            body = e.read().decode(errors="replace")[:200]
            raise RuntimeError(f"HTTP {e.code} for {url}: {body}") from e


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        fail(f"no config at {CONFIG_PATH}. Run: python3 cli.py setup --team <slug> --projects <name>=<site>,...")
    return json.loads(CONFIG_PATH.read_text())


def parse_window(value: str) -> int:
    """Parse '24h' / '90m' / '2d' into milliseconds."""
    units = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}
    if not value or value[-1] not in units or not value[:-1].isdigit():
        fail(f"bad --since value {value!r}; use forms like 30m, 12h, 1d")
    return int(value[:-1]) * units[value[-1]]


def classify(user_agent: str) -> str | None:
    ua = user_agent.lower()
    for bot, needles in AI_BOTS.items():
        if any(n in ua for n in needles):
            return bot
    return None


def row_timestamp_ms(row: dict) -> int:
    """Parse a row's ISO timestamp ('2026-06-10T07:20:27.692Z') to epoch ms."""
    ts = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
    return int(ts.timestamp() * 1000)


def fetch_rows(token: str, team_id: str, project_id: str, start_ms: int, end_ms: int):
    """Yield request-log rows for a project over a window.

    The endpoint's `page` param is ignored server-side (verified 2026-06 —
    every page returns the same newest-50 rows, official CLI included), so we
    paginate by time-slicing: walk endDate down to the oldest row received,
    deduping by requestId across the overlap.
    """
    base = "https://vercel.com/api/logs/request-logs"
    seen: set[str] = set()
    end = end_ms
    for _ in range(MAX_PAGES):
        params = urllib.parse.urlencode({
            "projectId": project_id,
            "ownerId": team_id,
            "teamId": team_id,
            "page": 0,
            "startDate": start_ms,
            "endDate": end,
        })
        data = api_get(f"{base}?{params}", token)
        if data.get("name") == "ExceedsBillingLimitError":
            raise RuntimeError(
                "window exceeds your plan's request-log retention — shrink --since"
            )
        rows = data.get("rows", [])
        if not rows:
            return
        new_rows = [r for r in rows if r.get("requestId") not in seen]
        for row in new_rows:
            seen.add(row["requestId"])
            yield row
        if len(rows) < PAGE_ROWS and not data.get("hasMoreRows"):
            return
        oldest_ms = min(row_timestamp_ms(r) for r in rows)
        # Re-fetch from the oldest timestamp (inclusive — dedupe absorbs the
        # overlap); if the whole batch was already seen, force progress.
        next_end = oldest_ms if new_rows else oldest_ms - 1
        if next_end >= end:
            next_end = end - 1
        end = next_end
        if end <= start_ms:
            return
        time.sleep(0.15)  # be polite between requests
    print(
        f"Warning: stopped after {MAX_PAGES} requests ({MAX_PAGES * PAGE_ROWS} rows) — "
        "results for this site are truncated; use a smaller --since.",
        file=sys.stderr,
    )


def cmd_setup(args) -> None:
    token = vercel_token()

    # Resolve team slug/id.
    teams = api_get("https://api.vercel.com/v2/teams", token).get("teams", [])
    team = next((t for t in teams if args.team in (t.get("slug"), t.get("id"))), None)
    if not team:
        fail(f"team {args.team!r} not found. Teams: {', '.join(t['slug'] for t in teams)}")
    team_id = team["id"]

    projects = []
    for spec in args.projects.split(","):
        name, _, site = spec.strip().partition("=")
        if not name:
            continue
        info = api_get(
            f"https://api.vercel.com/v9/projects/{urllib.parse.quote(name)}?teamId={team_id}",
            token,
        )
        if not info.get("id"):
            fail(f"project {name!r} not found in team {args.team}")
        projects.append({"name": name, "site": site or name, "projectId": info["id"]})

    if not projects:
        fail("no projects given. Use --projects name=site.com,name2=site2.com")

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps({"teamId": team_id, "projects": projects}, indent=2) + "\n")
    print(f"Wrote {CONFIG_PATH} ({len(projects)} site(s), team {team['slug']}).")
    print("Run `python3 cli.py doctor` to verify end to end.")


def cmd_doctor(args) -> None:
    ok = True

    token = os.environ.get("VERCEL_TOKEN") or next(
        (p for p in VERCEL_AUTH_PATHS if p.exists()), None
    )
    if token is None:
        print("✗ Vercel token: not found — run `vercel login` or export VERCEL_TOKEN")
        sys.exit(1)
    print("✓ Vercel token: found")
    token = vercel_token()

    if not CONFIG_PATH.exists():
        print(f"✗ Config: missing {CONFIG_PATH} — run setup")
        sys.exit(1)
    config = load_config()
    print(f"✓ Config: {CONFIG_PATH} ({len(config['projects'])} site(s))")

    # Live ping: token works and request-logs are reachable for each project.
    user = api_get("https://api.vercel.com/v2/user", token).get("user", {})
    print(f"✓ Auth ping: logged in as {user.get('username', '?')}")

    end_ms = int(time.time() * 1000)
    for project in config["projects"]:
        try:
            next(
                fetch_rows(token, config["teamId"], project["projectId"],
                           end_ms - 3_600_000, end_ms),
                None,
            )
            print(f"✓ Request logs reachable: {project['site']}")
        except RuntimeError as e:
            ok = False
            print(f"✗ Request logs failed for {project['site']}: {e}")

    sys.exit(0 if ok else 1)


def cmd_report(args) -> None:
    token = vercel_token()
    config = load_config()
    window_ms = parse_window(args.since)
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - window_ms

    projects = config["projects"]
    if args.site:
        projects = [p for p in projects if args.site in (p["site"], p["name"])]
        if not projects:
            fail(f"site {args.site!r} not in config ({', '.join(p['site'] for p in config['projects'])})")

    report = {
        "from": datetime.fromtimestamp(start_ms / 1000).isoformat(timespec="minutes"),
        "to": datetime.fromtimestamp(end_ms / 1000).isoformat(timespec="minutes"),
        "window": args.since,
        "sites": [],
    }

    for project in projects:
        bots: dict[str, Counter] = defaultdict(Counter)
        scanned = 0
        try:
            for row in fetch_rows(token, config["teamId"], project["projectId"], start_ms, end_ms):
                scanned += 1
                bot = classify(row.get("clientUserAgent", ""))
                if bot:
                    bots[bot][row.get("requestPath", "?")] += 1
        except RuntimeError as e:
            print(f"Warning: {project['site']}: {e}", file=sys.stderr)

        report["sites"].append({
            "site": project["site"],
            "scanned_requests": scanned,
            "bots": {
                bot: {
                    "hits": sum(paths.values()),
                    "top_paths": paths.most_common(args.top),
                }
                for bot, paths in sorted(
                    bots.items(), key=lambda kv: -sum(kv[1].values())
                )
            },
        })

    RESULTS_DIR.mkdir(exist_ok=True)
    snapshot = RESULTS_DIR / f"report_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.json"
    snapshot.write_text(json.dumps(report, indent=2) + "\n")

    if args.json:
        print(json.dumps(report, indent=2))
        print(f"\nSaved to {snapshot}", file=sys.stderr)
        return

    print(f"\nAI crawler report — {report['from']} → {report['to']} ({args.since} window)")
    for site in report["sites"]:
        print(f"\n{site['site']}  ({site['scanned_requests']:,} requests scanned)")
        print("─" * 78)
        if not site["bots"]:
            print("  no AI crawler hits in this window")
            continue
        print(f"  {'Bot':<22} {'Hits':>6}  Top paths")
        for bot, data in site["bots"].items():
            tops = ", ".join(f"{path} ({n})" for path, n in data["top_paths"])
            print(f"  {bot:<22} {data['hits']:>6}  {tops}")
    print(
        "\nCoverage note: Vercel request-log backfill on regular plans only goes "
        "back ~1 day, so this report covers the window above — not everything "
        "since the last run. Run daily (or compare results/ snapshots) for trends."
    )
    print(f"Saved to {snapshot}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI crawler report for Vercel-hosted sites")
    sub = parser.add_subparsers(dest="command")

    s = sub.add_parser("setup", help="Resolve team + projects and write the machine-local config")
    s.add_argument("--team", required=True, help="Vercel team slug or id")
    s.add_argument(
        "--projects", required=True,
        help="Comma-separated project=site pairs, e.g. drafty=drafty.im,myapp=myapp.com",
    )

    sub.add_parser("doctor", help="Check token, config, and live request-log access")

    r = sub.add_parser("report", help="Per-site table of AI bot -> hits -> top paths")
    r.add_argument("--since", default="24h", help="Window: 30m, 12h, 24h (default; plan retention caps this)")
    r.add_argument("--top", type=int, default=5, help="Top paths per bot (default 5)")
    r.add_argument("--site", help="Limit to one configured site")
    r.add_argument("--json", action="store_true", help="Print the JSON report instead of the table")

    args = parser.parse_args()
    if args.command == "setup":
        cmd_setup(args)
    elif args.command == "doctor":
        cmd_doctor(args)
    elif args.command == "report":
        cmd_report(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
