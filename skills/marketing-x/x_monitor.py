#!/usr/bin/env python3
"""
x-monitor — track X (Twitter) profiles for new posts.

Usage:
    x_monitor.py setup [--home PATH]              configure cross-machine sync
    x_monitor.py doctor [--api]                   sanity-check setup
    x_monitor.py add <handle-or-url>              subscribe a handle
    x_monitor.py rm  <handle>                     unsubscribe
    x_monitor.py list [--json]                    list subscriptions
    x_monitor.py check [--handle H] [--json]      fetch new posts since last check
    x_monitor.py tweets <handle> [--since DATE]   query the local archive (no API)
                       [--grep TEXT] [--limit N] [--json]
    x_monitor.py runs [--limit N] [--json]        list past run summaries
    x_monitor.py runs latest [--json]             show the most recent run

Cache home (env override):
    X_MONITOR_HOME, default ~/.cache/x-monitor
    Layout: state.json, runs/<iso>.json, tweets/<handle>.jsonl

Credentials:
    X_BEARER_TOKEN env, else ~/.config/x-monitor/credentials.json
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

API_BASE = "https://api.x.com/2"
CREDS_PATH = Path.home() / ".config" / "x-monitor" / "credentials.json"

TWEET_FIELDS = "created_at,public_metrics,entities,referenced_tweets,attachments,lang"
USER_FIELDS = "name,username,verified,profile_image_url,description"


def home_dir() -> Path:
    raw = os.environ.get("X_MONITOR_HOME") or "~/.cache/x-monitor"
    return Path(os.path.expandvars(os.path.expanduser(raw)))


def state_path() -> Path:
    return home_dir() / "state.json"


def runs_dir() -> Path:
    return home_dir() / "runs"


def tweets_dir() -> Path:
    return home_dir() / "tweets"


def archive_path(handle: str) -> Path:
    return tweets_dir() / f"{handle}.jsonl"


def load_bearer() -> str:
    token = os.environ.get("X_BEARER_TOKEN")
    if token:
        return token
    if CREDS_PATH.exists():
        try:
            data = json.loads(CREDS_PATH.read_text())
            t = data.get("bearer_token")
            if t:
                return t
        except json.JSONDecodeError:
            pass
    sys.exit(
        "Error: no X bearer token found.\n"
        f"Set X_BEARER_TOKEN, or write {CREDS_PATH} with {{\"bearer_token\": \"...\"}}."
    )


def api_get(path: str, params: Optional[dict] = None) -> dict:
    url = f"{API_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {load_bearer()}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        if e.code == 429:
            reset = e.headers.get("x-rate-limit-reset")
            hint = ""
            if reset:
                try:
                    secs = max(0, int(reset) - int(time.time()))
                    hint = f" (resets in {secs}s)"
                except ValueError:
                    pass
            sys.exit(f"X API rate limit hit{hint}.\n{body}")
        if e.code == 401:
            sys.exit(f"X API auth failed (401). Check bearer token.\n{body}")
        if e.code == 403:
            sys.exit(
                "X API access denied (403). Your API plan may not allow reading "
                f"user tweets — Free tier is write-only; reads need Basic+.\n{body}"
            )
        if e.code == 402:
            sys.exit(
                "X API credits depleted (402). Your developer account has no "
                "credits left to fulfill read requests. Top up at "
                "https://developer.x.com/en/portal/products or upgrade your "
                f"plan, then retry.\n{body}"
            )
        sys.exit(f"X API error {e.code}: {body}")
    except urllib.error.URLError as e:
        sys.exit(f"Network error reaching X API: {e}")


def normalize_handle(s: str) -> str:
    s = s.strip()
    m = re.search(r"(?:x\.com|twitter\.com)/(@?[A-Za-z0-9_]{1,15})", s)
    if m:
        s = m.group(1)
    return s.lstrip("@").lower()


def load_state() -> dict:
    p = state_path()
    if not p.exists():
        return {"subscriptions": {}}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return {"subscriptions": {}}


def save_state(state: dict) -> None:
    home_dir().mkdir(parents=True, exist_ok=True)
    state_path().write_text(json.dumps(state, indent=2))


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def lookup_user(handle: str) -> dict:
    res = api_get(f"/users/by/username/{handle}", {"user.fields": USER_FIELDS})
    if "data" not in res:
        sys.exit(f"User @{handle} not found: {json.dumps(res)}")
    return res["data"]


def fetch_tweets(user_id: str, since_id: Optional[str], max_results: int = 20) -> dict:
    params = {
        "max_results": max(5, min(100, max_results)),
        "tweet.fields": TWEET_FIELDS,
        "exclude": "retweets,replies",
    }
    if since_id:
        params["since_id"] = since_id
    return api_get(f"/users/{user_id}/tweets", params)


def archive_tweets(handle: str, tweets: Iterable[dict]) -> int:
    """Append tweets to the per-handle archive, dedup by id. Returns # new rows written."""
    tweets = [t for t in tweets if t.get("id")]
    if not tweets:
        return 0
    tweets_dir().mkdir(parents=True, exist_ok=True)
    p = archive_path(handle)
    seen: set[str] = set()
    if p.exists():
        with p.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    seen.add(json.loads(line)["id"])
                except (json.JSONDecodeError, KeyError):
                    continue
    fresh = [t for t in tweets if t["id"] not in seen]
    if not fresh:
        return 0
    with p.open("a") as f:
        for t in fresh:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    return len(fresh)


