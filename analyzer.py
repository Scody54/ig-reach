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
dont cant wont its it's you're we're link bio follow comment share save tag
thanks thank week weekend everyone guys""".split())


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


# ---------------- Reel review ----------------
def _reel_stats(m):
    ins = m.get("insights") or {}
    views = ins.get("views") or m.get("view_count") or 0
    reach = ins.get("reach") or 0
    likes = ins.get("likes", m.get("like_count")) or 0
    comments = ins.get("comments", m.get("comments_count")) or 0
    saves, shares = ins.get("saved") or 0, ins.get("shares") or 0
    base = reach or views or 1
    awt = ins.get("ig_reels_avg_watch_time")
    return {
        "views": views, "reach": reach, "likes": likes, "comments": comments,
        "saves": saves, "shares": shares, "follows": ins.get("follows"),
        "avg_watch_s": round(awt / 1000, 1) if awt else None,
        "skip_rate": round(ins["reels_skip_rate"], 1) if ins.get("reels_skip_rate") is not None else None,
        "eng_rate": round((likes + comments + saves + shares) / base * 100, 2),
        "share_rate": round(shares / base * 100, 2), "save_rate": round(saves / base * 100, 2),
        "follow_per_1k": round((ins.get("follows") or 0) / base * 1000, 1) if ins.get("follows") is not None else None,
    }


def reel_list(media):
    reels = [m for m in media if media_format(m) == "Reel"]
    vals = [_reel_stats(m)["views"] for m in reels]
    med = _median(vals, 1) or 1
    out = []
    for m in reels:
        s = _reel_stats(m)
        idx = s["views"] / med
        out.append({"id": m["id"], "date": _ts(m["timestamp"]).strftime("%d %b"),
                    "caption": (m.get("caption") or "")[:70], "thumb": m.get("thumbnail_url"),
                    "permalink": m.get("permalink"), "views": s["views"], "index": round(idx, 2),
                    "label": "Top" if idx >= 1.4 else "Low" if idx <= 0.7 else "Avg"})
    return out


def review_reel(reel, all_media, own_acc, compare_ctx=None):
    reels = [m for m in all_media if media_format(m) == "Reel"]
    s = _reel_stats(reel)
    allstats = [_reel_stats(m) for m in reels]

    def med(k):
        return _median([x[k] for x in allstats if x[k] is not None], None)

    base = {k: med(k) for k in ["views", "reach", "eng_rate", "share_rate", "save_rate",
                                "avg_watch_s", "skip_rate", "follow_per_1k"]}
    idx = s["views"] / (base["views"] or 1)
    verdict = ("Top performer" if idx >= 1.4 else "Underperforming" if idx <= 0.7 else "Average")

    rows = []
    for key, label, unit, higher in [("views", "Views", "", True), ("reach", "Accounts reached", "", True),
                                     ("skip_rate", "Skipped in first 3s", "%", False),
                                     ("avg_watch_s", "Avg watch time", "s", True),
                                     ("eng_rate", "Engagement / reach", "%", True),
                                     ("share_rate", "Shares / reach", "%", True),
                                     ("save_rate", "Saves / reach", "%", True),
                                     ("follow_per_1k", "Follows per 1k reached", "", True)]:
        v, b = s[key], base[key]
        if v is None:
            continue
        good = None if b in (None, 0) else ((v >= b) if higher else (v <= b))
        rows.append({"label": label, "value": v, "benchmark": _r(b, 1) if b is not None else None,
                     "unit": unit, "good": good})

    cap = reel.get("caption") or ""
    first = cap.split("\n")[0].strip()
    tags = HASHTAG_RE.findall(cap)
    posted = _ts(reel["timestamp"])
    best_days = [d["label"] for d in own_acc.get("best_days", [])[:3]]
    best_slots = [d["label"] for d in own_acc.get("best_slots", [])[:2]]
    kws = (compare_ctx or {}).get("keywords") or []

    issues = []

    def issue(sev, title, why, fix):
        issues.append({"severity": sev, "title": title, "why": why, "fix": fix})

    if s["skip_rate"] is not None and s["skip_rate"] >= 45:
        issue("High", "The hook loses people",
              f"{s['skip_rate']}% swiped away in the first 3 seconds (your Reels' median: {base['skip_rate']}%).",
              "Open on the result or the most striking frame. Put a 5-7 word text hook on screen in frame 1. Cut any intro, logo or 'hi guys'.")
    if s["avg_watch_s"] is not None and base["avg_watch_s"] and s["avg_watch_s"] < 0.8 * base["avg_watch_s"]:
        issue("High", "Viewers leave early",
              f"Average watch time {s['avg_watch_s']}s vs your usual {base['avg_watch_s']}s.",
              "Trim to 7–15s, cut every pause, change the shot every 1–2s, and end on a frame that loops back to the start.")
    if base["share_rate"] and s["share_rate"] < 0.7 * base["share_rate"]:
        issue("Medium", "Not shareable enough",
              f"{s['share_rate']}% of viewers shared it vs your usual {base['share_rate']}%. Shares drive reach to non-followers.",
              "Give people a reason to send it: a relatable moment, a 'tag someone who…' angle, or a tip their friend needs.")
    if base["save_rate"] and s["save_rate"] < 0.7 * base["save_rate"]:
        issue("Medium", "Low save value",
              f"{s['save_rate']}% saved it vs your usual {base['save_rate']}%.",
              "Add something worth keeping: a recipe card, price list, steps or a checklist as the last frame. Say 'Save this'.")
    if s["follow_per_1k"] is not None and base["follow_per_1k"] and s["follow_per_1k"] < 0.6 * base["follow_per_1k"]:
        issue("Medium", "Few new followers from it",
              f"{s['follow_per_1k']} follows per 1,000 reached vs your usual {base['follow_per_1k']}.",
              "Give non-followers a reason to follow: say it's part 1 of a series, or end with 'Follow for part 2'.")
    if s["reach"] and own_acc.get("followers") and s["reach"] < 0.3 * own_acc["followers"]:
        issue("Medium", "Barely left your followers",
              f"Reached {s['reach']:,} accounts — under 30% of your {own_acc['followers']:,} followers.",
              "Re-post as a Trial Reel (shown to non-followers first) with a new hook, or collaborate with a comparable page.")
    if not first or len(first) > 125:
        issue("Low", "Caption has no first-line hook",
              "Only the first ~125 characters show before 'more'.",
              "Start the caption with one short line that promises the payoff.")
    if len(tags) > HASHTAG_CAP:
        issue("Low", f"Too many hashtags ({len(tags)})", f"Instagram allows {HASHTAG_CAP}.", "Keep the 3–5 most specific ones.")
    elif not tags:
        issue("Low", "No hashtags", "A few niche tags still help discovery.", "Add 3–5 specific tags from Captions & SEO.")
    if not CTA_RE.search(cap):
        issue("Low", "No call-to-action", "Captions with one clear ask get more comments and saves.",
              "End with one ask: 'Save this', 'Send to a friend who…' or 'Comment YES for the recipe'.")
    if kws and not any(k in cap.lower() for k in kws):
        issue("Low", "No search keyword", "Instagram search reads captions.",
              f"Work in one keyword naturally, e.g. '{kws[0]}'.")
    if best_days and DAYS[posted.weekday()] not in best_days:
        issue("Low", "Posted on a weaker day",
              f"Posted on {DAYS[posted.weekday()]} at {posted.strftime('%I:%M %p')}.",
              f"Your strongest days: {', '.join(best_days)}; windows: {', '.join(best_slots)}.")

    actions = []
    if verdict != "Top performer":
        actions.append({"key": "trial", "title": "Re-post as a Trial Reel",
                        "detail": "Shown to non-followers first; Instagram shares it with your followers only if it does well. Use a new first 2 seconds and a new caption."})
    else:
        actions.append({"key": "pin", "title": "Pin it to the top of your profile",
                        "detail": "Your best Reels convert profile visitors into followers. Pin it in the Instagram app (… → Pin to your profile)."})
    actions += [
        {"key": "story", "title": "Share it to your Story with a sticker",
         "detail": "Add a poll or question sticker. Story taps send viewers back to the Reel and signal interest."},
        {"key": "comments", "title": "Reply to the top comments with video replies",
         "detail": "Each video reply is a new Reel that links back to this one."},
        {"key": "carousel", "title": "Turn it into a carousel",
         "detail": "Use 4–6 key frames + text. Carousels earn saves and reach a different audience."},
    ]
    comps = (compare_ctx or {}).get("competitors") or []
    if comps:
        actions.append({"key": "collab", "title": f"Collab with @{comps[0]}",
                        "detail": "A collab post appears on both profiles. Pick a page from Compare with a similar audience."})

    return {"verdict": verdict, "index": round(idx, 2), "stats": s, "rows": rows,
            "issues": sorted(issues, key=lambda i: {"High": 0, "Medium": 1, "Low": 2}[i["severity"]]),
            "actions": actions, "caption": cap, "first_line": first,
            "posted": posted.strftime("%a %d %b, %I:%M %p"), "permalink": reel.get("permalink"),
            "media_url": reel.get("media_url"), "thumb": reel.get("thumbnail_url"),
            "note": "Instagram's API can't edit a published caption — copy the new one and edit it in the app, or re-post as a Trial Reel."}
