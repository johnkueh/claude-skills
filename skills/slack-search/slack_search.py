#!/usr/bin/env python3
"""
Slack Search — find messages, channels, users, and threads.

Usage:
    slack_search.py search "keyword" [--channel C] [--from U] [--limit N] [--json]
    slack_search.py thread <permalink-or-channel:ts> [--json]
    slack_search.py channels [--limit N] [--json]
    slack_search.py users [--limit N] [--json]
    slack_search.py me [--json]

Token: reads SLACK_USER_TOKEN from the environment. Falls back to a `.env`
in the current working directory if present.
"""

import argparse
import json as json_module
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
except ImportError:
    print("Error: slack-sdk not installed. Run: pip install slack-sdk", file=sys.stderr)
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.getcwd(), ".env"))
except ImportError:
    pass


_user_cache: dict[str, dict] = {}

DEFAULT_DOWNLOAD_ROOT = Path.home() / ".cache" / "slack-search" / "files"


def get_client() -> WebClient:
    token = os.environ.get("SLACK_USER_TOKEN")
    if not token:
        print(
            "Error: SLACK_USER_TOKEN not set.\n"
            "Add it to ~/.claude/settings.json under env, "
            "or to a .env in the current directory.",
            file=sys.stderr,
        )
        sys.exit(1)
    return WebClient(token=token)


def fmt_ts(ts: str) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return ts


def resolve_user(client: WebClient, user_id: str) -> str:
    """Resolve a user ID to @handle. Cached per process."""
    if not user_id:
        return "?"
    if user_id in _user_cache:
        return _user_cache[user_id].get("name", user_id)
    try:
        info = client.users_info(user=user_id).get("user", {})
        _user_cache[user_id] = info
        return info.get("name", user_id)
    except SlackApiError:
        return user_id


def expand_mentions(client: WebClient, text: str) -> str:
    """Replace <@U123> with @username."""
    def repl(m):
        return f"@{resolve_user(client, m.group(1))}"
    return re.sub(r"<@([A-Z0-9]+)(?:\|[^>]+)?>", repl, text or "")


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_name(name: str) -> str:
    cleaned = _SAFE_NAME_RE.sub("_", name).strip("_")
    return cleaned or "file"


def _file_summary(f: dict) -> dict:
    """Project a Slack file object down to the fields we surface."""
    return {
        "id": f.get("id"),
        "name": f.get("name"),
        "title": f.get("title"),
        "mimetype": f.get("mimetype"),
        "filetype": f.get("filetype"),
        "size": f.get("size"),
        "url_private": f.get("url_private"),
        "url_private_download": f.get("url_private_download"),
        "permalink": f.get("permalink"),
    }


def _download_one(url: str, dest: Path, token: str) -> Optional[str]:
    """Download a single Slack file URL with bearer auth. Returns local path or None.

    Slack returns the workspace login HTML (instead of the file) when the token lacks
    the `files:read` scope; detect that and surface a clear error.
    """
    if not url:
        return None
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            ctype = resp.headers.get("Content-Type", "")
            if ctype.startswith("text/html"):
                print(
                    f"  ! download blocked for {url}: Slack returned login HTML. "
                    "Token likely missing the `files:read` scope — add it in the "
                    "Slack App OAuth settings and reinstall.",
                    file=sys.stderr,
                )
                return None
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as out:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    out.write(chunk)
        return str(dest)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        print(f"  ! download failed for {url}: {e}", file=sys.stderr)
        return None