def read_archive(handle: str) -> list[dict]:
    p = archive_path(handle)
    if not p.exists():
        return []
    out = []
    with p.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _summarize_tweet(t: dict) -> dict:
    return {
        "id": t["id"],
        "created_at": t.get("created_at"),
        "text": t.get("text", "").strip(),
        "metrics": t.get("public_metrics", {}),
        "lang": t.get("lang"),
    }


# ---------- commands ----------

ICLOUD_BASE = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
DEFAULT_LOCAL_HOME = Path.home() / ".cache" / "x-monitor"
SETTINGS_PATH = Path.home() / ".claude" / "settings.json"


def _merge_env_setting(settings_path: Path, key: str, value: str) -> str:
    """Idempotently set settings_path.env[key] = value. Returns 'created'/'updated'/'unchanged'."""
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text())
        except json.JSONDecodeError:
            sys.exit(
                f"Refusing to overwrite {settings_path} — file exists but isn't valid JSON. "
                "Fix it by hand and rerun."
            )
    else:
        data = {}
    env = data.setdefault("env", {})
    if env.get(key) == value:
        return "unchanged"
    status = "updated" if key in env else "created"
    env[key] = value
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(data, indent=2) + "\n")
    return status


def _migrate_dir(src: Path, dst: Path) -> dict:
    """Copy contents of src into dst (non-destructive). Returns counts."""
    import shutil
    if not src.exists():
        return {"copied": 0, "skipped": 0, "src_missing": True}
    dst.mkdir(parents=True, exist_ok=True)
    copied = skipped = 0
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if target.exists():
            skipped += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        copied += 1
    return {"copied": copied, "skipped": skipped, "src_missing": False}


