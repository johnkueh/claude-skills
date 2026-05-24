#!/usr/bin/env python3
"""GPT Image 2 generation CLI with cost logging.

Calls OpenAI's /v1/images/generations and /v1/images/edits with model=gpt-image-2.
Estimates cost pre-flight, logs actual usage post-flight.

Pricing (per 1M tokens):
  Text input:    $5.00   (cached $1.25)
  Image input:   $8.00   (cached $2.00)
  Image output:  $30.00
"""

import base64
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click
import requests

API_BASE = "https://api.openai.com/v1"
MODEL = "gpt-image-2"
LOG_PATH = Path.home() / ".config" / "image-gen" / "usage.jsonl"
CONFIG_ENV = Path.home() / ".config" / "image-gen" / "env"

# gpt-image-2 dropped support for `background: "transparent"` — its
# `background` enum is now {auto, opaque} only. Model was trained for
# scene-consistency, not isolated cut-outs. Workaround used by --transparent
# below: prompt the model to paint on solid magenta #FF00FF, then chroma-key
# it out in post-process. Standard trick for sticker / cut-out assets.
MAGENTA_BG_BLOCK = (
    "\n\nCRITICAL — background: solid uniform pure magenta #FF00FF "
    "(rgb 255, 0, 255), edge-to-edge, completely flat with no gradient, no "
    "texture, no atmosphere — every pixel outside the painted subject and "
    "its shadow must be exact pure magenta. This is critical: the magenta "
    "will be chroma-keyed out in post-processing to produce a transparent "
    "PNG, so it must be a perfectly clean color block. No magenta or "
    "pink-purple anywhere in the subject itself."
)

PRICE = {
    "text_in": 5.00 / 1_000_000,
    "text_in_cached": 1.25 / 1_000_000,
    "image_in": 8.00 / 1_000_000,
    "image_in_cached": 2.00 / 1_000_000,
    "image_out": 30.00 / 1_000_000,
}

# Output image token counts by (size, quality). Based on the published gpt-image-1
# table; gpt-image-2 charges the same shape per-(size,quality). The API returns the
# real count in `usage.output_tokens`, so this is only used for pre-flight estimates.
OUTPUT_TOKEN_TABLE = {
    ("1024x1024", "low"): 272,
    ("1024x1024", "medium"): 1056,
    ("1024x1024", "high"): 4160,
    ("1024x1536", "low"): 408,
    ("1024x1536", "medium"): 1584,
    ("1024x1536", "high"): 6240,
    ("1536x1024", "low"): 400,
    ("1536x1024", "medium"): 1568,
    ("1536x1024", "high"): 6208,
}

SIZES = ["auto", "1024x1024", "1024x1536", "1536x1024"]
QUALITIES = ["low", "medium", "high", "auto"]
FORMATS = ["png", "jpeg", "webp"]
BACKGROUNDS = ["auto", "transparent", "opaque"]