def download_message_files(
    files: list[dict], download_dir: Path, token: str, message_ts: str
) -> list[dict]:
    """Download every file attached to a message. Annotates each file dict with local_path."""
    annotated = []
    for idx, f in enumerate(files or []):
        info = _file_summary(f)
        url = info.get("url_private_download") or info.get("url_private")
        if not url:
            annotated.append(info)
            continue
        ext = ""
        if info.get("name") and "." in info["name"]:
            ext = "." + info["name"].rsplit(".", 1)[-1]
        elif info.get("filetype"):
            ext = "." + info["filetype"]
        base = info.get("id") or f"f{idx}"
        ts_safe = (message_ts or "0").replace(".", "_")
        fname = _safe_name(f"{ts_safe}_{base}{ext}")
        local = _download_one(url, download_dir / fname, token)
        if local:
            info["local_path"] = local
        annotated.append(info)
    return annotated


def resolve_download_dir(arg_value: Optional[str], scope: str) -> Optional[Path]:
    """Translate the --download CLI value into a target directory, or None if disabled."""
    if arg_value is None:
        return None
    if arg_value == "__DEFAULT__":
        safe_scope = _safe_name(scope) or "misc"
        return DEFAULT_DOWNLOAD_ROOT / safe_scope
    return Path(arg_value).expanduser()


PERMALINK_RE = re.compile(
    r"https?://[^/]+/archives/(?P<channel>[A-Z0-9]+)/p(?P<ts>\d+)(?:\?.*)?$"
)


def parse_thread_target(target: str) -> tuple[str, str]:
    """Accept either a Slack permalink or `channel:ts` form. Returns (channel, ts)."""
    m = PERMALINK_RE.match(target.strip())
    if m:
        ts_raw = m.group("ts")
        ts = f"{ts_raw[:-6]}.{ts_raw[-6:]}"
        return m.group("channel"), ts
    if ":" in target:
        ch, ts = target.split(":", 1)
        return ch.strip(), ts.strip()
    print(
        "Error: pass a Slack permalink (https://*.slack.com/archives/.../p...)"
        " or `<channel-id>:<ts>`.",
        file=sys.stderr,
    )
    sys.exit(1)


def search_messages(query: str, channel: Optional[str], from_user: Optional[str],
                    limit: int, as_json: bool, download: Optional[str]) -> None:
    client = get_client()
    q = query
    if channel:
        q += f" in:{channel}"
    if from_user:
        q += f" from:{from_user}"

    try:
        result = client.search_messages(query=q, count=limit, sort="timestamp")
    except SlackApiError as e:
        print(f"Error: {e.response['error']}", file=sys.stderr)
        if e.response["error"] == "missing_scope":
            print("Need scope: search:read", file=sys.stderr)
        sys.exit(1)

    matches = result.get("messages", {}).get("matches", [])
    download_dir = resolve_download_dir(download, scope=f"search_{q}")
    token = os.environ.get("SLACK_USER_TOKEN", "")

    rendered_matches = []
    for m in matches:
        files = m.get("files") or []
        if download_dir is not None and files:
            files_out = download_message_files(files, download_dir, token, m.get("ts", ""))
        else:
            files_out = [_file_summary(f) for f in files]
        rendered_matches.append({
            "raw": m,
            "files": files_out,
        })

    if as_json:
        out = [
            {
                "channel": m["raw"].get("channel", {}).get("name"),
                "channel_id": m["raw"].get("channel", {}).get("id"),
                "user": m["raw"].get("username"),
                "ts": m["raw"].get("ts"),
                "time": fmt_ts(m["raw"].get("ts", "")),
                "text": expand_mentions(client, m["raw"].get("text", "")),
                "permalink": m["raw"].get("permalink"),
                "files": m["files"],
            }
            for m in rendered_matches
        ]
        print(json_module.dumps(out, indent=2))
        return

    if not matches:
        print(f"No messages for: {q}")
        return

    print(f"\n=== {len(matches)} match(es) for: {q} ===\n")
    for entry in rendered_matches:
        m = entry["raw"]
        ch = m.get("channel", {}).get("name", "?")
        u = m.get("username", "?")
        text = expand_mentions(client, m.get("text", ""))
        print(f"#{ch} | @{u} | {fmt_ts(m.get('ts', ''))}")
        print(f"  {text}")
        if m.get("permalink"):
            print(f"  {m['permalink']}")
        for f in entry["files"]:
            label = f.get("name") or f.get("title") or f.get("id") or "(file)"
            mime = f.get("mimetype") or ""
            local = f.get("local_path")
            tail = f" -> {local}" if local else ""
            print(f"  [file] {label} ({mime}){tail}")
        print()


