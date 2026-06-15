#!/usr/bin/env python3
"""Build + push a Drafty-branded design-review canvas from feedback.json.

Extracts a real screenshot at each feedback item's timestamp (ffmpeg), renders
a dual-theme Drafty-brand HTML canvas (brand/look from drafty_theme), and pushes
it to drafty. Local <img> refs auto-upload to Drafty's Blob CDN on push — never
data URIs.

usage:
  build-canvas.py feedback.json --video <file> --title "T" --project P \\
      [--slug S] [--kicker "proj · design review"] [--respect respect.md] \\
      [--out-dir DIR] [--source-note "..."] [--no-push]

  --respect FILE   bullets of data-backed design decisions NOT to "fix"
                   (markdown "- " bullets, **bold** ok). Renders the guard
                   callout. Omit to skip it.
  --no-push        build only; print the html path (don't call drafty).
"""
import json, os, re, subprocess, argparse
import drafty_theme as T  # synced into this dir by scripts/build-marketplace.ts


def to_sec(ts):
    parts = [int(p) for p in re.findall(r"\d+", ts or "")]
    if not parts: return None
    if len(parts) == 3: return parts[0]*3600 + parts[1]*60 + parts[2]
    if len(parts) == 2: return parts[0]*60 + parts[1]
    return parts[0]


def extract_frames(items, video, shots_dir):
    os.makedirs(shots_dir, exist_ok=True)
    for it in items:
        sec = to_sec(it.get("timestamp_start"))
        if sec is None: continue
        out = os.path.join(shots_dir, f"item_{it['id']:02d}.png")
        subprocess.run(
            ["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", str(sec),
             "-i", video, "-frames:v", "1", "-vf", "scale=760:-1", "-y", out],
            check=False)


def feedback_card(it, shots_rel, out_dir):
    p = os.path.join(shots_rel, f"item_{it['id']:02d}.png")
    exists = os.path.exists(os.path.join(out_dir, p))
    img = (f'<img alt="{T.esc(it["screen"])} — #{it["id"]}" src="{p}" loading="lazy" decoding="async">'
           if exists else '<div class="noimg"></div>')
    quote = f'<blockquote>“{T.esc(it.get("transcript_quote",""))}”</blockquote>' if it.get("transcript_quote") else ""
    added = "" if it.get("is_speaker_opinion", True) else '<span class="tag added">added observation</span>'
    end = ("–" + T.esc(it["timestamp_end"])) if it.get("timestamp_end") else ""
    return f"""
<article class="card cb-{it['severity']}" id="item-{it['id']}">
  <div class="shot">{img}</div>
  <div class="body">
    <div class="cardhead">{T.sev_pill(it['severity'])}<span class="tag">{T.esc(it['category'])}</span>{added}<span class="ts">⏱ {T.esc(it['timestamp_start'])}{end}</span></div>
    <h3>#{it['id']} · {T.esc(it['screen'])}</h3>
    <p class="onscreen"><strong>On screen:</strong> {T.esc(it['on_screen'])}</p>
    {quote}
    <p class="problem"><strong>The problem:</strong> {T.esc(it['ui_ux_problem'])}</p>
    <div class="fix"><strong>Fix →</strong> {T.esc(it['suggested_fix'])}</div>
  </div>
</article>"""


def build_html(d, title, kicker, respect_bullets, source_note, shots_rel, out_dir):
    from collections import Counter
    items = sorted(d["feedback_items"], key=lambda x: (T.SEV_ORDER.get(x["severity"], 9), x["timestamp_start"]))
    counts = Counter(it["severity"] for it in items)

    rows = "".join(
        f'<tr><td class="num">#{it["id"]}</td><td>{T.sev_pill(it["severity"])}</td>'
        f'<td>{T.esc(it["screen"])}</td><td>{T.esc(it["ui_ux_problem"])}</td>'
        f'<td class="ts">{T.esc(it["timestamp_start"])}</td></tr>' for it in items)

    cards = "".join(feedback_card(it, shots_rel, out_dir) for it in items)
    inv = "".join(f"<li><span class='ts'>{T.esc(s['first_seen'])}</span> {T.esc(s['screen'])}</li>"
                  for s in d.get("screen_inventory", []))

    body = T.severity_chips(counts)
    if respect_bullets:
        body += T.callout("Design decisions to respect (don't \"fix\" these)",
                          "Data-backed product calls. Feedback below was checked against them — none conflicts. The fixing agent holds these as constraints:",
                          respect_bullets)
    body += f'<p class="over"><strong>App overview.</strong> {T.esc(d.get("app_overview",""))}</p>'
    body += T.section(f"Summary — {len(items)} items (by severity)")
    body += (f'<table><thead><tr><th>#</th><th>Severity</th><th>Screen</th><th>Problem</th><th>At</th></tr></thead>'
             f'<tbody>{rows}</tbody></table>')
    body += T.section("Detail — each item with screenshot + fix") + cards
    body += T.section("Screen inventory (timestamps)") + f'<ul class="inv">{inv}</ul>'
    foot = T.esc(source_note) if source_note else "Screenshots are real frames pulled at each item's timestamp. Reviewers' opinions are scoped to UI/UX craft."
    body += f"<footer>{foot}</footer>"

    sub = (f'{len(items)} actionable UI/UX items from a recorded walkthrough. '
           f'Every item is a real spoken opinion unless tagged <em>added observation</em>.')
    return T.page(title, body, kicker=kicker, sub=sub)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("feedback")
    ap.add_argument("--video")
    ap.add_argument("--title", default="Design feedback walkthrough")
    ap.add_argument("--project", required=True)
    ap.add_argument("--slug")
    ap.add_argument("--kicker")
    ap.add_argument("--respect")
    ap.add_argument("--source-note")
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()

    d = json.load(open(a.feedback))
    os.makedirs(a.out_dir, exist_ok=True)
    out_html = os.path.join(a.out_dir, "design-review.html")
    shots_rel = "shots"
    if a.video:
        extract_frames(d["feedback_items"], a.video, os.path.join(a.out_dir, shots_rel))

    respect = None
    if a.respect:
        respect = [re.sub(r"^[-*]\s+", "", l).strip() for l in open(a.respect) if l.strip()]
    kicker = a.kicker or f"{a.project} · design review"

    open(out_html, "w").write(build_html(d, a.title, kicker, respect, a.source_note, shots_rel, a.out_dir))
    print(f"wrote {out_html}")

    if a.no_push:
        return
    cmd = ["drafty", "canvas", "push", out_html, "--title", a.title,
           "--private", "--mode", "feedback", "--project", a.project, "--tag", "design-feedback"]
    if a.slug: cmd += ["--slug", a.slug]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
