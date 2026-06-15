"""Drafty canvas brand theme — one source of truth for the house look.

A self-contained design system for drafty canvases: dual-theme (light + dark)
brand tokens, component CSS (cards, callouts, severity pills, tables, quotes,
fix boxes), and small render primitives. Any canvas-building skill imports this
so every branded canvas shares the same look and updates in one place.

Brand: magenta accent (#c600db light / #e05cf0 dark) on lavender/deep-purple,
reserved 60-30-10 for the things that matter (primary status + actions); real
prefers-color-scheme dual palette, never a single color-scheme (that kills the
other theme). Keep canvases self-contained — inline this CSS, no external refs.

Render with page(title, body, kicker=…, sub=…). Compose `body` from the
primitives here (section/callout/sev_pill/chips) plus your own semantic markup
using the component classes below (.card/.shot/.fix/blockquote/.tag/table).
"""
import html as _html
import re as _re

SEV_ORDER = {"high": 0, "medium": 1, "low": 2, "nit": 3}


def esc(s):
    return _html.escape(s or "")


def md_inline(s):
    """Minimal markdown for short bullets: **bold** -> <strong>."""
    return _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc(s))


# ── the brand stylesheet (tokens + every component class) ────────────────────
THEME_CSS = """
:root{--bg1:#fdf9fe;--bg2:#f7f0fb;--ink:#0d0d14;--mut:#6c6b76;--mut2:#4a4954;--faint:#9a99a3;--line:#ece6f1;--line2:#e3dbeb;--card:#fff;--cardb:#ece4f2;--shadow:0 1px 2px rgba(80,30,90,.04);--accent:#c600db;--accentink:#9410ab;--tagbg:#f3eef6;--tagb:#e7dfee;--calbg:#faf4fc;--calb:#ecddf2;--qb:#e7b9f0;--qbg:#faf6fb;--qtx:#57565f;--fixbg:#fdf2fe;--fixb:#f3d4f8;--fixleft:#c600db;--fixtx:#7d1490;--shotb:#ece6f1;--noimg:#f3eef6;--addbg:#fdf2fe;--addb:#ecc6f3}
@media (prefers-color-scheme:dark){:root{--bg1:#140f1a;--bg2:#0c0910;--ink:#f4eff7;--mut:#a09aa8;--mut2:#cfc8d6;--faint:#7d7688;--line:#241c2b;--line2:#2c2435;--card:#191220;--cardb:#2a2032;--shadow:0 1px 2px rgba(0,0,0,.45);--accent:#e05cf0;--accentink:#ef8bfa;--tagbg:#231a2b;--tagb:#33283d;--calbg:#1b1326;--calb:#33283d;--qb:#5a2f66;--qbg:#1e1727;--qtx:#b8b0c2;--fixbg:#241430;--fixb:#4a2456;--fixleft:#e05cf0;--fixtx:#eaa6f5;--shotb:#2c2435;--noimg:#231a2b;--addbg:#241430;--addb:#5a2f66}}
*{box-sizing:border-box}
body{margin:0;padding:44px 24px 80px;color:var(--ink);background:linear-gradient(180deg,var(--bg1),var(--bg2));background-attachment:fixed;font:15px/1.6 -apple-system,"SF Pro Text",BlinkMacSystemFont,"Segoe UI",Inter,system-ui,sans-serif}
.wrap{max-width:900px;margin:0 auto}
.kicker{font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);margin:0 0 6px}
h1{font-size:27px;font-weight:800;margin:0 0 6px;letter-spacing:-.02em}
h1 .dot{color:var(--accent)}
.sub{color:var(--mut);font-size:14.5px;margin:0 0 16px}
.sub em{color:var(--accentink);font-style:normal;font-weight:600}
.chips{margin:14px 0 28px}
.sev{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;padding:3px 10px;border-radius:999px;margin-right:6px;vertical-align:middle;border:1px solid transparent}
.sev-high{background:var(--accent);color:#fff;border-color:var(--accent)}
.sev-medium{background:#3f3e47;color:#fff;border-color:#3f3e47}
.sev-low{background:transparent;color:var(--mut);border-color:var(--line2)}
.sev-nit{background:transparent;color:var(--faint);border-color:var(--line)}
.cb-high{border-left:3px solid var(--accent)}.cb-medium{border-left:3px solid #8a8893}.cb-low{border-left:3px solid var(--line2)}.cb-nit{border-left:3px solid var(--line)}
.tag{display:inline-block;background:var(--tagbg);border:1px solid var(--tagb);color:var(--mut);font-size:11px;font-weight:600;padding:3px 9px;border-radius:6px;margin-right:6px}
.tag.added{background:var(--addbg);border:1px dashed var(--addb);color:var(--accentink);font-style:italic}
.ts{color:var(--faint);font-size:12.5px;font-variant-numeric:tabular-nums}
.callout{background:var(--calbg);border:1px solid var(--calb);border-radius:12px;padding:17px 19px;margin:22px 0 30px}
.callout h2{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--accentink);margin:0 0 8px}
.callout .lead{margin:0 0 10px;font-size:13px;color:var(--mut)}
.callout ul{margin:0;padding-left:18px;font-size:13.5px;color:var(--mut2)}
.callout li{margin:4px 0}.callout strong,p strong{color:var(--ink);font-weight:600}
.over{color:var(--mut2);font-size:14.5px;margin:0 0 8px}
table{width:100%;border-collapse:collapse;font-size:13.5px;margin:8px 0 36px}
th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--faint);border-bottom-color:var(--line2)}
td{color:var(--mut2)}td.num{font-weight:700;white-space:nowrap;color:var(--ink)}td.ts{white-space:nowrap}
h2.section{font-size:12.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--faint);margin:36px 0 16px;border-top:1px solid var(--line);padding-top:22px}
.card{display:flex;gap:20px;background:var(--card);border:1px solid var(--cardb);border-radius:14px;padding:16px;margin:0 0 18px;align-items:flex-start;box-shadow:var(--shadow)}
.shot{flex:0 0 210px}.shot img{width:100%;border-radius:10px;border:1px solid var(--shotb);display:block}
.noimg{width:100%;aspect-ratio:9/19;background:var(--noimg);border-radius:10px}
.body{flex:1;min-width:0}.cardhead{margin-bottom:8px}
.card h3{font-size:16px;margin:6px 0 8px;letter-spacing:-.01em;color:var(--ink)}
.card p{margin:6px 0;font-size:14px;color:var(--mut2)}
.onscreen{color:var(--mut)}.onscreen strong{color:var(--mut2)}
blockquote{margin:10px 0;padding:9px 14px;border-left:2px solid var(--qb);background:var(--qbg);color:var(--qtx);font-style:italic;font-size:14px;border-radius:0 8px 8px 0}
.fix{margin-top:10px;background:var(--fixbg);border:1px solid var(--fixb);border-left:3px solid var(--fixleft);color:var(--fixtx);border-radius:0 9px 9px 0;padding:10px 14px;font-size:14px}.fix strong{color:var(--accentink)}
.inv{columns:2;gap:24px;font-size:13.5px;color:var(--mut);list-style:none;padding:0;margin:0}.inv li{margin:5px 0;break-inside:avoid}
footer{margin-top:48px;color:var(--faint);font-size:12.5px;border-top:1px solid var(--line);padding-top:18px;line-height:1.7}
@media(max-width:640px){.card{flex-direction:column}.shot{flex:0 0 auto;max-width:240px}.inv{columns:1}}
""".strip()