def cmd_setup(args: argparse.Namespace) -> None:
    print("[setup] x-monitor cross-machine setup")

    target_home = Path(args.home).expanduser() if args.home else (ICLOUD_BASE / "x-monitor")
    using_icloud = ICLOUD_BASE in target_home.parents or target_home == ICLOUD_BASE / "x-monitor"

    if using_icloud and not ICLOUD_BASE.exists():
        sys.exit(
            f"iCloud Drive not found at {ICLOUD_BASE}.\n"
            "Enable iCloud Drive in System Settings (Apple ID → iCloud → Drive),"
            " or pass --home <path> to use a different shared location."
        )

    print(f"  target home: {target_home}")
    target_home.mkdir(parents=True, exist_ok=True)
    print(f"  ✓ created/verified target home")

    # Migrate from default local cache if it exists and target is empty
    if (
        DEFAULT_LOCAL_HOME.exists()
        and DEFAULT_LOCAL_HOME != target_home
        and not (target_home / "state.json").exists()
    ):
        result = _migrate_dir(DEFAULT_LOCAL_HOME, target_home)
        if result["copied"]:
            print(f"  ✓ migrated {result['copied']} file(s) from {DEFAULT_LOCAL_HOME}")
            print(f"    (left source intact as backup; remove with: rm -rf {DEFAULT_LOCAL_HOME})")
        else:
            print(f"  · nothing to migrate from {DEFAULT_LOCAL_HOME}")
    elif (target_home / "state.json").exists():
        print(f"  · target already has state.json — skipping migration")

    # Update settings.json
    status = _merge_env_setting(SETTINGS_PATH, "X_MONITOR_HOME", str(target_home))
    print(f"  ✓ {SETTINGS_PATH}: X_MONITOR_HOME {status}")
    if status != "unchanged":
        print(f"    (restart Claude Code so the new env is picked up)")

    # Credentials: bidirectional bootstrap via the synced home
    shared_creds = target_home / "credentials.json"
    local_has = CREDS_PATH.exists()
    shared_has = shared_creds.exists()

    if args.share_credentials:
        if not local_has:
            sys.exit(
                f"--share-credentials requires {CREDS_PATH} to exist locally; "
                "nothing to share."
            )
        import shutil
        shared_creds.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(CREDS_PATH, shared_creds)
        os.chmod(shared_creds, 0o600)
        print(f"  ✓ copied credentials → {shared_creds} (mode 600)")
        print(f"    other Macs running `setup` will auto-install them locally")
        shared_has = True

    if local_has:
        print(f"  ✓ credentials present at {CREDS_PATH}")
    elif shared_has:
        import shutil
        CREDS_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(shared_creds, CREDS_PATH)
        os.chmod(CREDS_PATH, 0o600)
        print(f"  ✓ installed credentials from synced home → {CREDS_PATH}")
    else:
        print(f"  ✗ no credentials at {CREDS_PATH} or {shared_creds}")
        print(f"    Options:")
        print(f"      • on your other Mac, run: x_monitor.py setup --share-credentials")
        print(f"        then re-run setup here")
        print(f"      • or write {CREDS_PATH} with {{\"bearer_token\": \"...\"}}")

    # Final doctor (re-resolve home from the env we just wrote, if env not yet set in this proc)
    if not os.environ.get("X_MONITOR_HOME"):
        os.environ["X_MONITOR_HOME"] = str(target_home)
    print()
    cmd_doctor(argparse.Namespace(api=False))


def cmd_doctor(args: argparse.Namespace) -> None:
    ok = True
    print(f"[doctor] x-monitor")
    print(f"  home:        {home_dir()}")

    home = home_dir()
    try:
        home.mkdir(parents=True, exist_ok=True)
        probe = home / ".write-probe"
        probe.write_text("ok")
        probe.unlink()
        print(f"  cache dir:   writable")
    except OSError as e:
        print(f"  cache dir:   FAIL — {e}")
        ok = False

    icloud = "Mobile Documents/com~apple~CloudDocs" in str(home)
    if icloud:
        print(f"  sync:        iCloud Drive (cross-machine OK)")
    else:
        print(f"  sync:        local only — set X_MONITOR_HOME to an iCloud path")
        print(f"               for cross-machine sharing")

    sp = state_path()
    if sp.exists():
        try:
            s = json.loads(sp.read_text())
            n = len(s.get("subscriptions", {}))
            print(f"  state.json:  ok ({n} subscription{'s' if n != 1 else ''})")
        except json.JSONDecodeError as e:
            print(f"  state.json:  CORRUPT — {e}")
            ok = False
    else:
        print(f"  state.json:  not yet created (run `add` first)")

    td = tweets_dir()
    if td.exists():
        files = list(td.glob("*.jsonl"))
        total = 0
        for f in files:
            with f.open() as fh:
                total += sum(1 for _ in fh)
        print(f"  archive:     {len(files)} handle(s), {total} tweet(s) cached")
    else:
        print(f"  archive:     empty")

    src = "X_BEARER_TOKEN env" if os.environ.get("X_BEARER_TOKEN") else (
        f"{CREDS_PATH}" if CREDS_PATH.exists() else "MISSING"
    )
    print(f"  bearer:      loaded from {src}")
    if src == "MISSING":
        ok = False

    if args.api:
        print(f"  api ping:    fetching @x (costs $0.010 for 1 user lookup)...")
        try:
            user = lookup_user("x")
            print(f"  api ping:    ok — resolved @x to user_id {user['id']}")
        except SystemExit as e:
            print(f"  api ping:    FAIL — {e}")
            ok = False
    else:
        print(f"  api ping:    skipped (pass --api to verify, costs $0.010)")

    print(f"\n[doctor] {'PASS — ready' if ok else 'FAIL — fix issues above'}")
    if not ok:
        sys.exit(1)


