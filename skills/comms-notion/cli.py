#!/usr/bin/env python3
"""Read content from a Notion page (URL or page ID) and return it as Markdown."""

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from notion_client import Client
    from notion_client.errors import APIResponseError
except ImportError:
    print("Error: notion-client not installed. Run: uv sync", file=sys.stderr)
    sys.exit(1)

try:
    from dotenv import load_dotenv
    # Load from CWD first, then skill dir as fallback
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass


PAGE_ID_RE = re.compile(r"([0-9a-f]{32})", re.IGNORECASE)
DASHED_ID_RE = re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)


def extract_page_id(url_or_id: str) -> str:
    """Extract a Notion page ID from a URL, dashed ID, or bare 32-char hex."""
    s = url_or_id.strip()
    m = DASHED_ID_RE.search(s)
    if m:
        return m.group(1).replace("-", "")
    m = PAGE_ID_RE.search(s)
    if m:
        return m.group(1)
    raise ValueError(f"Could not extract a Notion page ID from: {url_or_id!r}")


def to_dashed(page_id: str) -> str:
    p = page_id.replace("-", "")
    return f"{p[0:8]}-{p[8:12]}-{p[12:16]}-{p[16:20]}-{p[20:32]}"


def get_client() -> Client:
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        print(
            "Error: NOTION_TOKEN not set. Add to .env: NOTION_TOKEN=ntn_...",
            file=sys.stderr,
        )
        sys.exit(1)
    return Client(auth=token)


def rich_text_to_md(rich_text: list) -> str:
    """Convert Notion rich_text array to inline markdown."""
    out = []
    for rt in rich_text or []:
        text = rt.get("plain_text", "")
        if not text:
            continue
        ann = rt.get("annotations", {}) or {}
        href = rt.get("href")
        if ann.get("code"):
            text = f"`{text}`"
        if ann.get("bold"):
            text = f"**{text}**"
        if ann.get("italic"):
            text = f"*{text}*"
        if ann.get("strikethrough"):
            text = f"~~{text}~~"
        if href:
            text = f"[{text}]({href})"
        out.append(text)
    return "".join(out)


def get_page_title(page: dict) -> str:
    """Extract a page's title from its properties or fallback fields."""
    props = page.get("properties", {}) or {}
    for prop in props.values():
        if prop.get("type") == "title":
            return rich_text_to_md(prop.get("title", []))
    # Database row fallback (rare): use first title-like field
    return "Untitled"


EXT_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/heic": ".heic",
}


