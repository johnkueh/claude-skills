#!/usr/bin/env python3
"""youtube-mine — mine YouTube comments for unanswered questions, via yt-dlp.

Replacement for the retired comment-mine YouTube path. No API key: yt-dlp
scrapes the public site. Output shape is drop-in compatible with
reddit-miner's `mine` (questions[] + clusters_unanswered) so the daily SEO
loops (glp3-daily, johnkueh-daily) can consume either source identically.

Question/cluster NLP is a straight port of reddit-miner's cli.ts.
"""

import argparse
import json
import math
import re
import shutil
import subprocess
import sys

# ----------------------------- NLP (ported from reddit-miner) -----------------------------

QWORDS = re.compile(
    r"^\s*(what|how|when|why|where|which|who|does|do|is|are|was|were|be|been|being|"
    r"can|should|would|will|has|have|did|any|anyone|anybody)\b", re.I)
URL_RX = re.compile(r"https?://\S+|\bwww\.\S+|\[[^\]]+\]\([^)]+\)")
SNARK_RX = re.compile(r"\b(ever stop|are you kidding|are you serious|seriously\?|wtf|lol|lmao|🤣|😂)\b", re.I)
STOPWORDS = set((
    "a an the of for on in to with from at by is are was were be been being "
    "have has had do does did will would can could should may might must shall need ought "
    "i you he she it we they me him her us them my your his its our their "
    "this that these those there where when how what why which who whom whose "
    "and or but if then so as than not no yes do dont don cant won wont about into over under out up down off yeah ya hey lol u ok okay "
    "get got getting gets give gives gave giving go goes going went gone come comes came coming "
    "know knew known knows think thinks thought thinking want wants wanted wanting need needs needed "
    "use uses used using make makes made making take takes took taken taking "
    "see sees saw seen seeing say says said saying tell tells told telling ask asks asked asking "
    "try tries tried trying find finds found finding work works worked working "
    "feel feels felt thing things stuff way ways one two many much lot lots really very just also even still always never "
    "guy guys people person someone anybody anyone everybody everyone friend friends "
    "today yesterday tomorrow day days week weeks month months year years time times "
    "good great bad better best worse worst nice fine ok okay sure right wrong same different "
    "help helps helped helping please thanks thank"
).split())


def clean_text(s):
    if not s:
        return ""
    return re.sub(r"\s+", " ", URL_RX.sub(" ", s).replace("&amp;", "&")).strip()


def extract_question(body, topic_rx):
    body = clean_text(body)
    if not body or "?" not in body or len(body) < 20 or len(body) > 400:
        return None
    if SNARK_RX.search(body):
        return None
    if topic_rx and not topic_rx.search(body):
        return None
    m = re.search(r"([^.?!]{5,300}\?)", body)
    if not m:
        return None
    q = re.sub(r"^(and|but|so|also|oh|hey|hi)[, ]+", "", m.group(1).strip(), flags=re.I).strip()
    if not QWORDS.match(q):
        return None
    tokens = re.findall(r"[A-Za-z'][A-Za-z']*", q)
    if not (4 <= len(tokens) <= 25):
        return None
    return q


def answered(reply_bodies):
    for r in reply_bodies:
        r = (r or "").strip()
        if len(r) < 40 or r.endswith("?"):
            continue
        if r.lower() in ("idk", "dunno", "same", "this", "yes", "no"):
            continue
        return True
    return False


def content_tokens(q_text):
    toks = [t.lower() for t in re.findall(r"[A-Za-z][A-Za-z']{2,}", q_text)]
    return [t for t in toks if t not in STOPWORDS and not QWORDS.match(t)]


def cluster(qs, top_n=10):
    if not qs:
        return []
    df = {}
    for q in qs:
        for t in set(content_tokens(q["q"])):
            df[t] = df.get(t, 0) + 1
    n = len(qs)
    rarity = lambda t: -math.log((df.get(t, 0) + 1) / (n + 1))

    buckets = {}
    def put(key, q):
        buckets.setdefault("\x1f".join(key), {"key": key, "items": []})["items"].append(q)

    for q in qs:
        toks = [t for t in content_tokens(q["q"]) if df.get(t, 0) >= 2]
        if not toks:
            put(["_singleton", q["q"][:40].lower()], q)
            continue
        ranked = sorted(set(toks), key=lambda t: (-rarity(t), t))
        put(sorted(ranked[:2]) if len(ranked) >= 2 else [ranked[0]], q)

    merged = {}
    def mput(key, items):
        merged.setdefault("\x1f".join(key), {"key": key, "items": []})["items"].extend(items)

    for b in buckets.values():
        key, items = b["key"], b["items"]
        if key[0] == "_singleton":
            mput(key, items)
        elif len(items) == 1 and len(key) == 2:
            mput([key[0]], items)
        else:
            mput(key, items)

    out = []
    for b in merged.values():
        if b["key"][0] == "_singleton":
            continue
        items = sorted(b["items"], key=lambda x: -x["score"])
        out.append({
            "key": " + ".join(b["key"]), "count": len(items), "top_score": items[0]["score"],
            "sample": items[0]["q"], "permalink": items[0]["permalink"],
            "examples": [{"q": i["q"], "score": i["score"], "permalink": i["permalink"]} for i in items[:3]],
        })
    out.sort(key=lambda c: (-c["count"], -c["top_score"]))
    return out[:top_n]


# ----------------------------- yt-dlp plumbing -----------------------------