def fetch_thread(target: str, as_json: bool, download: Optional[str]) -> None:
    channel, ts = parse_thread_target(target)
    client = get_client()
    try:
        result = client.conversations_replies(channel=channel, ts=ts, limit=200)
    except SlackApiError as e:
        print(f"Error: {e.response['error']}", file=sys.stderr)
        sys.exit(1)

    msgs = result.get("messages", [])
    download_dir = resolve_download_dir(download, scope=f"{channel}_{ts}")
    token = os.environ.get("SLACK_USER_TOKEN", "")

    rendered = []
    for m in msgs:
        files = m.get("files") or []
        if download_dir is not None and files:
            files_out = download_message_files(files, download_dir, token, m.get("ts", ""))
        else:
            files_out = [_file_summary(f) for f in files]
        rendered.append({
            "user": resolve_user(client, m.get("user", "")),
            "user_id": m.get("user"),
            "ts": m.get("ts"),
            "time": fmt_ts(m.get("ts", "")),
            "text": expand_mentions(client, m.get("text", "")),
            "files": files_out,
        })

    if as_json:
        out = {
            "channel": channel,
            "thread_ts": ts,
            "count": len(rendered),
            "messages": rendered,
        }
        if download_dir is not None:
            out["download_dir"] = str(download_dir)
        print(json_module.dumps(out, indent=2))
        return

    if not rendered:
        print("No messages in thread.")
        return

    print(f"\n=== Thread {channel}:{ts} ({len(rendered)} messages) ===\n")
    for m in rendered:
        print(f"[{m['time']}] @{m['user']}: {m['text']}")
        for f in m["files"]:
            label = f.get("name") or f.get("title") or f.get("id") or "(file)"
            mime = f.get("mimetype") or ""
            local = f.get("local_path")
            tail = f" -> {local}" if local else ""
            print(f"   [file] {label} ({mime}){tail}")
        print()


def list_channels(limit: int, as_json: bool) -> None:
    client = get_client()
    try:
        public = client.conversations_list(types="public_channel", limit=limit,
                                           exclude_archived=True).get("channels", [])
        private = client.conversations_list(types="private_channel", limit=limit,
                                            exclude_archived=True).get("channels", [])
    except SlackApiError as e:
        print(f"Error: {e.response['error']}", file=sys.stderr)
        sys.exit(1)

    chans = sorted(public + private, key=lambda c: c.get("name", "").lower())

    if as_json:
        print(json_module.dumps([
            {
                "id": c.get("id"),
                "name": c.get("name"),
                "is_private": c.get("is_private", False),
                "members": c.get("num_members"),
                "purpose": c.get("purpose", {}).get("value", ""),
            }
            for c in chans
        ], indent=2))
        return

    print(f"\n=== Channels ({len(chans)}) ===\n")
    for c in chans:
        icon = "🔒" if c.get("is_private") else "📢"
        print(f"{icon} #{c.get('name')} ({c.get('num_members', '?')} members) [{c.get('id')}]")
        purpose = (c.get("purpose", {}).get("value") or "")[:60]
        if purpose:
            print(f"    {purpose}")