def cmd_add(args: argparse.Namespace) -> None:
    handle = normalize_handle(args.handle)
    state = load_state()
    if handle in state["subscriptions"]:
        print(f"Already subscribed to @{handle}.", file=sys.stderr)
        return
    user = lookup_user(handle)
    latest = fetch_tweets(user["id"], since_id=None, max_results=5)
    tweets = latest.get("data") or []
    archived = archive_tweets(handle, tweets)
    latest_id = tweets[0]["id"] if tweets else None
    state["subscriptions"][handle] = {
        "user_id": user["id"],
        "name": user.get("name"),
        "username": user.get("username", handle),
        "added_at": now_iso(),
        "last_seen_id": latest_id,
        "last_checked_at": now_iso(),
    }
    save_state(state)
    print(f"Subscribed to @{user.get('username', handle)} ({user.get('name')}).")
    if latest_id:
        print(f"  Baseline tweet id: {latest_id}")
    print(f"  Archived {archived} tweet(s) to {archive_path(handle)}")


def cmd_rm(args: argparse.Namespace) -> None:
    handle = normalize_handle(args.handle)
    state = load_state()
    if handle not in state["subscriptions"]:
        print(f"Not subscribed to @{handle}.", file=sys.stderr)
        sys.exit(1)
    del state["subscriptions"][handle]
    save_state(state)
    print(f"Unsubscribed from @{handle}.")


def cmd_list(args: argparse.Namespace) -> None:
    state = load_state()
    subs = state["subscriptions"]
    if args.json:
        print(json.dumps(subs, indent=2))
        return
    if not subs:
        print("No subscriptions. Add one with: x_monitor.py add <handle>")
        return
    for handle, sub in subs.items():
        last = sub.get("last_checked_at", "never")
        print(f"@{handle:<20} {sub.get('name','')!r:<30} last_checked={last}")


def cmd_check(args: argparse.Namespace) -> None:
    state = load_state()
    subs = state["subscriptions"]
    if not subs:
        out = {"checked_at": now_iso(), "results": [], "note": "no subscriptions"}
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            print("No subscriptions to check.")
        return

    targets = [args.handle.lstrip("@").lower()] if args.handle else list(subs.keys())
    results = []
    for handle in targets:
        sub = subs.get(handle)
        if not sub:
            results.append({"handle": handle, "error": "not subscribed"})
            continue
        try:
            res = fetch_tweets(
                sub["user_id"],
                since_id=sub.get("last_seen_id"),
                max_results=args.limit,
            )
        except SystemExit as e:
            results.append({"handle": handle, "error": str(e)})
            continue

        tweets = res.get("data") or []
        archive_tweets(handle, tweets)
        new = [_summarize_tweet(t) for t in tweets]
        if new:
            sub["last_seen_id"] = new[0]["id"]
        sub["last_checked_at"] = now_iso()
        results.append(
            {
                "handle": handle,
                "name": sub.get("name"),
                "user_id": sub["user_id"],
                "new_count": len(new),
                "tweets": new,
            }
        )

    save_state(state)

    run = {
        "checked_at": now_iso(),
        "results": results,
        "total_new": sum(r.get("new_count", 0) for r in results),
    }
    runs_dir().mkdir(parents=True, exist_ok=True)
    run_path = runs_dir() / f"{run['checked_at'].replace(':','-')}.json"
    run_path.write_text(json.dumps(run, indent=2))

    if args.json:
        print(json.dumps(run, indent=2))
        return

    print(f"Checked {len(results)} handle(s) at {run['checked_at']}.")
    print(f"Total new posts: {run['total_new']}")
    for r in results:
        if r.get("error"):
            print(f"  @{r['handle']}: error — {r['error']}")
            continue
        print(f"  @{r['handle']}: {r['new_count']} new")
        for t in r.get("tweets", []):
            preview = t["text"].replace("\n", " ")[:120]
            print(f"    [{t['created_at']}] {preview}")


