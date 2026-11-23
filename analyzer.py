"""Turns raw Instagram data into benchmarks, evidence and recommendations.

All logic is plain Python so it is easy to read and tweak.
"""
import math
import os
import re
import statistics as st
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Kolkata"))
HASHTAG_CAP = 5  # Instagram limits posts/Reels to 5 hashtags (since Dec 2025)
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
SLOTS = ["12-3am", "3-6am", "6-9am", "9am-12", "12-3pm", "3-6pm", "6-9pm", "9pm-12"]

HASHTAG_RE = re.compile(r"#(\w+)", re.UNICODE)
MENTION_RE = re.compile(r"@\w+")
URL_RE = re.compile(r"https?://\S+")
WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z']{3,}")
CTA_RE = re.compile(r"\b(comment|save|share|tag|follow|link in bio|dm|click|subscribe|"
                    r"order|book|shop|try this|let me know|tell us|drop a)\b", re.I)
STOP = set("""about above after again against also among another because been before being
below between both could does doing down during each from further have having here hers
herself himself into itself just more most myself only other ours ourselves over same
should some such than that their theirs them themselves then there these they this those
through under until very were what when where which while whom with would your yours
yourself yourselves will shall make made like love today this that what with from have
your just more than into over only every much many most when here there they them their
dont cant wont its it's you're we're link bio follow comment share save tag""".split())


# ---------------- helpers ----------------
def _ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z").astimezone(TZ)


def media_format(m):
    if m.get("media_product_type") == "REELS" or m.get("media_type") == "VIDEO":
        return "Reel"
    if m.get("media_type") == "CAROUSEL_ALBUM":
        return "Carousel"
    return "Image"


def _median(vals, default=0):
    vals = [v for v in vals if v is not None]
    return st.median(vals) if vals else default


def _r(x, n=1):
    if not isinstance(x, (int, float)):
        return x
    return int(round(x)) if n == 0 else round(x, n)


def keywords(text):
    text = URL_RE.sub(" ", HASHTAG_RE.sub(" ", MENTION_RE.sub(" ", text or "")))
    return [w.lower() for w in WORD_RE.findall(text) if w.lower() not in STOP]