# ── render primitives ────────────────────────────────────────────────────────
def page(title, body, *, kicker=None, sub=None, color_scheme="light dark"):
    """Wrap composed body HTML in a full self-contained branded document."""
    head = ""
    if kicker:
        head += f'<p class="kicker">{esc(kicker)}</p>'
    head += f'<h1>{esc(title)}<span class="dot">.</span></h1>'
    if sub:
        head += f'<p class="sub">{sub}</p>'  # sub may contain <em> markup — caller-escaped
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta name="color-scheme" content="{color_scheme}">'
        f'<title>{esc(title)}</title>'
        f'<style>{THEME_CSS}</style></head><body><div class="wrap">'
        f'<header>{head}</header>{body}</div></body></html>'
    )


def sev_pill(level, label=None):
    return f'<span class="sev sev-{level}">{label or level.upper()}</span>'


def severity_chips(counts):
    """counts: dict level->n. Renders the top-of-page severity summary chips."""
    return ('<div class="chips">'
            + " ".join(sev_pill(k, f"{counts[k]} {k}")
                       for k in ["high", "medium", "low", "nit"] if counts.get(k))
            + "</div>")


def section(title):
    return f'<h2 class="section">{esc(title)}</h2>'


def callout(title, lead, bullets):
    """A guard/constraints box. bullets: list of markdown-ish strings."""
    lis = "".join(f"<li>{md_inline(b)}</li>" for b in bullets)
    return (f'<div class="callout"><h2>{esc(title)}</h2>'
            f'<p class="lead">{esc(lead)}</p><ul>{lis}</ul></div>')
