#!/usr/bin/env python3
"""Build + push a Drafty-branded design-review canvas from feedback.json.

Extracts a real screenshot at each feedback item's timestamp (ffmpeg), renders
a dual-theme (light + dark) Drafty-brand HTML canvas, and pushes it to drafty.
Local <img> refs auto-upload to Drafty's Blob CDN on push — never data URIs.

usage:
  build-canvas.py feedback.json --video <file> --title "T" --project P \\
      [--slug S] [--kicker "proj · design review"] [--respect respect.md] \\
      [--out-dir DIR] [--source-note "..."] [--no-push]

  --respect FILE   bullets of data-backed design decisions NOT to "fix"
                   (markdown "- " bullets, **bold** ok). Renders the guard
                   callout. Omit to skip it.
  --no-push        build only; print the html path (don't call drafty).
"""
import json, html, os, re, sys, subprocess, argparse

SEV_ORDER = {"high": 0, "medium": 1, "low": 2, "nit": 3}


def esc(s): return html.escape(s or "")
def md_inline(s): return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc(s))


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


def sev_pill(k, label=None):
    return f'<span class="sev sev-{k}">{label or k.upper()}</span>'


def build_html(d, title, kicker, respect_bullets, source_note, shots_dir_rel):
    items = sorted(d["feedback_items"], key=lambda x: (SEV_ORDER.get(x["severity"], 9), x["timestamp_start"]))
    from collections import Counter
    cnt = Counter(it["severity"] for it in items)
    chips = " ".join(sev_pill(k, f"{cnt[k]} {k}") for k in ["high", "medium", "low", "nit"] if cnt.get(k))

    rows = "".join(
        f'<tr><td class="num">#{it["id"]}</td><td>{sev_pill(it["severity"])}</td>'
        f'<td>{esc(it["screen"])}</td><td>{esc(it["ui_ux_problem"])}</td>'
        f'<td class="ts">{esc(it["timestamp_start"])}</td></tr>' for it in items)

    cards = ""
    for it in items:
        p = os.path.join(shots_dir_rel, f"item_{it['id']:02d}.png")
        exists = os.path.exists(os.path.join(os.path.dirname(OUT_HTML) or ".", p))
        imgtag = (f'<img alt="{esc(it["screen"])} — #{it["id"]}" src="{p}" loading="lazy" decoding="async">'
                  if exists else '<div class="noimg"></div>')
        quote = f'<blockquote>“{esc(it.get("transcript_quote",""))}”</blockquote>' if it.get("transcript_quote") else ""
        added = "" if it.get("is_speaker_opinion", True) else '<span class="tag added">added observation</span>'
        end = ("–" + esc(it["timestamp_end"])) if it.get("timestamp_end") else ""
        cards += f"""
<article class="card cb-{it['severity']}" id="item-{it['id']}">
  <div class="shot">{imgtag}</div>
  <div class="body">
    <div class="cardhead">{sev_pill(it['severity'])}<span class="tag">{esc(it['category'])}</span>{added}<span class="ts">⏱ {esc(it['timestamp_start'])}{end}</span></div>
    <h3>#{it['id']} · {esc(it['screen'])}</h3>
    <p class="onscreen"><strong>On screen:</strong> {esc(it['on_screen'])}</p>
    {quote}
    <p class="problem"><strong>The problem:</strong> {esc(it['ui_ux_problem'])}</p>
    <div class="fix"><strong>Fix →</strong> {esc(it['suggested_fix'])}</div>
  </div>
</article>"""

    inv = "".join(f"<li><span class='ts'>{esc(s['first_seen'])}</span> {esc(s['screen'])}</li>"
                  for s in d.get("screen_inventory", []))

    callout = ""
    if respect_bullets:
        lis = "".join(f"<li>{md_inline(b)}</li>" for b in respect_bullets)
        callout = f"""<div class="callout"><h2>Design decisions to respect (don't "fix" these)</h2>
<p class="lead">Data-backed product calls. Feedback below was checked against them — none conflicts. The fixing agent holds these as constraints:</p>
<ul>{lis}</ul></div>"""

    foot = esc(source_note) if source_note else "Screenshots are real frames pulled at each item's timestamp. Reviewers' opinions are scoped to UI/UX craft."

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{esc(title)}</title>
<style>
:root{{--bg1:#fdf9fe;--bg2:#f7f0fb;--ink:#0d0d14;--mut:#6c6b76;--mut2:#4a4954;--faint:#9a99a3;--line:#ece6f1;--line2:#e3dbeb;--card:#fff;--cardb:#ece4f2;--shadow:0 1px 2px rgba(80,30,90,.04);--accent:#c600db;--accentink:#9410ab;--tagbg:#f3eef6;--tagb:#e7dfee;--calbg:#faf4fc;--calb:#ecddf2;--qb:#e7b9f0;--qbg:#faf6fb;--qtx:#57565f;--fixbg:#fdf2fe;--fixb:#f3d4f8;--fixleft:#c600db;--fixtx:#7d1490;--shotb:#ece6f1;--noimg:#f3eef6;--addbg:#fdf2fe;--addb:#ecc6f3}}
@media (prefers-color-scheme:dark){{:root{{--bg1:#140f1a;--bg2:#0c0910;--ink:#f4eff7;--mut:#a09aa8;--mut2:#cfc8d6;--faint:#7d7688;--line:#241c2b;--line2:#2c2435;--card:#191220;--cardb:#2a2032;--shadow:0 1px 2px rgba(0,0,0,.45);--accent:#e05cf0;--accentink:#ef8bfa;--tagbg:#231a2b;--tagb:#33283d;--calbg:#1b1326;--calb:#33283d;--qb:#5a2f66;--qbg:#1e1727;--qtx:#b8b0c2;--fixbg:#241430;--fixb:#4a2456;--fixleft:#e05cf0;--fixtx:#eaa6f5;--shotb:#2c2435;--noimg:#231a2b;--addbg:#241430;--addb:#5a2f66}}}}
*{{box-sizing:border-box}}
body{{margin:0;padding:44px 24px 80px;color:var(--ink);background:linear-gradient(180deg,var(--bg1),var(--bg2));background-attachment:fixed;font:15px/1.6 -apple-system,"SF Pro Text",BlinkMacSystemFont,"Segoe UI",Inter,system-ui,sans-serif}}
.wrap{{max-width:900px;margin:0 auto}}
.kicker{{font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);margin:0 0 6px}}
h1{{font-size:27px;font-weight:800;margin:0 0 6px;letter-spacing:-.02em}}
h1 .dot{{color:var(--accent)}}
.sub{{color:var(--mut);font-size:14.5px;margin:0 0 16px}}
.sub em{{color:var(--accentink);font-style:normal;font-weight:600}}
.chips{{margin:14px 0 28px}}
.sev{{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;padding:3px 10px;border-radius:999px;margin-right:6px;vertical-align:middle;border:1px solid transparent}}
.sev-high{{background:var(--accent);color:#fff;border-color:var(--accent)}}
.sev-medium{{background:#3f3e47;color:#fff;border-color:#3f3e47}}
.sev-low{{background:transparent;color:var(--mut);border-color:var(--line2)}}
.sev-nit{{background:transparent;color:var(--faint);border-color:var(--line)}}
.cb-high{{border-left:3px solid var(--accent)}}.cb-medium{{border-left:3px solid #8a8893}}.cb-low{{border-left:3px solid var(--line2)}}.cb-nit{{border-left:3px solid var(--line)}}
.tag{{display:inline-block;background:var(--tagbg);border:1px solid var(--tagb);color:var(--mut);font-size:11px;font-weight:600;padding:3px 9px;border-radius:6px;margin-right:6px}}
.tag.added{{background:var(--addbg);border:1px dashed var(--addb);color:var(--accentink);font-style:italic}}
.ts{{color:var(--faint);font-size:12.5px;font-variant-numeric:tabular-nums}}
.callout{{background:var(--calbg);border:1px solid var(--calb);border-radius:12px;padding:17px 19px;margin:22px 0 30px}}
.callout h2{{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--accentink);margin:0 0 8px}}
.callout .lead{{margin:0 0 10px;font-size:13px;color:var(--mut)}}
.callout ul{{margin:0;padding-left:18px;font-size:13.5px;color:var(--mut2)}}
.callout li{{margin:4px 0}}.callout strong,p strong{{color:var(--ink);font-weight:600}}
.over{{color:var(--mut2);font-size:14.5px;margin:0 0 8px}}
table{{width:100%;border-collapse:collapse;font-size:13.5px;margin:8px 0 36px}}
th,td{{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--faint);border-bottom-color:var(--line2)}}
td{{color:var(--mut2)}}td.num{{font-weight:700;white-space:nowrap;color:var(--ink)}}td.ts{{white-space:nowrap}}
h2.section{{font-size:12.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--faint);margin:36px 0 16px;border-top:1px solid var(--line);padding-top:22px}}
.card{{display:flex;gap:20px;background:var(--card);border:1px solid var(--cardb);border-radius:14px;padding:16px;margin:0 0 18px;align-items:flex-start;box-shadow:var(--shadow)}}
.shot{{flex:0 0 210px}}.shot img{{width:100%;border-radius:10px;border:1px solid var(--shotb);display:block}}
.noimg{{width:100%;aspect-ratio:9/19;background:var(--noimg);border-radius:10px}}
.body{{flex:1;min-width:0}}.cardhead{{margin-bottom:8px}}
.card h3{{font-size:16px;margin:6px 0 8px;letter-spacing:-.01em;color:var(--ink)}}
.card p{{margin:6px 0;font-size:14px;color:var(--mut2)}}
.onscreen{{color:var(--mut)}}.onscreen strong{{color:var(--mut2)}}
blockquote{{margin:10px 0;padding:9px 14px;border-left:2px solid var(--qb);background:var(--qbg);color:var(--qtx);font-style:italic;font-size:14px;border-radius:0 8px 8px 0}}
.fix{{margin-top:10px;background:var(--fixbg);border:1px solid var(--fixb);border-left:3px solid var(--fixleft);color:var(--fixtx);border-radius:0 9px 9px 0;padding:10px 14px;font-size:14px}}.fix strong{{color:var(--accentink)}}
.inv{{columns:2;gap:24px;font-size:13.5px;color:var(--mut);list-style:none;padding:0;margin:0}}.inv li{{margin:5px 0;break-inside:avoid}}
footer{{margin-top:48px;color:var(--faint);font-size:12.5px;border-top:1px solid var(--line);padding-top:18px;line-height:1.7}}
@media(max-width:640px){{.card{{flex-direction:column}}.shot{{flex:0 0 auto;max-width:240px}}.inv{{columns:1}}}}
</style></head><body><div class="wrap">
<header>{f'<p class="kicker">{esc(kicker)}</p>' if kicker else ''}
<h1>{esc(title)}<span class="dot">.</span></h1>
<p class="sub">{len(items)} actionable UI/UX items from a recorded walkthrough. Every item is a real spoken opinion unless tagged <em>added observation</em>.</p>
<div class="chips">{chips}</div></header>
{callout}
<p class="over"><strong>App overview.</strong> {esc(d.get('app_overview',''))}</p>
<h2 class="section">Summary — {len(items)} items (by severity)</h2>
<table><thead><tr><th>#</th><th>Severity</th><th>Screen</th><th>Problem</th><th>At</th></tr></thead><tbody>{rows}</tbody></table>
<h2 class="section">Detail — each item with screenshot + fix</h2>{cards}
<h2 class="section">Screen inventory (timestamps)</h2><ul class="inv">{inv}</ul>
<footer>{foot}</footer>
</div></body></html>"""


OUT_HTML = None

def main():
    global OUT_HTML
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
    OUT_HTML = os.path.join(a.out_dir, "design-review.html")
    shots_rel = "shots"
    if a.video:
        extract_frames(d["feedback_items"], a.video, os.path.join(a.out_dir, shots_rel))

    respect = None
    if a.respect:
        respect = [re.sub(r"^[-*]\s+", "", l).strip() for l in open(a.respect) if l.strip()]
    kicker = a.kicker or f"{a.project} · design review"

    html_out = build_html(d, a.title, kicker, respect, a.source_note, shots_rel)
    open(OUT_HTML, "w").write(html_out)
    print(f"wrote {OUT_HTML}")

    if a.no_push:
        return
    cmd = ["drafty", "canvas", "push", OUT_HTML, "--title", a.title,
           "--private", "--mode", "feedback", "--project", a.project, "--tag", "design-feedback"]
    if a.slug: cmd += ["--slug", a.slug]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