# ---------------- per-account analysis ----------------
def analyze_account(profile, media):
    followers = profile.get("followers_count") or 0
    posts = []
    for m in media:
        if not m.get("timestamp"):
            continue
        likes = m.get("like_count") or 0
        comments = m.get("comments_count") or 0
        cap = m.get("caption") or ""
        eng = likes + comments
        posts.append({
            "ts": _ts(m["timestamp"]), "fmt": media_format(m), "likes": likes,
            "comments": comments, "eng": eng, "er": eng / followers * 100 if followers else 0,
            "caption": cap, "tags": [t.lower() for t in HASHTAG_RE.findall(cap)],
            "words": len(cap.split()), "cta": bool(CTA_RE.search(cap)), "question": "?" in cap,
            "views": m.get("view_count"), "permalink": m.get("permalink"),
            "insights": m.get("insights") or {},
        })
    posts.sort(key=lambda p: p["ts"], reverse=True)
    n = len(posts)

    ppw = 0
    if n >= 2:
        span = (posts[0]["ts"] - posts[-1]["ts"]).total_seconds() / 86400
        ppw = (n - 1) / (span / 7) if span > 0 else n
    avg_eng = st.mean([p["eng"] for p in posts]) if posts else 0

    fmt_count = Counter(p["fmt"] for p in posts)
    fmt_eng = defaultdict(list)
    day_eng, slot_eng = defaultdict(list), defaultdict(list)
    tag_count = Counter()
    for p in posts:
        fmt_eng[p["fmt"]].append(p["er"])
        rel = p["eng"] / avg_eng if avg_eng else 0  # performance vs own average
        day_eng[p["ts"].weekday()].append(rel)
        slot_eng[p["ts"].hour // 3].append(rel)
        tag_count.update(set(p["tags"]))

    def ranked(d, labels):
        # smoothed toward 1.0 so a single lucky post doesn't win
        rows = [{"label": labels[k], "lift": _r((sum(v) + 2) / (len(v) + 2), 2), "posts": len(v)}
                for k, v in d.items()]
        return sorted(rows, key=lambda x: -x["lift"])

    reel_views = [p["views"] for p in posts if p["fmt"] == "Reel" and p["views"]]
    top = sorted(posts, key=lambda p: -p["eng"])[:3]
    return {
        "username": profile.get("username"), "name": profile.get("name"),
        "bio": profile.get("biography") or "", "website": profile.get("website"),
        "picture": profile.get("profile_picture_url"), "followers": followers,
        "media_count": profile.get("media_count"), "sample": n,
        "posts_per_week": _r(ppw), "avg_likes": _r(st.mean([p["likes"] for p in posts]) if posts else 0, 0),
        "avg_comments": _r(st.mean([p["comments"] for p in posts]) if posts else 0, 0),
        "avg_engagement": _r(avg_eng, 0),
        "engagement_rate": _r(avg_eng / followers * 100 if followers else 0, 2),
        "format_mix": {k: _r(v / n * 100, 0) for k, v in fmt_count.items()} if n else {},
        "format_er": {k: _r(st.mean(v), 2) for k, v in fmt_eng.items()},
        "best_days": ranked(day_eng, DAYS), "best_slots": ranked(slot_eng, SLOTS),
        "avg_hashtags": _r(st.mean([len(p["tags"]) for p in posts]) if posts else 0),
        "avg_caption_words": _r(st.mean([p["words"] for p in posts]) if posts else 0, 0),
        "cta_rate": _r(sum(p["cta"] for p in posts) / n * 100 if n else 0, 0),
        "question_rate": _r(sum(p["question"] for p in posts) / n * 100 if n else 0, 0),
        "avg_reel_views": _r(st.mean(reel_views), 0) if reel_views else None,
        "top_hashtags": [{"tag": t, "posts": c} for t, c in tag_count.most_common(10)],
        "top_posts": [{"permalink": p["permalink"], "fmt": p["fmt"], "eng": p["eng"],
                       "likes": p["likes"], "comments": p["comments"],
                       "date": p["ts"].strftime("%d %b, %a %I:%M %p"),
                       "caption": (p["caption"][:140] + "…") if len(p["caption"]) > 140 else p["caption"]}
                      for p in top],
        "_posts": posts,  # internal, stripped before sending to browser
    }


def public(acc):
    return {k: v for k, v in acc.items() if not k.startswith("_")}


# ---------------- comparison ----------------
def compare(own, comps):
    comps = [c for c in comps if c["sample"]]
    if not comps:
        return {"error": "No competitor data. Check the usernames are Business/Creator accounts."}

    def bench(key):
        return _median([c[key] for c in comps])

    def leader(key):
        return max(comps, key=lambda c: c[key] or 0)

    b = {k: _r(bench(k), 2) for k in ["posts_per_week", "engagement_rate", "avg_hashtags",
                                       "avg_caption_words", "cta_rate", "question_rate", "followers"]}
    # format share and ER benchmarks
    fmts = ["Reel", "Carousel", "Image"]
    b["format_mix"] = {f: _r(_median([c["format_mix"].get(f, 0) for c in comps]), 0) for f in fmts}
    b["format_er"] = {f: _r(_median([c["format_er"].get(f) for c in comps if f in c["format_er"]]), 2)
                      for f in fmts}

    scorecard = []

    def row(label, key, unit="", higher_better=True):
        you, med, lead = own[key], b[key], leader(key)
        tol = 0.15 * max(abs(med), 1)
        if higher_better is None:  # neither direction is "better"
            status = "higher" if you - med > tol else ("lower" if med - you > tol else "on par")
            if key == "avg_hashtags" and you > HASHTAG_CAP:
                status = "over limit"
        else:
            gap = (you - med) if higher_better else (med - you)
            status = "ahead" if gap > tol else ("behind" if gap < -tol else "on par")
        scorecard.append({"metric": label, "you": you, "benchmark": med, "unit": unit,
                          "leader": f"@{lead['username']}", "leader_value": lead[key], "status": status})

    row("Posts per week", "posts_per_week")
    row("Engagement rate", "engagement_rate", "%")
    row("Captions with a call-to-action", "cta_rate", "%")
    row("Captions asking a question", "question_rate", "%")
    row("Avg caption length (words)", "avg_caption_words", higher_better=None)
    row("Avg hashtags per post", "avg_hashtags", higher_better=None)

    evidence = _evidence(own, comps)
    recs = _recommendations(own, comps, b)
    return {
        "benchmark": b, "scorecard": scorecard, "evidence": evidence, "recommendations": recs,
        "hashtags": suggest_hashtags(own, comps), "seo": seo_ideas(own, comps),
        "upload_plan": upload_plan(own, comps, b),
        "competitors": [public(c) for c in comps],
    }


def _evidence(own, comps):
    ev = []
    for c in comps:
        best_fmt = max(c["format_er"], key=c["format_er"].get) if c["format_er"] else None
        bd = c["best_days"][0]["label"] if c["best_days"] else "-"
        bs = c["best_slots"][0]["label"] if c["best_slots"] else "-"
        facts = [
            f"Posts {c['posts_per_week']}×/week (you: {own['posts_per_week']})",
            f"Engagement rate {c['engagement_rate']}% (you: {own['engagement_rate']}%)",
            "Format mix: " + ", ".join(f"{k} {v}%" for k, v in c["format_mix"].items()),
        ]
        if best_fmt:
            facts.append(f"Best format for them: {best_fmt} ({c['format_er'][best_fmt]}% ER)")
        facts.append(f"Their strongest window: {bd}, {bs}")
        facts.append(f"{c['cta_rate']}% of captions have a CTA; {c['question_rate']}% ask a question")
        if c["top_hashtags"]:
            facts.append("Most used tags: " + " ".join("#" + t["tag"] for t in c["top_hashtags"][:5]))
        ev.append({"username": c["username"], "followers": c["followers"], "facts": facts,
                   "top_posts": c["top_posts"]})
    return ev


def _recommendations(own, comps, b):
    recs = []

    def add(priority, title, why, action):
        recs.append({"priority": priority, "title": title, "why": why, "action": action})

    # 1. Posting frequency
    if own["posts_per_week"] < 0.7 * b["posts_per_week"]:
        lead = max(comps, key=lambda c: c["posts_per_week"])
        target = max(3, round(b["posts_per_week"]))
        add("High", f"Post more often: aim for {target} posts/week",
            f"You post {own['posts_per_week']}×/week. Comparable pages post {b['posts_per_week']}×/week "
            f"(median). @{lead['username']} posts {lead['posts_per_week']}×/week.",
            "Batch-create content once a week. Schedule from the Upload tab.")

    # 2. Format shift
    best_fmt = max(b["format_er"], key=lambda f: b["format_er"][f] or 0)
    own_share = own["format_mix"].get(best_fmt, 0)
    if b["format_er"][best_fmt] and own_share < b["format_mix"].get(best_fmt, 0) - 10:
        add("High", f"Shift your mix toward {best_fmt}s",
            f"Across competitors, {best_fmt}s earn the highest engagement "
            f"({b['format_er'][best_fmt]}% median ER). They make {b['format_mix'][best_fmt]}% of competitor "
            f"posts vs {own_share}% of yours.",
            f"Make at least {max(b['format_mix'][best_fmt], 50):.0f}% of next month's posts {best_fmt}s.")

    # 3. Engagement rate
    if own["engagement_rate"] < 0.8 * b["engagement_rate"]:
        add("High", "Lift engagement per post",
            f"Your engagement rate is {own['engagement_rate']}% vs {b['engagement_rate']}% benchmark.",
            "Open with a hook in the first line / first 2 seconds. End with one clear ask "
            "(comment, save, share). Reply to every comment in the first hour.")

    # 4. CTA usage
    if own["cta_rate"] < b["cta_rate"] - 15:
        add("Medium", "Add a call-to-action to most captions",
            f"{b['cta_rate']}% of competitor captions include a CTA vs {own['cta_rate']}% of yours.",
            "Use asks like 'Save this for later', 'Send this to a friend who…', 'Comment YES for…'.")

    # 5. Questions
    if own["question_rate"] < b["question_rate"] - 15:
        add("Medium", "Ask questions to drive comments",
            f"Competitors ask a question in {b['question_rate']}% of captions; you do in {own['question_rate']}%.",
            "End captions with an easy, opinion-style question.")

    # 6. Hashtags
    if own["avg_hashtags"] > HASHTAG_CAP:
        add("Medium", f"Cut hashtags to {HASHTAG_CAP} or fewer",
            f"You use {own['avg_hashtags']} on average. Instagram now caps posts at {HASHTAG_CAP}.",
            "Pick 3–5 specific tags from the Hashtags list below; put keywords in the caption text instead.")
    elif own["avg_hashtags"] < 2:
        add("Low", "Use 3–5 targeted hashtags",
            f"You average {own['avg_hashtags']} hashtags. A few niche tags still help discovery.",
            "Use the suggested tags below — they come from competitors' best posts.")

    # 7. Caption length
    if b["avg_caption_words"] and abs(own["avg_caption_words"] - b["avg_caption_words"]) > 0.5 * b["avg_caption_words"]:
        direction = "longer" if own["avg_caption_words"] < b["avg_caption_words"] else "shorter"
        add("Low", f"Try {direction} captions",
            f"Your captions average {own['avg_caption_words']} words vs {b['avg_caption_words']} for competitors.",
            "Instagram search reads caption text — work 2–3 keywords in naturally.")

    # 8. Timing
    plan = upload_plan(own, comps, b)
    if plan["best_days"]:
        add("Medium", "Post in your strongest time windows",
            "Based on when your posts and competitor posts over-perform (in "
            f"{TZ.key} time).",
            f"Best days: {', '.join(plan['best_days'][:3])}. Best windows: {', '.join(plan['best_slots'][:2])}.")

    # 9. SEO
    seo = seo_ideas(own, comps)
    if seo["missing_keywords"]:
        add("Medium", "Add search keywords to your name and bio",
            "Instagram search matches the name field and bio. Competitors use keywords you don't: "
            + ", ".join(seo["missing_keywords"][:5]) + ".",
            seo["name_field"])

    order = {"High": 0, "Medium": 1, "Low": 2}
    return sorted(recs, key=lambda r: order[r["priority"]])


# ---------------- hashtags / SEO / upload ----------------
def suggest_hashtags(own, comps, top_n=15):
    score, accounts, uses = defaultdict(float), defaultdict(set), Counter()
    for c in comps:
        avg = c["avg_engagement"] or 1
        for p in c["_posts"]:
            lift = p["eng"] / avg
            for t in set(p["tags"]):
                score[t] += lift
                accounts[t].add(c["username"])
                uses[t] += 1
    own_tags = {t["tag"] for t in own["top_hashtags"]}
    rows = []
    for t, s in score.items():
        rows.append({"tag": t, "uses": uses[t], "accounts": len(accounts[t]),
                     "avg_lift": _r(s / uses[t], 2), "you_use": t in own_tags,
                     "score": s * math.log(1 + len(accounts[t]))})
    rows.sort(key=lambda r: -r["score"])
    for r in rows:
        r.pop("score")
    picks = [r["tag"] for r in rows if r["avg_lift"] >= 1][:HASHTAG_CAP]
    return {"suggested": rows[:top_n], "ready_set": ["#" + t for t in picks],
            "note": f"Instagram allows {HASHTAG_CAP} hashtags per post. 'Lift' = how a post with this tag "
                    f"performed vs that account's average (1.0 = average)."}


def seo_ideas(own, comps):
    own_text = set(keywords(own["bio"] + " " + (own["name"] or "")))
    bio_df, cap_df = Counter(), Counter()
    for c in comps:
        bio_df.update(set(keywords(c["bio"] + " " + (c["name"] or ""))))
        cap_df.update(set(w for p in c["_posts"] for w in keywords(p["caption"])))
    need = 2 if len(comps) > 1 else 1
    score = {w: 3 * bio_df[w] + cap_df[w] for w in set(bio_df) | set(cap_df)
             if bio_df[w] >= 1 or cap_df[w] >= need}
    ranked = sorted(score, key=lambda w: (-score[w], w))
    missing = [w for w in ranked if w not in own_text][:12]
    kw = " · ".join(w.title() for w in missing[:2]) if missing else "Your Main Keyword"
    base = own["name"] or own["username"] or "Brand"
    return {
        "missing_keywords": missing,
        "name_field": f"Set your Name field to something like: \"{base} | {kw}\" (the Name field is searchable; the @handle is too).",
        "tips": [
            "Put your #1 keyword in the first line of every caption — Instagram search reads caption text.",
            "Write a bio that says what you do + who it's for + location (e.g. 'Home bakery in Dhanbad').",
            "Add alt text to images (Upload tab has an alt-text box) — it helps accessibility and search.",
            "Tag a location on posts with local intent.",
            "Use on-screen text and spoken keywords in Reels; Instagram indexes them.",
            "Keep the same 2–3 topics so Instagram learns what your page is about.",
        ],
    }


def upload_plan(own, comps, b):
    day_lift, slot_lift = defaultdict(list), defaultdict(list)
    for acc in [own] + comps:
        for d in acc["best_days"]:
            day_lift[d["label"]].append(d["lift"])
        for s in acc["best_slots"]:
            slot_lift[s["label"]].append(s["lift"])
    days = sorted(day_lift, key=lambda k: -st.mean(day_lift[k]))
    slots = sorted(slot_lift, key=lambda k: -st.mean(slot_lift[k]))
    best_fmt = max(b["format_er"], key=lambda f: b["format_er"][f] or 0) if b.get("format_er") else "Reel"
    return {
        "best_days": days, "best_slots": slots, "best_format": best_fmt,
        "posts_per_week": max(3, round(b.get("posts_per_week") or 3)),
        "specs": [
            {"format": "Reel", "size": "1080×1920 (9:16)", "tip": "Hook in first 2 seconds, on-screen text, keep key text inside the centre safe zone, add a cover image."},
            {"format": "Feed image", "size": "1080×1350 (4:5)", "tip": "Portrait takes more screen space than square. Add alt text."},
            {"format": "Carousel", "size": "1080×1350 (4:5), 2–10 slides via API", "tip": "Slide 1 = promise, last slide = CTA. Great for saves."},
        ],
        "note": "Specs are general best practice; timing comes from your data and your competitors'.",
    }
