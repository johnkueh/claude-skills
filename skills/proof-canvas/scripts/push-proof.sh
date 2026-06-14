#!/bin/bash
# Build + push a proof canvas: screenshots with captions (and an optional
# story) on a private drafty canvas, so John can eye the result from any
# device and annotate directly on the images.
#
# usage:
#   push-proof.sh --title "Proof: <feature>" [--meta "branch X · commit Y"] \
#                 [--story story.md] [--slug existing-slug] \
#                 img1.png "caption 1" [img2.png "caption 2" ...]
#
# - Images are embedded as data URIs (no asset hosting needed). Keep each
#   screenshot under ~500KB; total canvas under ~5MB.
# - --story: a file of HTML/plain paragraphs inserted between the meta line
#   and the figures (the narrative: what changed, what to look at, bugs found).
# - --slug: re-push onto an existing proof canvas (iteration → version history)
#   instead of minting a new one.
set -euo pipefail

TITLE="" META="" STORY="" SLUG="" PROJECT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --title)   TITLE="$2";   shift 2 ;;
    --meta)    META="$2";    shift 2 ;;
    --story)   STORY="$2";   shift 2 ;;
    --slug)    SLUG="$2";    shift 2 ;;
    --project) PROJECT="$2"; shift 2 ;;
    *) break ;;
  esac
done
[[ -n "$TITLE" && $# -ge 2 ]] || { echo "usage: push-proof.sh --title T --project P [--meta M] [--story F] [--slug S] img caption [img caption ...]" >&2; exit 1; }
[[ -n "$PROJECT" ]] || { echo "--project is required (the repo/project this proof belongs to, e.g. drafty, clove)" >&2; exit 1; }
[[ $(( $# % 2 )) -eq 0 ]] || { echo "images and captions must come in pairs" >&2; exit 1; }

OUT="$(mktemp -d)/proof.html"
esc() { sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' <<<"$1"; }

{
cat <<HEAD
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$(esc "$TITLE")</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; padding: 40px 24px 64px; background: #0a0a0a; color: #fafafa; font: 15px/1.6 -apple-system, "SF Pro Text", system-ui, sans-serif; }
  main { max-width: 880px; margin: 0 auto; }
  h1 { font-size: 22px; letter-spacing: -0.02em; margin: 0 0 4px; }
  .meta { color: #8a8a8a; font-size: 13px; margin: 0 0 28px; }
  .meta code, .story code { background: #1c1c1c; border: 1px solid #2a2a2a; border-radius: 5px; padding: 1px 6px; font-size: 12px; }
  .story { margin: 0 0 36px; color: #d4d4d4; }
  figure { margin: 0 0 40px; }
  figcaption { font-size: 13px; color: #b5b5b5; margin: 0 0 10px; }
  figcaption strong { color: #fafafa; font-weight: 600; }
  img { width: 100%; height: auto; display: block; border: 1px solid #262626; border-radius: 10px; }
  figure.narrow img { max-width: 320px; }
  /* Paste-ready blocks: use <div class="paste">…</div> (or <pre>) in --story /
     captions — the script below gives every one a copy button automatically.
     Standing rule: a copy-target without a copy button is a bug. */
  .paste, .story pre { position: relative; background: #161616; border: 1px solid #2a2a2a; border-radius: 8px; padding: 14px 72px 14px 16px; font: 13px/1.55 ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre-wrap; color: #e8e8e8; margin: 8px 0 24px; overflow-wrap: break-word; }
  .copywrap { position: relative; }
  .copybtn { position: absolute; top: 8px; right: 8px; font: 600 11px/1 -apple-system, system-ui, sans-serif; color: #d4d4d4; background: #262626; border: 1px solid #3a3a3a; border-radius: 6px; padding: 6px 10px; cursor: pointer; }
  .copybtn.is-copied { color: #0a0a0a; background: #fafafa; border-color: #fafafa; }
</style>
</head>
<body>
<main>
  <h1>$(esc "$TITLE")</h1>
HEAD
[[ -n "$META" ]] && printf '  <p class="meta">%s · Comment on anything that looks off.</p>\n' "$META" \
                 || printf '  <p class="meta">Comment on anything that looks off.</p>\n'
[[ -n "$STORY" ]] && { printf '  <div class="story">\n'; cat "$STORY"; printf '\n  </div>\n'; }
while [[ $# -gt 0 ]]; do
  IMG="$1"; CAP="$2"; shift 2
  [[ -f "$IMG" ]] || { echo "no such image: $IMG" >&2; exit 1; }
  # Portrait/phone shots render at natural-ish width instead of full-bleed.
  CLASS=""
  read -r W H < <(sips -g pixelWidth -g pixelHeight "$IMG" 2>/dev/null | awk '/pixelWidth/{w=$2} /pixelHeight/{h=$2} END{print w, h}')
  [[ -n "$W" && -n "$H" && "$H" -gt "$W" ]] && CLASS=" class=\"narrow\""
  printf '  <figure%s>\n    <figcaption>%s</figcaption>\n    <img alt="%s" src="data:image/png;base64,%s">\n  </figure>\n' \
    "$CLASS" "$CAP" "$(esc "$CAP")" "$(base64 -i "$IMG")"
done
cat <<'TAIL'
</main>
<script>
// Copy button on every paste block / pre. Text is captured before the button
// joins the subtree so the label never leaks into what's copied; runtime
// wrappers can't shift annotation anchors (those are baked server-side from
// the source). textarea+execCommand covers frames without a clipboard API.
(function(){
  document.querySelectorAll("main pre, main .paste").forEach(function(el){
    var text = el.innerText.replace(/\n$/, "");
    var wrap = document.createElement("div");
    wrap.className = "copywrap";
    el.parentNode.insertBefore(wrap, el);
    wrap.appendChild(el);
    var btn = document.createElement("button");
    btn.type = "button"; btn.className = "copybtn"; btn.textContent = "Copy";
    btn.setAttribute("aria-label", "Copy to clipboard");
    var t;
    function done(){ btn.textContent = "Copied"; btn.classList.add("is-copied"); clearTimeout(t); t = setTimeout(function(){ btn.textContent = "Copy"; btn.classList.remove("is-copied"); }, 1600); }
    function fallback(){ var ta = document.createElement("textarea"); ta.value = text; ta.style.cssText = "position:fixed;opacity:0"; document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); } catch (e) {} ta.remove(); done(); }
    btn.addEventListener("click", function(ev){ ev.stopPropagation(); if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, fallback); else fallback(); });
    wrap.appendChild(btn);
  });
})();
</script>
</body>
</html>
TAIL
} > "$OUT"

if [[ -n "$SLUG" ]]; then
  drafty canvas push "$OUT" --title "$TITLE" --slug "$SLUG" --private --project "$PROJECT" --tag proof
else
  drafty canvas push "$OUT" --title "$TITLE" --private --project "$PROJECT" --tag proof
fi
