#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "click>=8.0",
#   "google-auth>=2.0",
#   "google-auth-oauthlib>=1.0",
# ]
# ///
"""YouTube OAuth one-time flow.

Opens a browser, user picks account + grants scopes, refresh token is saved to
$YOUTUBE_TOKEN_PATH (default ~/.config/youtube-upload/token.json).
"""

import json
import os
import sys
from pathlib import Path

import click
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

DEFAULT_CLIENT_SECRET = Path.home() / ".config/youtube-upload/client-secret.json"
DEFAULT_TOKEN_PATH = Path.home() / ".config/youtube-upload/token.json"


@click.group()
def cli():
    """Auth CLI."""


@cli.command()
@click.option("--client-secret", "client_secret",
              type=click.Path(dir_okay=False),
              default=None)
@click.option("--token", "token_path", type=click.Path(), default=None)
def youtube(client_secret: str | None, token_path: str | None):
    """Run OAuth flow and save refresh token."""
    client_secret_path = Path(client_secret
                              or os.environ.get("YOUTUBE_CLIENT_SECRET_PATH")
                              or DEFAULT_CLIENT_SECRET)
    token = Path(token_path
                 or os.environ.get("YOUTUBE_TOKEN_PATH")
                 or DEFAULT_TOKEN_PATH)

    if not client_secret_path.exists():
        click.echo(
            f"Error: client_secret.json not found at {client_secret_path}\n\n"
            "Create one via Google Cloud Console:\n"
            "  1. https://console.cloud.google.com -> create/select project\n"
            "  2. APIs & Services -> Library -> enable YouTube Data API v3\n"
            "  3. OAuth consent screen -> External -> Testing mode\n"
            "     (add your Gmail as a test user)\n"
            "  4. Credentials -> Create OAuth client -> Desktop app\n"
            "  5. Download JSON and save to the path above.",
            err=True,
        )
        sys.exit(1)

    token.parent.mkdir(parents=True, exist_ok=True)

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    token.write_text(creds.to_json())
    click.echo(f"Saved refresh token to {token}")


if __name__ == "__main__":
    cli()
