#!/usr/bin/env python3
"""
daily-digest — per-project digest of signups, activities, and costs from
bq-analytics, with the latest x-monitor posts appended.

Designed to be invoked daily via `/loop`. Emits structured JSON the
parent agent reformats for the user.

Usage:
    daily_digest.py setup                              create dirs
    daily_digest.py add  <name> [flags]                add project
    daily_digest.py rm   <name>                        remove project
    daily_digest.py list [--json]                      list projects
    daily_digest.py check [--project N] [--since DUR]  produce digest
                          [--json] [--no-state]

Flags for `add`:
    --bq-project ID         GCP project for bq-analytics tables
    --group-type T          bq-analytics group_type to attach to signups
                            (e.g. household, workspace)
    --description TEXT      one-line note shown in digest header

State home (env override):
    DAILY_DIGEST_HOME, default ~/.cache/daily-digest
    Layout: projects.json, state.json, runs/<iso>.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_LOOKBACK = timedelta(days=1)


def home_dir() -> Path:
    raw = os.environ.get("DAILY_DIGEST_HOME") or "~/.cache/daily-digest"
    return Path(os.path.expandvars(os.path.expanduser(raw)))


def projects_path() -> Path:
    return home_dir() / "projects.json"


def state_path() -> Path:
    return home_dir() / "state.json"


def runs_dir() -> Path:
    return home_dir() / "runs"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    tmp.replace(path)


def parse_duration(s: str) -> timedelta:
    m = re.fullmatch(r"\s*(\d+)\s*([smhd])\s*", s)
    if not m:
        raise SystemExit(f"bad duration {s!r}; use forms like 30m, 6h, 7d")
    n, unit = int(m.group(1)), m.group(2)
    return {"s": timedelta(seconds=n), "m": timedelta(minutes=n),
            "h": timedelta(hours=n), "d": timedelta(days=n)}[unit]


# ---------------------------------------------------------------------------
# bq runner
# ---------------------------------------------------------------------------

def bq(project: str, sql: str) -> list[dict]:
    cmd = ["bq", "query", f"--project_id={project}",
           "--nouse_legacy_sql", "--format=json", "--max_rows=1000"]
    p = subprocess.run(cmd, input=sql, capture_output=True, text=True)
    if p.returncode != 0:
        return [{"_error": p.stderr.strip() or p.stdout.strip()}]
    out = p.stdout.strip()
    if not out:
        return []
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return [{"_error": f"non-JSON output: {out[:200]}"}]


def bq_users(project: str, since: datetime, group_type: str | None = None) -> dict:
    since_iso = iso(since)
    enrich_select = ""
    enrich_join = ""
    if group_type:
        enrich_select = """,
         ug.group_id,
         COALESCE(JSON_VALUE(g.traits, '$.display_name'),
                  JSON_VALUE(g.traits, '$.name')) AS group_name"""
        enrich_join = f"""
  LEFT JOIN `{project}.events.user_groups_current` ug
    ON ug.user_id = f.user_id AND ug.group_type = "{group_type}"
  LEFT JOIN `{project}.events.groups_current` g
    ON g.group_type = ug.group_type AND g.group_id = ug.group_id"""
    struct_fields = "user_id, FORMAT_TIMESTAMP('%FT%TZ', first_ts) AS first_seen"
    if group_type:
        struct_fields += ", group_id, group_name"
    sql = f"""
WITH first_seen AS (
  SELECT user_id, MIN(ts) AS first_ts
  FROM `{project}.events.identifies`
  GROUP BY user_id
), enriched AS (
  SELECT f.user_id, f.first_ts{enrich_select}
  FROM first_seen f{enrich_join}
)
SELECT
  (SELECT COUNT(*) FROM first_seen) AS total_users,
  COUNTIF(first_ts >= TIMESTAMP("{since_iso}")) AS new_users,
  ARRAY_AGG(IF(first_ts >= TIMESTAMP("{since_iso}"),
               STRUCT({struct_fields}),
               NULL) IGNORE NULLS
            ORDER BY first_ts DESC LIMIT 10) AS sample
FROM enriched
"""
    rows = bq(project, sql)
    if rows and "_error" in rows[0]:
        return {"error": rows[0]["_error"]}
    if not rows:
        return {"new": 0, "total": 0, "sample": []}
    r = rows[0]
    return {"new": int(r.get("new_users") or 0),
            "total": int(r.get("total_users") or 0),
            "sample": r.get("sample") or [],
            "group_type": group_type}


def bq_activities(project: str, since: datetime) -> dict:
    since_iso = iso(since)
    sql = f"""
SELECT event_name, COUNT(*) AS n,
       COUNT(DISTINCT user_id) AS users