def load_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key and CONFIG_ENV.exists():
        for line in CONFIG_ENV.read_text().splitlines():
            line = line.strip()
            if line.startswith("export OPENAI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
            if line.startswith("OPENAI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if not key:
        click.echo(
            "Error: OPENAI_API_KEY not set. Put it in ~/.config/image-gen/env "
            "as `export OPENAI_API_KEY=sk-...` or export it in your shell.",
            err=True,
        )
        sys.exit(2)
    return key


def count_text_tokens(text: str) -> int:
    try:
        import tiktoken
        enc = tiktoken.get_encoding("o200k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def estimate_image_input_tokens(ref_path: Path) -> int:
    """Rough estimate based on file size. Real value comes back in usage."""
    try:
        kb = ref_path.stat().st_size / 1024
    except Exception:
        return 1500
    # Empirical-ish: ~1000 tok for a tiny png, ~2500 for a typical 1-2MB photo.
    return int(min(4000, max(500, 800 + kb * 1.5)))


def estimate_cost(
    prompt: str,
    size: str,
    quality: str,
    n: int = 1,
    refs: list[Path] | None = None,
) -> dict:
    text_tok = count_text_tokens(prompt)
    img_in_tok = sum(estimate_image_input_tokens(p) for p in (refs or []))
    # If size or quality is "auto", assume worst case for the estimate.
    eff_size = size if size != "auto" else "1024x1536"
    eff_quality = quality if quality != "auto" else "high"
    per_img_out = OUTPUT_TOKEN_TABLE.get((eff_size, eff_quality), 4160)
    out_tok = per_img_out * n

    cost_text = text_tok * PRICE["text_in"]
    cost_img_in = img_in_tok * PRICE["image_in"]
    cost_img_out = out_tok * PRICE["image_out"]
    total = cost_text + cost_img_in + cost_img_out

    return {
        "text_in_tokens": text_tok,
        "image_in_tokens_est": img_in_tok,
        "output_tokens_est": out_tok,
        "cost_text_in": cost_text,
        "cost_image_in": cost_img_in,
        "cost_image_out": cost_img_out,
        "total_cost_est": total,
        "assumed_size": eff_size,
        "assumed_quality": eff_quality,
    }


def compute_actual_cost(usage: dict) -> dict:
    """Compute $ from a usage block returned by the API."""
    details = usage.get("input_tokens_details") or {}
    text_in = details.get("text_tokens", 0)
    img_in = details.get("image_tokens", 0)
    cached_in = details.get("cached_tokens", 0)
    # If breakdown missing, fall back to lumped input.
    if not text_in and not img_in and usage.get("input_tokens"):
        text_in = usage["input_tokens"]
    out = usage.get("output_tokens", 0)

    # Cached tokens displace text input pricing (image cached pricing also exists,
    # but the API doesn't currently split cached_in between text/image — treat as text).
    text_in_billable = max(0, text_in - cached_in)
    cost = (
        text_in_billable * PRICE["text_in"]
        + cached_in * PRICE["text_in_cached"]
        + img_in * PRICE["image_in"]
        + out * PRICE["image_out"]
    )
    return {
        "text_in_tokens": text_in,
        "image_in_tokens": img_in,
        "cached_in_tokens": cached_in,
        "output_tokens": out,
        "total_tokens": usage.get("total_tokens", text_in + img_in + out),
        "cost_usd": round(cost, 6),
        "breakdown": {
            "text_in": round(text_in_billable * PRICE["text_in"], 6),
            "cached_in": round(cached_in * PRICE["text_in_cached"], 6),
            "image_in": round(img_in * PRICE["image_in"], 6),
            "image_out": round(out * PRICE["image_out"], 6),
        },
    }


def log_usage(record: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(record) + "\n")


def slugify(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return s[:max_len] or "image"


def default_out_path(prompt: str, fmt: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path.cwd() / f"{ts}-{slugify(prompt)}.{fmt}"


def open_file(path: Path) -> None:
    try:
        subprocess.run(["open", str(path)], check=False)
    except Exception:
        pass


def format_cost(c: float) -> str:
    if c < 0.01:
        return f"${c:.4f}"
    return f"${c:.3f}"


def print_estimate(est: dict, n: int, mode: str) -> None:
    click.echo(
        f"  est: {format_cost(est['total_cost_est'])}  "
        f"(text_in≈{est['text_in_tokens']} tok"
        + (
            f", img_in≈{est['image_in_tokens_est']} tok"
            if est["image_in_tokens_est"]
            else ""
        )
        + f", out≈{est['output_tokens_est']} tok"
        + (f" × {n}" if n > 1 else "")
        + f", quality={est['assumed_quality']}, size={est['assumed_size']})",
        err=True,
    )


def chroma_key_file(
    in_path: Path,
    out_path: Path,
    key_rgb: tuple[int, int, int] = (255, 0, 255),
    tol_per_channel: int = 70,
) -> tuple[int, int]:
    """Strip a uniform background color from a PNG, producing a transparent PNG.

    For each pixel, if its squared-RGB distance from key_rgb is below
    3 * tol_per_channel², set alpha to 0. The hand-painted subject (which
    sits well outside the chroma key band) and its watercolor shadow survive.

    Returns (cleared_count, total_count). Lazy imports Pillow + numpy so
    importing this module stays cheap for users who don't chroma-key.
    """
    from PIL import Image
    import numpy as np

    img = Image.open(in_path).convert("RGBA")
    arr = np.array(img)
    r = arr[..., 0].astype(np.int32)
    g = arr[..., 1].astype(np.int32)
    b = arr[..., 2].astype(np.int32)
    kr, kg, kb = key_rgb
    dist_sq = (r - kr) ** 2 + (g - kg) ** 2 + (b - kb) ** 2
    mask = dist_sq < 3 * (tol_per_channel ** 2)
    arr[..., 3][mask] = 0
    Image.fromarray(arr).save(out_path)
    return int(mask.sum()), int(arr.shape[0] * arr.shape[1])


def parse_hex_color(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.lstrip("#").upper()
    if len(h) != 6 or not all(c in "0123456789ABCDEF" for c in h):
        raise click.BadParameter(f"Expected 6-digit hex (e.g. FF00FF), got: {hex_str}")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


@click.group()
def cli():
    """GPT Image 2 CLI — generate, edit, and track cost."""


@cli.command()
@click.option("--prompt", "-p", required=True, help="Final, cookbook-shaped prompt.")
@click.option("--size", default="auto", type=click.Choice(SIZES))
@click.option("--quality", default="high", type=click.Choice(QUALITIES))
@click.option("--format", "fmt", default="png", type=click.Choice(FORMATS))
@click.option("--background", default="auto", type=click.Choice(BACKGROUNDS))
@click.option("--n", default=1, type=int, help="Images to generate (1-10).")
@click.option("--out", "-o", default=None, help="Output path (default: cwd/<ts>-<slug>.<fmt>).")
@click.option("--compression", default=None, type=int, help="0-100, jpeg/webp only.")
@click.option(
    "--transparent",
    "-t",
    is_flag=True,
    help=(
        "Produce a transparent PNG via the magenta-bg + chroma-key workaround. "
        "gpt-image-2 dropped native transparent support; this auto-appends a "
        "magenta-bg instruction block to the prompt and post-processes the "
        "output to alpha out the magenta. Forces --format=png and --background=opaque."
    ),
)
@click.option("--dry-run", is_flag=True, help="Print estimate and exit.")
@click.option("--no-open", is_flag=True, help="Don't auto-open result in Preview.")
def generate(prompt, size, quality, fmt, background, n, out, compression, transparent, dry_run, no_open):
    """Text → image via /v1/images/generations."""
    if transparent:
        # Force PNG + opaque (gpt-image-2 rejects 'transparent' on the API),
        # then chroma-key after save. Append the magenta-bg instruction so
        # the model paints a clean key color.
        fmt = "png"
        background = "opaque"
        prompt = prompt + MAGENTA_BG_BLOCK
    est = estimate_cost(prompt, size, quality, n=n)
    click.echo(f"Prompt ({len(prompt)} chars):", err=True)
    click.echo(prompt, err=True)
    click.echo("", err=True)
    print_estimate(est, n, "generate")

    if dry_run:
        click.echo(json.dumps({"dry_run": True, "estimate": est}, indent=2))
        return

    body = {
        "model": MODEL,
        "prompt": prompt,
        "n": n,
        "size": size,
        "quality": quality,
        "output_format": fmt,
        "background": background,
    }
    if compression is not None and fmt in ("jpeg", "webp"):
        body["output_compression"] = compression

    t0 = time.time()
    resp = requests.post(
        f"{API_BASE}/images/generations",
        headers={
            "Authorization": f"Bearer {load_api_key()}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=300,
    )
    elapsed = time.time() - t0

    if resp.status_code != 200:
        click.echo(f"API error {resp.status_code}: {resp.text}", err=True)
        sys.exit(1)

    data = resp.json()
    usage = data.get("usage") or {}
    actual = compute_actual_cost(usage)

    saved = []
    for i, img in enumerate(data.get("data", [])):
        b64 = img.get("b64_json")
        if not b64:
            continue
        target = (
            Path(out)
            if out and n == 1
            else default_out_path(prompt, fmt) if not out
            else Path(out).with_stem(f"{Path(out).stem}-{i+1}")
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(b64))

        # --transparent: chroma-key the magenta we asked the model for, in place.
        if transparent:
            cleared, total = chroma_key_file(target, target)
            pct = 100 * cleared / total
            click.echo(
                f"  chroma-key: α=0 on {cleared}/{total} px ({pct:.1f}%)  → {target}",
                err=True,
            )

        saved.append(str(target))

    record = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "mode": "generate",
        "model": MODEL,
        "size": data.get("size", size),
        "quality": data.get("quality", quality),
        "format": data.get("output_format", fmt),
        "background": data.get("background", background),
        "n": n,
        "elapsed_s": round(elapsed, 2),
        "prompt_preview": prompt[:200],
        "out_files": saved,
        **actual,
    }
    log_usage(record)

    click.echo(f"  actual: {format_cost(actual['cost_usd'])} "
               f"({actual['output_tokens']} out tok, {elapsed:.1f}s)", err=True)
    for s in saved:
        click.echo(s)
    if saved and not no_open:
        open_file(Path(saved[0]))


@cli.command()
@click.option("--prompt", "-p", required=True, help="Edit instruction (cookbook-shaped).")
@click.option("--ref", "refs", multiple=True, required=True, type=click.Path(exists=True),
              help="Reference image(s). Repeat for multi-image input.")
@click.option("--mask", default=None, type=click.Path(exists=True),
              help="Optional mask PNG (transparent = editable area).")
@click.option("--size", default="auto", type=click.Choice(SIZES))
@click.option("--quality", default="high", type=click.Choice(QUALITIES))
@click.option("--format", "fmt", default="png", type=click.Choice(FORMATS))
@click.option("--background", default="auto", type=click.Choice(BACKGROUNDS))
@click.option("--n", default=1, type=int)
@click.option("--out", "-o", default=None)
@click.option("--dry-run", is_flag=True)
@click.option("--no-open", is_flag=True)
def edit(prompt, refs, mask, size, quality, fmt, background, n, out, dry_run, no_open):
    """Image(s) + prompt → image via /v1/images/edits. Supports moodboards / style refs."""
    ref_paths = [Path(r) for r in refs]
    est = estimate_cost(prompt, size, quality, n=n, refs=ref_paths)
    click.echo(f"Prompt ({len(prompt)} chars), refs: {[p.name for p in ref_paths]}", err=True)
    click.echo(prompt, err=True)
    click.echo("", err=True)
    print_estimate(est, n, "edit")

    if dry_run:
        click.echo(json.dumps({"dry_run": True, "estimate": est}, indent=2))
        return

    files = []
    # Multipart: send each ref as image[] (multiple) or image (single).
    if len(ref_paths) == 1:
        files.append(("image", (ref_paths[0].name, ref_paths[0].read_bytes(), "image/png")))
    else:
        for p in ref_paths:
            files.append(("image[]", (p.name, p.read_bytes(), "image/png")))
    if mask:
        m = Path(mask)
        files.append(("mask", (m.name, m.read_bytes(), "image/png")))

    form = {
        "model": MODEL,
        "prompt": prompt,
        "n": str(n),
        "size": size,
        "quality": quality,
        "output_format": fmt,
        "background": background,
    }

    t0 = time.time()
    resp = requests.post(
        f"{API_BASE}/images/edits",
        headers={"Authorization": f"Bearer {load_api_key()}"},
        data=form,
        files=files,
        timeout=300,
    )
    elapsed = time.time() - t0

    if resp.status_code != 200:
        click.echo(f"API error {resp.status_code}: {resp.text}", err=True)
        sys.exit(1)

    data = resp.json()
    usage = data.get("usage") or {}
    actual = compute_actual_cost(usage)

    saved = []
    for i, img in enumerate(data.get("data", [])):
        b64 = img.get("b64_json")
        if not b64:
            continue
        target = (
            Path(out) if out and n == 1
            else default_out_path(prompt, fmt) if not out
            else Path(out).with_stem(f"{Path(out).stem}-{i+1}")
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(b64))
        saved.append(str(target))

    record = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "mode": "edit",
        "model": MODEL,
        "size": data.get("size", size),
        "quality": data.get("quality", quality),
        "format": data.get("output_format", fmt),
        "background": data.get("background", background),
        "n": n,
        "refs": [str(p) for p in ref_paths],
        "elapsed_s": round(elapsed, 2),
        "prompt_preview": prompt[:200],
        "out_files": saved,
        **actual,
    }
    log_usage(record)

    click.echo(f"  actual: {format_cost(actual['cost_usd'])} "
               f"({actual['output_tokens']} out tok, {elapsed:.1f}s)", err=True)
    for s in saved:
        click.echo(s)
    if saved and not no_open:
        open_file(Path(saved[0]))


@cli.command()
@click.option("--tail", default=0, type=int, help="Show last N calls.")
@click.option("--days", default=0, type=int, help="Restrict summary to last N days.")
def cost(tail, days):
    """Summarize usage.jsonl: total spend, per-day, per-mode."""
    if not LOG_PATH.exists():
        click.echo("No usage log yet.")
        return
    records = [json.loads(line) for line in LOG_PATH.read_text().splitlines() if line.strip()]

    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        records = [r for r in records if datetime.fromisoformat(r["ts"].replace("Z", "+00:00")) >= cutoff]

    if tail:
        for r in records[-tail:]:
            click.echo(
                f"{r['ts']}  {r['mode']:8} {r.get('size','?'):>9} {r.get('quality','?'):>6}  "
                f"{format_cost(r.get('cost_usd', 0)):>8}  {r.get('prompt_preview','')[:60]}"
            )
        return

    by_day: dict[str, float] = {}
    by_mode: dict[str, float] = {}
    total = 0.0
    for r in records:
        day = r["ts"][:10]
        c = r.get("cost_usd", 0)
        by_day[day] = by_day.get(day, 0) + c
        by_mode[r["mode"]] = by_mode.get(r["mode"], 0) + c
        total += c

    click.echo(f"Total spend ({len(records)} calls): {format_cost(total)}")
    click.echo("\nBy mode:")
    for m, c in sorted(by_mode.items(), key=lambda x: -x[1]):
        click.echo(f"  {m:8}  {format_cost(c)}")
    click.echo("\nBy day:")
    for d, c in sorted(by_day.items())[-14:]:
        click.echo(f"  {d}  {format_cost(c)}")


@cli.command(name="chroma-key")
@click.argument("input", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--output",
    "-o",
    default=None,
    type=click.Path(path_type=Path),
    help="Output path. Default: <input-stem>-transparent.png in the same dir.",
)
@click.option(
    "--key-color",
    default="FF00FF",
    help="Hex of the background color to strip. Default FF00FF (magenta).",
)
@click.option(
    "--tolerance",
    default=70,
    type=int,
    help="Per-channel tolerance, 0-255 (default 70 → squared total 14700).",
)
def chroma_key(input: Path, output: Path | None, key_color: str, tolerance: int):
    """Strip a uniform background color from a PNG → transparent PNG.

    Use after `generate` on a solid magenta background to get transparent
    output. The model paints; this strips. Prefer `generate --transparent`
    which does both in one step.
    """
    if output is None:
        output = input.with_stem(f"{input.stem}-transparent")
    key_rgb = parse_hex_color(key_color)
    cleared, total = chroma_key_file(input, output, key_rgb, tolerance)
    pct = 100 * cleared / total
    click.echo(f"  α=0 on {cleared}/{total} px ({pct:.1f}%)  → {output}")


if __name__ == "__main__":
    cli()