def ytdlp(args, timeout=300):
    cmd = ["yt-dlp", "--no-warnings", "--quiet"] + args
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp failed ({r.returncode}): {r.stderr.strip()[:400]}")
    return r.stdout


def search_videos(query, limit):
    out = ytdlp(["-J", "--flat-playlist", f"ytsearch{limit}:{query}"])
    data = json.loads(out)
    vids = []
    for e in data.get("entries") or []:
        if not e or not e.get("id"):
            continue
        vids.append({
            "id": e["id"],
            "title": e.get("title") or "",
            "channel": e.get("channel") or e.get("uploader") or "",
            "view_count": e.get("view_count"),
            "url": f"https://www.youtube.com/watch?v={e['id']}",
        })
    return vids


def channel_videos(channel, limit):
    url = channel if channel.startswith("http") else f"https://www.youtube.com/{channel.lstrip('@') and '@' + channel.lstrip('@')}"
    out = ytdlp(["-J", "--flat-playlist", "--playlist-end", str(limit), url.rstrip("/") + "/videos"])
    data = json.loads(out)
    vids = []
    for e in data.get("entries") or []:
        if not e or not e.get("id"):
            continue
        vids.append({
            "id": e["id"],
            "title": e.get("title") or "",
            "view_count": e.get("view_count"),
            "duration": e.get("duration"),
            "url": f"https://www.youtube.com/watch?v={e['id']}",
        })
    return vids


def fetch_comments(video_id, max_comments):
    # max_comments extractor-arg: max-comments,max-parents,max-replies,max-replies-per-thread
    out = ytdlp([
        "-J", "--skip-download", "--write-comments",
        "--extractor-args", f"youtube:max_comments={max_comments},all,all,10;comment_sort=top",
        f"https://www.youtube.com/watch?v={video_id}",
    ], timeout=600)
    data = json.loads(out)
    return data.get("comments") or []


# ----------------------------- commands -----------------------------

def cmd_mine(args):
    topic_rx = re.compile(args.topic_keywords, re.I) if args.topic_keywords else None
    questions, videos_scanned, comments_scanned, failures = [], 0, 0, []

    videos = search_videos(args.query, args.videos)
    for v in videos:
        try:
            comments = fetch_comments(v["id"], args.comments)
        except Exception as e:  # one dead video must not kill the mine
            failures.append({"video": v["id"], "error": str(e)[:200]})
            continue
        videos_scanned += 1
        comments_scanned += len(comments)
        by_parent = {}
        for c in comments:
            if c.get("parent") and c["parent"] != "root":
                by_parent.setdefault(c["parent"], []).append(c.get("text") or "")
        for c in comments:
            if c.get("parent") != "root":
                continue
            q = extract_question(c.get("text") or "", topic_rx)
            if not q:
                continue
            replies = by_parent.get(c.get("id"), [])
            questions.append({
                "q": q,
                "score": int(c.get("like_count") or 0),
                "answered": answered(replies),
                "n_replies": len(replies),
                "source": "youtube-comment",
                "thread_title": v["title"],
                "permalink": v["url"],
            })

    unans = [q for q in questions if not q["answered"]]
    result = {
        "query": args.query,
        "videos_scanned": videos_scanned,
        "comments_scanned": comments_scanned,
        "n_questions": len(questions),
        "n_unanswered": len(unans),
        "questions": questions,
        "top_questions": sorted(unans, key=lambda q: -q["score"])[:10],
        "clusters_unanswered": cluster(unans, 10),
        "failures": failures,
    }
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    print()


def cmd_videos(args):
    vids = channel_videos(args.channel, args.limit) if args.channel else search_videos(args.query, args.limit)
    json.dump(vids, sys.stdout, indent=2, ensure_ascii=False)
    print()


def cmd_comments(args):
    json.dump(fetch_comments(args.video, args.limit), sys.stdout, indent=2, ensure_ascii=False)
    print()


def cmd_doctor(args):
    ok = True
    path = shutil.which("yt-dlp")
    print(f"yt-dlp on PATH   {'OK ' + path if path else 'MISSING — brew install yt-dlp'}")
    ok = ok and bool(path)
    if path:
        try:
            v = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
            print(f"yt-dlp version   {v}")
            live = search_videos("test", 1)
            print(f"live search      {'OK (' + live[0]['id'] + ')' if live else 'FAILED — no results'}")
            ok = ok and bool(live)
        except Exception as e:
            print(f"live search      FAILED — {e}")
            ok = False
    sys.exit(0 if ok else 1)


def main():
    p = argparse.ArgumentParser(prog="youtube-mine")
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("mine", help="search videos, pull comments, extract+cluster unanswered questions")
    m.add_argument("--query", required=True)
    m.add_argument("--videos", type=int, default=8)
    m.add_argument("--comments", type=int, default=250, help="max comments per video")
    m.add_argument("--topic-keywords", default=None, help="regex; only keep questions matching it")
    m.set_defaults(fn=cmd_mine)

    v = sub.add_parser("videos", help="list videos by search query or channel")
    g = v.add_mutually_exclusive_group(required=True)
    g.add_argument("--query")
    g.add_argument("--channel", help="@handle or channel URL")
    v.add_argument("--limit", type=int, default=15)
    v.set_defaults(fn=cmd_videos)

    c = sub.add_parser("comments", help="raw comments for one video")
    c.add_argument("--video", required=True, help="video id")
    c.add_argument("--limit", type=int, default=250)
    c.set_defaults(fn=cmd_comments)

    d = sub.add_parser("doctor", help="check yt-dlp + live search")
    d.set_defaults(fn=cmd_doctor)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