FROM `{project}.events.raw`
WHERE ts >= TIMESTAMP("{since_iso}")
  AND DATE(ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY event_name ORDER BY n DESC LIMIT 15
"""
    rows = bq(project, sql)
    if rows and "_error" in rows[0]:
        return {"error": rows[0]["_error"]}
    return {"top": [{"event_name": r["event_name"],
                     "n": int(r["n"]),
                     "users": int(r["users"])} for r in rows]}


def bq_costs(project: str, since: datetime) -> dict:
    since_iso = iso(since)
    sql = f"""
SELECT
  COALESCE(JSON_VALUE(properties, '$.provider'), 'unknown') AS provider,
  COALESCE(JSON_VALUE(properties, '$.operation'), '') AS operation,
  COALESCE(JSON_VALUE(properties, '$.model'), '') AS model,
  COUNT(*) AS calls,
  ROUND(SUM(SAFE_CAST(JSON_VALUE(properties, '$.cost_micros') AS FLOAT64)) / 1e6, 4) AS cost_usd
FROM `{project}.events.raw`
WHERE event_name = 'cost.recorded'
  AND ts >= TIMESTAMP("{since_iso}")
  AND DATE(ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY 1, 2, 3 ORDER BY cost_usd DESC NULLS LAST LIMIT 20
"""
    rows = bq(project, sql)
    if rows and "_error" in rows[0]:
        return {"error": rows[0]["_error"]}
    breakdown = []
    total = 0.0
    total_calls = 0
    for r in rows:
        cost = float(r.get("cost_usd") or 0)
        calls = int(r.get("calls") or 0)
        breakdown.append({"provider": r["provider"],
                          "operation": r["operation"],
                          "model": r["model"],
                          "calls": calls, "cost_usd": cost})
        total += cost
        total_calls += calls
    return {"total_usd": round(total, 4),
            "total_calls": total_calls,
            "breakdown": breakdown}


def bq_errors(project: str, since: datetime) -> dict:
    since_iso = iso(since)
    sql = f"""
SELECT path,
       COUNTIF(status >= 500) AS errs,
       COUNT(*) AS total
FROM `{project}.logs.raw`
WHERE ts >= TIMESTAMP("{since_iso}")
  AND DATE(ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  AND path IS NOT NULL
GROUP BY path
HAVING errs > 0
ORDER BY errs DESC LIMIT 10
"""
    rows = bq(project, sql)
    if rows and "_error" in rows[0]:
        return {"error": rows[0]["_error"]}
    return {"top": [{"path": r["path"],
                     "errs": int(r["errs"]),
                     "total": int(r["total"])} for r in rows]}


def bq_feedback(project: str, since: datetime) -> dict:
    since_iso = iso(since)
    sql = f"""
SELECT FORMAT_TIMESTAMP('%FT%TZ', ts) AS ts, kind, subject,
       SUBSTR(message, 1, 240) AS message, user_id
FROM `{project}.events.feedback`
WHERE ts >= TIMESTAMP("{since_iso}")
  AND DATE(ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
ORDER BY ts DESC LIMIT 20
"""
    rows = bq(project, sql)
    if rows and "_error" in rows[0]:
        return {"error": rows[0]["_error"]}
    return {"items": rows}




# ---------------------------------------------------------------------------
# x-monitor — read directly from per-handle archives
# ---------------------------------------------------------------------------

def x_monitor_home() -> Path:
    raw = os.environ.get("X_MONITOR_HOME") or "~/.cache/x-monitor"
    return Path(os.path.expandvars(os.path.expanduser(raw)))


def x_monitor_recent(since: datetime) -> dict:
    """Read each subscribed handle's tweet archive, filter to since."""
    home = x_monitor_home()
    state_file = home / "state.json"
    if not state_file.exists():
        return {"error": "x-monitor not set up (no state.json)"}
    try:
        state = json.loads(state_file.read_text())
    except json.JSONDecodeError as e:
        return {"error": f"could not parse x-monitor state: {e}"}

    subs = state.get("subscriptions", {})
    if not subs:
        return {"error": "x-monitor has no subscriptions"}

    results = []
    total_new = 0
    for handle, info in subs.items():
        archive = home / "tweets" / f"{handle}.jsonl"
        tweets: list[dict] = []
        if archive.exists():
            for line in archive.read_text().splitlines():
                line = line.strip()
                if not line: continue
                try:
                    t = json.loads(line)
                except json.JSONDecodeError:
                    continue
                created = t.get("created_at", "")
                # tweets store "2026-05-06T04:18:21.000Z" or similar
                if created and created[:19] >= since.strftime("%Y-%m-%dT%H:%M:%S"):
                    tweets.append(t)
        tweets.sort(key=lambda t: t.get("created_at", ""), reverse=True)
        total_new += len(tweets)
        results.append({
            "handle": handle,
            "name": info.get("name") or handle,
            "last_checked_at": info.get("last_checked_at"),
            "new_count": len(tweets),
            "tweets": tweets[:10],
        })
    return {"since": iso(since), "total_new": total_new, "results": results}


# ---------------------------------------------------------------------------
# project record
# ---------------------------------------------------------------------------

def load_projects() -> dict:
    return load_json(projects_path(), {"projects": {}})


def save_projects(data: dict) -> None:
    save_json(projects_path(), data)


def cmd_setup(_args) -> int:
    home_dir().mkdir(parents=True, exist_ok=True)
    runs_dir().mkdir(parents=True, exist_ok=True)
    if not projects_path().exists():
        save_projects({"projects": {}})
    if not state_path().exists():
        save_json(state_path(), {"projects": {}})
    print(f"daily-digest home: {home_dir()}")
    print(f"projects: {projects_path()}")
    print(f"state:    {state_path()}")
    return 0


def cmd_add(args) -> int:
    data = load_projects()
    if args.name in data["projects"] and not args.force:
        sys.exit(f"project {args.name!r} already exists; pass --force to overwrite")
    data["projects"][args.name] = {
        "bq_project": args.bq_project,
        "group_type": args.group_type,
        "description": args.description,
        "added_at": iso(now_utc()),
    }
    save_projects(data)
    print(f"added {args.name}")
    return 0


def cmd_rm(args) -> int:
    data = load_projects()
    if args.name not in data["projects"]:
        sys.exit(f"no such project: {args.name}")
    del data["projects"][args.name]
    save_projects(data)
    state = load_json(state_path(), {"projects": {}})
    state["projects"].pop(args.name, None)
    save_json(state_path(), state)
    print(f"removed {args.name}")
    return 0


def cmd_list(args) -> int:
    data = load_projects()
    if args.json:
        print(json.dumps(data, indent=2)); return 0
    if not data["projects"]:
        print("no projects configured (run `add` first)"); return 0
    for name, p in data["projects"].items():
        bq = p.get("bq_project") or "—"
        gt = p.get("group_type") or "—"
        desc = p.get("description") or ""
        print(f"{name:24} bq={bq:18} group_type={gt:12} {desc}")
    return 0


# ---------------------------------------------------------------------------
# check (the actual digest)
# ---------------------------------------------------------------------------

def project_since(name: str, override: timedelta | None) -> datetime:
    state = load_json(state_path(), {"projects": {}})
    last = state.get("projects", {}).get(name, {}).get("last_checked_at")
    if override is not None:
        return now_utc() - override
    if last:
        try:
            return parse_iso(last)
        except ValueError:
            pass
    return now_utc() - DEFAULT_LOOKBACK


def update_state(name: str) -> None:
    state = load_json(state_path(), {"projects": {}})
    state.setdefault("projects", {})
    state["projects"][name] = {"last_checked_at": iso(now_utc())}
    save_json(state_path(), state)


def digest_project(name: str, cfg: dict, since: datetime) -> dict:
    out: dict = {
        "name": name,
        "since": iso(since),
        "description": cfg.get("description"),
    }
    bq_proj = cfg.get("bq_project")
    if bq_proj:
        out["users"] = bq_users(bq_proj, since, cfg.get("group_type"))
        out["activities"] = bq_activities(bq_proj, since)
        out["costs"] = bq_costs(bq_proj, since)
        out["errors"] = bq_errors(bq_proj, since)
        out["feedback"] = bq_feedback(bq_proj, since)
    else:
        out["bq_skipped"] = "no bq_project configured"

    return out


def cmd_check(args) -> int:
    data = load_projects()
    overrides = parse_duration(args.since) if args.since else None
    targets = ([args.project] if args.project else list(data["projects"].keys()))
    if not targets:
        sys.exit("no projects configured")

    started = now_utc()
    # x-monitor window: same as the widest project window, default 24h.
    xm_since = now_utc() - (overrides or DEFAULT_LOOKBACK)
    digest = {
        "generated_at": iso(started),
        "projects": [],
        "x_monitor": x_monitor_recent(xm_since),
    }
    for name in targets:
        cfg = data["projects"].get(name)
        if not cfg:
            digest["projects"].append({"name": name,
                                       "error": "not configured"})
            continue
        since = project_since(name, overrides)
        digest["projects"].append(digest_project(name, cfg, since))
        if not args.no_state:
            update_state(name)

    runs_dir().mkdir(parents=True, exist_ok=True)
    run_file = runs_dir() / (started.strftime("%Y-%m-%dT%H-%M-%SZ") + ".json")
    run_file.write_text(json.dumps(digest, indent=2))
    digest["run_file"] = str(run_file)

    if args.json:
        print(json.dumps(digest, indent=2))
    else:
        print(f"wrote {run_file}")
        print(f"projects: {[p['name'] for p in digest['projects']]}")
    return 0


# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(prog="daily_digest")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup").set_defaults(func=cmd_setup)

    a = sub.add_parser("add")
    a.add_argument("name")
    a.add_argument("--bq-project")
    a.add_argument("--group-type", help="bq-analytics group_type to attach to signups (e.g. household, workspace)")
    a.add_argument("--description")
    a.add_argument("--force", action="store_true")
    a.set_defaults(func=cmd_add)

    r = sub.add_parser("rm"); r.add_argument("name"); r.set_defaults(func=cmd_rm)

    l = sub.add_parser("list"); l.add_argument("--json", action="store_true")
    l.set_defaults(func=cmd_list)

    c = sub.add_parser("check")
    c.add_argument("--project")
    c.add_argument("--since", help="lookback override, e.g. 24h, 7d")
    c.add_argument("--json", action="store_true")
    c.add_argument("--no-state", action="store_true",
                   help="don't advance last_checked_at (for ad-hoc runs)")
    c.set_defaults(func=cmd_check)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