class ImageHandler:
    """Resolve image block URLs into the chosen output form.

    Modes:
        urls     — leave the original (signed) URL as-is
        download — fetch to ./images/<hash>.<ext>, rewrite to the relative path
        base64   — fetch and inline as a data: URL
        strip    — replace with `[image]` placeholder
    """

    def __init__(self, mode: str, out_dir: Optional[Path] = None):
        self.mode = mode
        self.out_dir = out_dir
        self.cache: dict[str, str] = {}
        self.downloaded: list[dict] = []

        if mode == "download":
            assert out_dir is not None
            (out_dir / "images").mkdir(parents=True, exist_ok=True)

    def render(self, url: str, alt: str = "image") -> str:
        if not url:
            return f"[{alt}]()"
        if self.mode == "urls":
            return f"![{alt}]({url})"
        if self.mode == "strip":
            return f"`[{alt}]`"
        if url in self.cache:
            return self.cache[url]

        try:
            data, mime = self._fetch(url)
        except Exception as e:
            print(f"warning: failed to fetch {url[:80]}…: {e}", file=sys.stderr)
            fallback = f"![{alt}]({url})"
            self.cache[url] = fallback
            return fallback

        if self.mode == "base64":
            b64 = base64.b64encode(data).decode("ascii")
            rendered = f"![{alt}](data:{mime};base64,{b64})"
        elif self.mode == "download":
            ext = EXT_BY_MIME.get(mime, ".bin")
            digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
            fname = f"img_{digest}{ext}"
            path = self.out_dir / "images" / fname
            path.write_bytes(data)
            rel = f"images/{fname}"
            rendered = f"![{alt}]({rel})"
            self.downloaded.append({
                "path": str(path),
                "relative": rel,
                "size": len(data),
                "mime": mime,
                "source_url": url,
            })
        else:
            rendered = f"![{alt}]({url})"

        self.cache[url] = rendered
        return rendered

    @staticmethod
    def _fetch(url: str) -> tuple[bytes, str]:
        req = urllib.request.Request(url, headers={"User-Agent": "notion-page-skill"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            mime = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
        if not mime:
            # Fall back to extension-based guess
            path = urllib.parse.urlparse(url).path
            mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        return data, mime


def fetch_block_children(client: Client, block_id: str) -> list:
    """Fetch all children of a block, paginated."""
    blocks = []
    cursor = None
    while True:
        kwargs = {"block_id": block_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = client.blocks.children.list(**kwargs)
        blocks.extend(resp.get("results", []))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return blocks


def render_block(
    client: Client,
    block: dict,
    indent: int = 0,
    images: Optional[ImageHandler] = None,
) -> str:
    """Render a single Notion block (and its children, recursively) as markdown."""
    btype = block.get("type", "")
    data = block.get(btype, {}) or {}
    pad = "  " * indent

    def rt(field="rich_text"):
        return rich_text_to_md(data.get(field, []))

    lines: list[str] = []

    if btype == "paragraph":
        text = rt()
        lines.append(f"{pad}{text}" if text else "")
    elif btype == "heading_1":
        lines.append(f"# {rt()}")
    elif btype == "heading_2":
        lines.append(f"## {rt()}")
    elif btype == "heading_3":
        lines.append(f"### {rt()}")
    elif btype == "bulleted_list_item":
        lines.append(f"{pad}- {rt()}")
    elif btype == "numbered_list_item":
        lines.append(f"{pad}1. {rt()}")
    elif btype == "to_do":
        checked = "x" if data.get("checked") else " "
        lines.append(f"{pad}- [{checked}] {rt()}")
    elif btype == "toggle":
        lines.append(f"{pad}- {rt()}")
    elif btype == "quote":
        for ln in (rt() or "").splitlines() or [""]:
            lines.append(f"{pad}> {ln}")
    elif btype == "callout":
        icon = (data.get("icon") or {}).get("emoji", "💡")
        lines.append(f"{pad}> {icon} {rt()}")
    elif btype == "code":
        lang = data.get("language", "") or ""
        code = "".join(t.get("plain_text", "") for t in data.get("rich_text", []))
        lines.append(f"```{lang}")
        lines.append(code)
        lines.append("```")
    elif btype == "divider":
        lines.append("---")
    elif btype == "bookmark" or btype == "embed":
        url = data.get("url", "")
        caption = rich_text_to_md(data.get("caption", []))
        lines.append(f"{pad}[{caption or url}]({url})")
    elif btype in ("image", "video", "file", "pdf"):
        f = data
        url = ""
        if f.get("type") == "external":
            url = f.get("external", {}).get("url", "")
        elif f.get("type") == "file":
            url = f.get("file", {}).get("url", "")
        caption = rich_text_to_md(data.get("caption", []))
        if btype == "image" and images is not None:
            lines.append(f"{pad}{images.render(url, alt=caption or 'image')}")
        else:
            prefix = "!" if btype == "image" else ""
            lines.append(f"{pad}{prefix}[{caption or btype}]({url})")
    elif btype == "child_page":
        lines.append(f"{pad}- 📄 **{data.get('title', 'Untitled')}** (child page)")
    elif btype == "child_database":
        lines.append(f"{pad}- 🗄️ **{data.get('title', 'Untitled')}** (database)")
    elif btype == "table":
        # Children rendering handles rows
        pass
    elif btype == "table_row":
        cells = data.get("cells", [])
        rendered = [rich_text_to_md(c) for c in cells]
        lines.append(f"{pad}| " + " | ".join(rendered) + " |")
    elif btype == "column_list" or btype == "column":
        # No own content; rely on children
        pass
    elif btype == "synced_block":
        pass
    elif btype == "equation":
        lines.append(f"{pad}$$ {data.get('expression', '')} $$")
    elif btype == "link_preview":
        lines.append(f"{pad}{data.get('url', '')}")
    else:
        # Unknown / unhandled types — emit a stub so nothing silently disappears
        lines.append(f"{pad}<!-- unsupported block: {btype} -->")

    # Recurse into children
    if block.get("has_children"):
        try:
            children = fetch_block_children(client, block["id"])
        except APIResponseError:
            children = []
        for child in children:
            child_md = render_block(client, child, indent=indent + 1, images=images)
            if child_md:
                lines.append(child_md)

    return "\n".join(l for l in lines if l is not None)


def fetch_page(
    url_or_id: str,
    max_chars: int = 0,
    images_mode: str = "urls",
    out_dir: Optional[Path] = None,
) -> dict:
    page_id = extract_page_id(url_or_id)
    client = get_client()

    try:
        page = client.pages.retrieve(page_id=to_dashed(page_id))
    except APIResponseError as e:
        return {
            "error": f"Failed to retrieve page: {e}",
            "hint": "Ensure the integration is added to the page (Share → Connections).",
        }

    title = get_page_title(page)

    images = ImageHandler(mode=images_mode, out_dir=out_dir)

    blocks = fetch_block_children(client, to_dashed(page_id))
    parts = [render_block(client, b, images=images) for b in blocks]
    content = "\n\n".join(p for p in parts if p.strip())
    content = re.sub(r"\n{3,}", "\n\n", content).strip()

    truncated = False
    if max_chars and len(content) > max_chars:
        content = content[:max_chars]
        truncated = True

    result = {
        "url": page.get("url", ""),
        "page_id": page_id,
        "title": title,
        "created_time": page.get("created_time", ""),
        "last_edited_time": page.get("last_edited_time", ""),
        "content": content,
        "content_length": len(content),
        "truncated": truncated,
        "images_mode": images_mode,
    }
    if images_mode == "download":
        result["output_dir"] = str(out_dir) if out_dir else None
        result["images"] = images.downloaded
    return result


def slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:60] or "page"


def main():
    parser = argparse.ArgumentParser(description="Read content from a Notion page.")
    parser.add_argument("url", help="Notion page URL or page ID")
    parser.add_argument(
        "--max-chars",
        type=int,
        default=0,
        help="Truncate content to this many characters (0 = no limit)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "md"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--images",
        choices=["urls", "download", "base64", "strip"],
        default="urls",
        help=(
            "How to handle images: 'urls' (default, keep signed S3 URLs), "
            "'download' (save to ./results/<page>/images/ and rewrite paths), "
            "'base64' (inline as data: URLs — bloats context, use sparingly), "
            "'strip' (replace with [image] placeholder)."
        ),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory when --images=download (default: results/<slug>_<timestamp>/)",
    )
    args = parser.parse_args()

    out_dir = args.out_dir
    if args.images == "download" and out_dir is None:
        page_id = extract_page_id(args.url)
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        out_dir = Path(__file__).parent / "results" / f"{page_id[:12]}_{ts}"
        out_dir.mkdir(parents=True, exist_ok=True)

    result = fetch_page(
        args.url,
        max_chars=args.max_chars,
        images_mode=args.images,
        out_dir=out_dir,
    )

    if "error" in result:
        print(json.dumps(result, indent=2), file=sys.stderr)
        sys.exit(1)

    # If we downloaded images, also drop the markdown next to them so paths resolve
    if args.images == "download" and out_dir is not None:
        md_path = out_dir / "page.md"
        md_path.write_text(f"# {result['title']}\n\n{result['content']}\n", encoding="utf-8")
        result["markdown_path"] = str(md_path)

    if args.format == "md":
        print(f"# {result['title']}\n")
        print(result["content"])
        if args.images == "download":
            print(
                f"\n<!-- {len(result.get('images', []))} image(s) downloaded to {out_dir} -->",
                file=sys.stderr,
            )
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