def list_users(limit: int, as_json: bool) -> None:
    client = get_client()
    try:
        members = client.users_list(limit=limit).get("members", [])
    except SlackApiError as e:
        print(f"Error: {e.response['error']}", file=sys.stderr)
        sys.exit(1)

    active = [m for m in members if not m.get("is_bot") and not m.get("deleted")]
    active.sort(key=lambda u: (u.get("real_name") or "").lower())

    if as_json:
        print(json_module.dumps([
            {
                "id": u.get("id"),
                "name": u.get("name"),
                "real_name": u.get("real_name"),
                "title": u.get("profile", {}).get("title", ""),
            }
            for u in active
        ], indent=2))
        return

    print(f"\n=== Users ({len(active)}) ===\n")
    for u in active:
        print(f"👤 {u.get('real_name', '')} (@{u.get('name', '')}) [{u.get('id')}]")
        title = u.get("profile", {}).get("title", "")
        if title:
            print(f"    {title}")


def get_my_info(as_json: bool) -> None:
    client = get_client()
    try:
        auth = client.auth_test()
        user = client.users_info(user=auth.get("user_id", "")).get("user", {})
    except SlackApiError as e:
        print(f"Error: {e.response['error']}", file=sys.stderr)
        sys.exit(1)

    info = {
        "user_id": auth.get("user_id"),
        "name": user.get("real_name"),
        "username": user.get("name"),
        "email": user.get("profile", {}).get("email"),
        "title": user.get("profile", {}).get("title"),
        "team": auth.get("team"),
    }

    if as_json:
        print(json_module.dumps(info, indent=2))
        return

    print("\n=== Slack Profile ===\n")
    for k, v in info.items():
        print(f"{k:9} {v or 'N/A'}")


def main():
    p = argparse.ArgumentParser(
        description="Slack search and lookup utilities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s search "deploy"
  %(prog)s search "bug" --channel engineering --from sam --limit 10
  %(prog)s thread https://yourteam.slack.com/archives/C04TS1N2WPR/p1777349051739419
  %(prog)s thread C04TS1N2WPR:1777349051.739419 --json
  %(prog)s channels --json
  %(prog)s users
  %(prog)s me
""",
    )
    sub = p.add_subparsers(dest="command")

    s = sub.add_parser("search", help="Search messages")
    s.add_argument("query")
    s.add_argument("--channel", "-c")
    s.add_argument("--from", "-f", dest="from_user")
    s.add_argument("--limit", "-l", type=int, default=20)
    s.add_argument("--json", "-j", action="store_true")
    s.add_argument(
        "--download", "-d",
        nargs="?", const="__DEFAULT__", default=None,
        metavar="DIR",
        help="Download file attachments. Pass DIR or omit to use ~/.cache/slack-search/files/.",
    )

    t = sub.add_parser("thread", help="Fetch a thread by permalink or channel:ts")
    t.add_argument("target", help="Slack permalink or '<channel-id>:<ts>'")
    t.add_argument("--json", "-j", action="store_true")
    t.add_argument(
        "--download", "-d",
        nargs="?", const="__DEFAULT__", default=None,
        metavar="DIR",
        help="Download file attachments. Pass DIR or omit to use ~/.cache/slack-search/files/<channel>_<ts>/.",
    )

    c = sub.add_parser("channels", help="List channels")
    c.add_argument("--limit", "-l", type=int, default=200)
    c.add_argument("--json", "-j", action="store_true")

    u = sub.add_parser("users", help="List workspace users")
    u.add_argument("--limit", "-l", type=int, default=200)
    u.add_argument("--json", "-j", action="store_true")

    m = sub.add_parser("me", help="Show your Slack profile")
    m.add_argument("--json", "-j", action="store_true")

    args = p.parse_args()

    if not args.command:
        p.print_help()
        sys.exit(1)

    if args.command == "search":
        search_messages(args.query, args.channel, args.from_user, args.limit, args.json, args.download)
    elif args.command == "thread":
        fetch_thread(args.target, args.json, args.download)
    elif args.command == "channels":
        list_channels(args.limit, args.json)
    elif args.command == "users":
        list_users(args.limit, args.json)
    elif args.command == "me":
        get_my_info(args.json)


if __name__ == "__main__":
    main()
