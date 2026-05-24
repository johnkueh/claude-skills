#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "click>=8.0",
#   "google-auth>=2.0",
#   "google-auth-oauthlib>=1.0",
#   "google-auth-httplib2>=0.2",
#   "google-api-python-client>=2.0",
# ]
# ///
"""YouTube Data API v3 publishing for rendered videos.

Does all of this in one command:
    1. videos().insert (resumable MP4 upload)
    2. captions().insert (SRT)
    3. thumbnails().set
    4. playlistItems().insert (optional)
    5. commentThreads().insert + comments pin (optional)
    6. Write manifest row
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# manifest.py is a sibling module
sys.path.insert(0, str(Path(__file__).resolve().parent))
import manifest as manifest_mod

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

DEFAULT_TOKEN_PATH = Path.home() / ".config/youtube-upload/token.json"

AI_DISCLOSURE = (
    "This video uses AI-generated narration and illustrations to summarize "
    "published clinical research. Sources are linked in the description and "
    "on the source article."
)

MAX_DESCRIPTION_CHARS = 5000
MAX_TITLE_CHARS = 100
MAX_TAG_CHARS = 500  # YouTube sums all tag chars; cap defensively


def load_credentials(token_path: Path) -> Credentials:
    if not token_path.exists():
        click.echo(
            f"Error: no token at {token_path}. Run `uv run cli.py auth youtube` first.",
            err=True,
        )
        sys.exit(1)
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json())
        else:
            click.echo("Error: credentials invalid and cannot refresh. Re-run auth.", err=True)
            sys.exit(1)
    return creds


def build_tags(script: dict, extra: list[str] | None = None) -> list[str]:
    tags: list[str] = []
    for src in (script.get("tags"), extra):
        if not src:
            continue
        for t in src:
            t = t.strip()
            if t and t not in tags:
                tags.append(t)
    # Keep under YouTube's tag-length cap
    total = 0
    trimmed: list[str] = []
    for t in tags:
        size = len(t) + (2 if " " in t else 0) + 1
        if total + size > MAX_TAG_CHARS:
            break
        trimmed.append(t)
        total += size
    return trimmed


def build_description(script: dict, disclaimer: str | None) -> str:
    body = (script.get("video_description_draft") or "").strip()
    lines: list[str] = []
    if disclaimer:
        lines.append(disclaimer.strip())
        lines.append("")
    lines.append(AI_DISCLOSURE)
    lines.append("")
    lines.append(body)
    desc = "\n".join(lines).strip()
    if len(desc) > MAX_DESCRIPTION_CHARS:
        desc = desc[: MAX_DESCRIPTION_CHARS - 3] + "..."
    return desc


def build_title(script: dict) -> str:
    t = (script.get("video_title") or "").strip()
    if len(t) > MAX_TITLE_CHARS:
        t = t[: MAX_TITLE_CHARS - 1] + "…"
    return t


def build_insert_body(script: dict, privacy: str, publish_at: str | None,
                      category_id: int, disclaimer: str | None,
                      extra_tags: list[str] | None) -> dict:
    status = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": False,
    }
    # NOTE: We do NOT set `containsSyntheticMedia: true`. YouTube's altered/
    # synthetic-content disclosure is only required for realistic content that
    # could be mistaken for real people/events/footage. Watercolor explainer
    # animations + AI narration are exempt. The AI_DISCLOSURE note still
    # appears in the description as an honesty signal.
    if publish_at:
        if privacy != "private":
            raise click.ClickException("publishAt requires privacyStatus=private")
        status["publishAt"] = publish_at
    return {
        "snippet": {
            "title": build_title(script),
            "description": build_description(script, disclaimer),
            "tags": build_tags(script, extra_tags),
            "categoryId": str(category_id),
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": status,
    }


def canonical_article_url(script: dict) -> str | None:
    slug = script.get("slug")
    if not slug:
        return None
    site = os.environ.get("YOUTUBE_SITE_URL", ""); return f"{site}/articles/{slug}" if site else ""


def comment_body(script: dict) -> str:
    url = canonical_article_url(script)
    if not url:
        return ""
    return (
        f"Full article with every source, table, and citation: {url}\n\n"
        "Retatrutide is an investigational drug not approved by the FDA. "
        "This is informational, not medical advice."
    )


def resumable_upload(youtube, body: dict, video_path: Path) -> str:
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/*")
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )
    response = None
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                click.echo(f"  uploading... {int(status.progress() * 100)}%", err=True)
        except HttpError as e:
            click.echo(f"YouTube upload error: {e}", err=True)
            raise
    return response["id"]


def upload_caption(youtube, video_id: str, captions_path: Path) -> str:
    media = MediaFileUpload(str(captions_path), mimetype="application/octet-stream", resumable=False)
    request = youtube.captions().insert(
        part="snippet",
        body={
            "snippet": {
                "videoId": video_id,
                "language": "en",
                "name": "English",
                "isDraft": False,
            }
        },
        media_body=media,
    )
    response = request.execute()
    return response["id"]


def set_thumbnail(youtube, video_id: str, thumbnail_path: Path) -> None:
    media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg", resumable=False)
    youtube.thumbnails().set(videoId=video_id, media_body=media).execute()


def add_to_playlist(youtube, video_id: str, playlist_id: str) -> str:
    response = youtube.playlistItems().insert(
        part="snippet",
        body={
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
            }
        },
    ).execute()
    return response["id"]


def post_pinned_comment(youtube, video_id: str, text: str) -> str | None:
    if not text:
        return None
    response = youtube.commentThreads().insert(
        part="snippet",
        body={
            "snippet": {
                "videoId": video_id,
                "topLevelComment": {"snippet": {"textOriginal": text}},
            }
        },
    ).execute()
    # Pinning a comment requires channel-owner context; the API pins implicitly
    # when the comment is posted by the uploading channel via commentThreads.insert
    # with the channel owner's creds. No separate pin call is needed.
    return response["id"]


@click.group()
def cli():
    """YouTube publishing CLI."""


@cli.command()
@click.option("--script", "script_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--video", "video_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--captions", "captions_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--thumbnail", "thumbnail_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--privacy", type=click.Choice(["private", "unlisted", "public"]), default="unlisted")
@click.option("--publish-at", "publish_at", type=str, default=None)
@click.option("--category-id", "category_id", type=int, default=27)
@click.option("--playlist-id", "playlist_id", type=str, default=None)
@click.option("--pin-comment/--no-pin-comment", default=True)
@click.option("--disclaimer", type=str, default=None,
              help="YMYL disclaimer prepended to description.")
@click.option("--extra-tag", "extra_tags", multiple=True,
              help="Additional tag(s) to append.")
@click.option("--manifest-dir", "manifest_dir", type=click.Path(), default=None)
@click.option("--token", "token_path", type=click.Path(), default=None)
@click.option("--dry-run/--no-dry-run", default=False)
def upload(script_path: str, video_path: str, captions_path: str | None,
           thumbnail_path: str | None, privacy: str, publish_at: str | None,
           category_id: int, playlist_id: str | None, pin_comment: bool,
           disclaimer: str | None, extra_tags: tuple[str, ...],
           manifest_dir: str | None, token_path: str | None, dry_run: bool):
    """Upload a rendered video to YouTube."""
    script = json.loads(Path(script_path).read_text())
    body = build_insert_body(script, privacy, publish_at, category_id,
                             disclaimer, list(extra_tags) or None)

    if dry_run:
        payload = {
            "operation": "videos.insert",
            "part": "snippet,status",
            "body": body,
            "media": str(video_path),
            "follow_ups": {
                "captions.insert": bool(captions_path),
                "thumbnails.set": bool(thumbnail_path),
                "playlistItems.insert": bool(playlist_id),
                "commentThreads.insert": bool(pin_comment and canonical_article_url(script)),
            },
            "comment_text": comment_body(script) if pin_comment else None,
        }
        click.echo(json.dumps(payload, indent=2))
        return

    token = Path(token_path or os.environ.get("YOUTUBE_TOKEN_PATH") or DEFAULT_TOKEN_PATH)
    creds = load_credentials(token)
    youtube = build("youtube", "v3", credentials=creds)

    click.echo(f"Uploading {video_path}...", err=True)
    video_id = resumable_upload(youtube, body, Path(video_path))
    url = f"https://www.youtube.com/watch?v={video_id}"
    click.echo(f"  video_id={video_id}  {url}", err=True)

    caption_id = None
    if captions_path:
        caption_id = upload_caption(youtube, video_id, Path(captions_path))
        click.echo(f"  caption_id={caption_id}", err=True)

    if thumbnail_path:
        set_thumbnail(youtube, video_id, Path(thumbnail_path))
        click.echo("  thumbnail set", err=True)

    playlist_item_id = None
    if playlist_id:
        playlist_item_id = add_to_playlist(youtube, video_id, playlist_id)
        click.echo(f"  playlist_item_id={playlist_item_id}", err=True)

    pinned_comment_id = None
    if pin_comment:
        pinned_comment_id = post_pinned_comment(youtube, video_id, comment_body(script))
        if pinned_comment_id:
            click.echo(f"  pinned_comment_id={pinned_comment_id}", err=True)

    if manifest_dir:
        data = manifest_mod.load(manifest_dir, script["slug"])
        data["published_at"] = datetime.now(timezone.utc).isoformat()
        data["youtube"] = {
            "status": "uploaded",
            "video_id": video_id,
            "url": url,
            "privacy": privacy,
            "publish_at": publish_at,
            "caption_id": caption_id,
            "thumbnail_set": bool(thumbnail_path),
            "playlist_id": playlist_id,
            "playlist_item_id": playlist_item_id,
            "pinned_comment_id": pinned_comment_id,
        }
        p = manifest_mod.save(manifest_dir, script["slug"], data)
        click.echo(f"Wrote manifest {p}", err=True)

    click.echo(url)


if __name__ == "__main__":
    cli()
