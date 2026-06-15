---
name: comms-notion
description: Read the full content of a Notion page from a URL or page ID. Returns title, metadata, and the page body as markdown. Use when the user pastes a Notion link or asks to read, summarize, or extract content from a Notion page. Triggers on notion.so URLs, "read this notion page", "fetch from notion", "what's in this notion doc".
---

# Notion Page

Fetch a Notion page's title and body content as markdown via the Notion API.

## Setup

Requires a Notion internal integration token in `.env` (in CWD or in this skill's directory):

```
NOTION_TOKEN=ntn_...
```

The page must be **shared with the integration**: open the page in Notion → `Share` → `Connections` → add the integration. Without sharing, the API returns 404 even though the page exists.

Dependencies install on first run via `uv` (notion-client, python-dotenv).

## Commands

Run from this skill's base directory.

### Read a page (JSON output, default)

```bash
uv run python cli.py "https://www.notion.so/Magic-Tags-Product-spec-31a4cb32d18780bbafeaf1e0d7660594?source=copy_link"
```

### Read a page (markdown output)

```bash
uv run python cli.py "<url-or-id>" --format md
```

### Truncate large pages

```bash
uv run python cli.py "<url-or-id>" --max-chars 20000
```

Accepts: full URL, dashed page ID (`31a4cb32-d187-80bb-afea-f1e0d7660594`), or bare 32-char hex (`31a4cb32d18780bbafeaf1e0d7660594`).

### Image handling

By default the page's signed S3 image URLs are kept inline (each is several KB of query-string noise — bad for context). Pick a different mode:

```bash
# Download images to results/<page>/images/ and rewrite markdown to relative paths.
# Best mode for agent use: agent gets local paths, can `Read` any image on demand.
uv run python cli.py "<url-or-id>" --images download

# Inline images as data: URLs. Self-contained but bloats context massively
# (a 7-image page becomes ~600K tokens). Use only if you need a single artifact.
uv run python cli.py "<url-or-id>" --images base64

# Replace every image with `[image]` placeholder. Smallest output.
uv run python cli.py "<url-or-id>" --images strip

# Custom output directory for --images=download
uv run python cli.py "<url-or-id>" --images download --out-dir /tmp/magic-tags
```

When `--images=download`, output also includes `page.md` and `images/img_<hash>.<ext>` next to each other, so the markdown's relative paths resolve.

## JSON output shape

```json
{
  "url": "https://www.notion.so/...",
  "page_id": "31a4cb32d18780bbafeaf1e0d7660594",
  "title": "Magic Tags — Product spec",
  "created_time": "2026-...",
  "last_edited_time": "2026-...",
  "content": "## Heading\n\nBody as markdown...",
  "content_length": 4823,
  "truncated": false,
  "images_mode": "download",
  "output_dir": "results/31a4cb32d187_2026-04-28_150833",
  "markdown_path": "results/.../page.md",
  "images": [
    {"path": ".../img_aa209471db1f.png", "relative": "images/img_aa209471db1f.png", "size": 223152, "mime": "image/png", "source_url": "..."}
  ]
}
```

The `images` array and output paths only appear when `--images=download`.

## Block coverage

Headings (1–3), paragraphs, bulleted/numbered lists, to-dos, toggles, quotes, callouts, code (with language), dividers, bookmarks/embeds, images/video/files/pdfs, tables, equations, child pages, child databases. Nested children render with indentation. Unsupported block types emit `<!-- unsupported block: <type> -->` so nothing disappears silently.

## Troubleshooting

- **404 / "object_not_found"** — the integration isn't added to the page. Share → Connections → add it.
- **"NOTION_TOKEN not set"** — drop a `.env` next to `cli.py` or in the directory you're running from.