def cmd_tweets(args: argparse.Namespace) -> None:
    handle = normalize_handle(args.handle)
    archive = read_archive(handle)
    if not archive:
        print(f"No archive for @{handle}. Run `add` or `check` first.", file=sys.stderr)
        sys.exit(1)

    archive.sort(key=lambda t: t.get("created_at", ""), reverse=True)

    if args.since:
        cutoff = args.since
        archive = [t for t in archive if (t.get("created_at") or "") >= cutoff]
    if args.grep:
        needle = args.grep.lower()
        archive = [t for t in archive if needle in (t.get("text") or "").lower()]
    if args.limit:
        archive = archive[: args.limit]

    if args.json:
        print(json.dumps(archive, indent=2, ensure_ascii=False))
        return
    if not archive:
        print(f"No tweets matched.")
        return
    for t in archive:
        text = (t.get("text") or "").replace("\n", " ")
        print(f"[{t.get('created_at')}] {t['id']}")
        print(f"  {text}")


def cmd_runs(args: argparse.Namespace) -> None:
    rd = runs_dir()
    rd.mkdir(parents=True, exist_ok=True)
    files = sorted(rd.glob("*.json"))
    if args.which == "latest":
        if not files:
            print("No runs yet.", file=sys.stderr)
            sys.exit(1)
        data = json.loads(files[-1].read_text())
        print(json.dumps(data, indent=2) if args.json else _render_run(data))
        return

    files = files[-args.limit :] if args.limit else files
    if args.json:
        print(json.dumps([json.loads(f.read_text()) for f in files], indent=2))
        return
    if not files:
        print("No runs yet.")
        return
    for f in files:
        data = json.loads(f.read_text())
        print(f"{data['checked_at']}  total_new={data.get('total_new', 0)}")


def _render_run(run: dict) -> str:
    lines = [f"Run at {run['checked_at']} — {run.get('total_new', 0)} new posts"]
    for r in run.get("results", []):
        if r.get("error"):
            lines.append(f"  @{r['handle']}: error — {r['error']}")
            continue
        lines.append(f"  @{r['handle']} ({r.get('name','')}): {r['new_count']} new")
        for t in r.get("tweets", []):
            preview = t["text"].replace("\n", " ")[:200]
            lines.append(f"    [{t['created_at']}] {preview}")
    return "\n".join(lines)


# ---------- main ----------

def main(argv: Optional[list[str]] = None) -> None:
    p = argparse.ArgumentParser(prog="x_monitor.py", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("setup", help="one-shot cross-machine configuration")
    sp.add_argument("--home", help="target cache home (default: iCloud Drive/x-monitor)")
    sp.add_argument("--share-credentials", action="store_true",
                    help="copy local creds into synced home so other Macs auto-install them")
    sp.set_defaults(func=cmd_setup)

    sp = sub.add_parser("doctor", help="sanity-check setup before running")
    sp.add_argument("--api", action="store_true",
                    help="also do a $0.010 user lookup to verify auth")
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("add", help="subscribe a handle")
    sp.add_argument("handle")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("rm", help="unsubscribe a handle")
    sp.add_argument("handle")
    sp.set_defaults(func=cmd_rm)

    sp = sub.add_parser("list", help="list subscriptions")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("check", help="check for new posts")
    sp.add_argument("--handle", help="only check this handle")
    sp.add_argument("--limit", type=int, default=20, help="max tweets per handle (5-100)")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("tweets", help="query the local archive (no API)")
    sp.add_argument("handle")
    sp.add_argument("--since", help="ISO date/time prefix, e.g. 2026-04-01")
    sp.add_argument("--grep", help="case-insensitive substring match on text")
    sp.add_argument("--limit", type=int, default=0, help="0 = no limit")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_tweets)

    sp = sub.add_parser("runs", help="show past run summaries")
    sp.add_argument("which", nargs="?", default="all", choices=["all", "latest"])
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_runs)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
