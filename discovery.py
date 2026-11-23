"""Finds 5–10 comparable Instagram pages automatically, using only official APIs.

Instagram has no "similar accounts" endpoint, so we:
1. Collect candidate @handles from: the page's own captions/bio, accounts that tagged it,
   top posts under its main hashtags, and optional admin seeds (SEED_COMPETITORS).
2. Check each candidate with Business Discovery (must be a public Business/Creator page).
3. Snowball: pages a good candidate mentions become new candidates.
4. Rank by niche match (shared keywords + hashtags), similar size and recent activity.
"""
import math
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone

from analyzer import HASHTAG_RE, keywords

MENTION_RE = re.compile(r"@([A-Za-z0-9_.]{2,30})")
_CACHE = {}  # (ig_id, username) -> (time, profile, media)
CACHE_TTL = 6 * 3600


def mentions(text):
    return {m.rstrip(".").lower() for m in MENTION_RE.findall(text or "")}


def cached_discover(fetch, ig_id, username):
    key = (ig_id, username.lower())
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1], hit[2]
    profile, media = fetch(username)
    _CACHE[key] = (time.time(), profile, media)
    return profile, media


def _fingerprint(profile, media):
    text = (profile.get("biography") or "") + " " + (profile.get("name") or "")
    words, tags = Counter(keywords(text) * 3), Counter()
    for m in media:
        cap = m.get("caption") or ""
        words.update(keywords(cap))
        tags.update(t.lower() for t in HASHTAG_RE.findall(cap))
    return words, tags


def _overlap(a, b, top=40):
    sa = {w for w, _ in a.most_common(top)}
    sb = {w for w, _ in b.most_common(top)}
    return sa & sb


def score_candidate(own_fp, own_followers, profile, media):
    words, tags = _fingerprint(profile, media)
    kw = _overlap(own_fp[0], words)
    ht = _overlap(own_fp[1], tags)
    f = profile.get("followers_count") or 0
    ratio = f / own_followers if own_followers else 1
    # best when 0.5x–10x your size; penalise far bigger/smaller
    size_fit = math.exp(-abs(math.log(max(ratio, 1e-3)) - math.log(2.5)) / 1.6)
    last = max((m.get("timestamp", "") for m in media), default="")
    active = 0.3
    if last:
        days = (datetime.now(timezone.utc) - datetime.strptime(last, "%Y-%m-%dT%H:%M:%S%z")).days
        active = 1.0 if days <= 14 else 0.7 if days <= 45 else 0.3
    niche = len(kw) * 1.0 + len(ht) * 1.5
    score = (niche + 0.5) * (0.4 + size_fit) * active
    reasons = []
    if ht:
        reasons.append(f"{len(ht)} shared hashtags (#{', #'.join(sorted(ht)[:3])})")
    if kw:
        reasons.append(f"same topics: {', '.join(sorted(kw)[:4])}")
    reasons.append(f"{f:,} followers ({ratio:.1f}× you)")
    if active < 1:
        reasons.append("posts less often lately")
    return round(score, 2), reasons, len(kw) + len(ht)


def discover(fetch, own_profile, own_media, ig_id, extra_sources=None, seeds=None,
             want=10, max_checks=30):
    """fetch(username) -> (profile, media). Returns ranked list of dicts."""
    own_user = (own_profile.get("username") or "").lower()
    own_fp = _fingerprint(own_profile, own_media)
    own_followers = own_profile.get("followers_count") or 1

    queue, why = [], {}

    def add(u, reason):
        u = u.lower().strip().lstrip("@")
        if not u or u == own_user or u in why:
            return
        why[u] = reason
        queue.append(u)

    for s in seeds or []:
        add(s, "your seed list")
    for u in mentions(own_profile.get("biography")):
        add(u, "mentioned in your bio")
    for m in own_media:
        for u in mentions(m.get("caption")):
            add(u, "you mentioned them")
    for u, reason in (extra_sources or []):
        add(u, reason)

    found, checked = {}, 0
    while queue and checked < max_checks:
        u = queue.pop(0)
        try:
            profile, media = cached_discover(fetch, ig_id, u)
        except Exception:
            continue
        checked += 1
        if not media:
            continue
        sc, reasons, niche_hits = score_candidate(own_fp, own_followers, profile, media)
        found[u] = {"username": profile.get("username") or u, "name": profile.get("name"),
                    "followers": profile.get("followers_count"), "score": sc,
                    "niche_hits": niche_hits, "source": why.get(u, ""), "reasons": reasons}
        # snowball only from pages that are actually in the niche
        if niche_hits >= 2:
            for m in media[:12]:
                for v in mentions(m.get("caption")):
                    add(v, f"mentioned by @{profile.get('username') or u}")
            for v in mentions(profile.get("biography")):
                add(v, f"linked from @{profile.get('username') or u}'s bio")

    ranked = sorted(found.values(), key=lambda r: -r["score"])
    top = ranked[0]["score"] if ranked else 0
    # keep real niche matches: some overlap AND at least 20% of the best match's score
    good = [r for r in ranked if r["niche_hits"] >= 3 and r["score"] >= 0.2 * top] or ranked[:want]
    for r in good:
        if (r["followers"] or 0) > 50 * (own_profile.get("followers_count") or 1):
            r["reasons"].append("much bigger — use as inspiration, not a direct benchmark")
    return {"picked": good[:want], "checked": checked,
            "note": ("Found by scanning mentions, tags and hashtag posts, then ranking by shared "
                     "topics, hashtags and size. Remove any that don't fit and add your own.")}


def gather_sources(client, ig_id, own_media):
    """Extra candidate handles from accounts tagging you and from top posts under your hashtags."""
    out = []
    for t in client.tagged_by(ig_id):
        if t.get("username"):
            out.append((t["username"], "tagged you in a post"))
    tags = Counter(t.lower() for m in own_media for t in HASHTAG_RE.findall(m.get("caption") or ""))
    for tag, _ in tags.most_common(3):  # Meta allows 30 unique hashtag searches per 7 days
        for cap in client.hashtag_top_captions(ig_id, tag):
            for u in mentions(cap):
                out.append((u, f"active in top #{tag} posts"))
    return out


def seeds_from_env():
    return [s.strip() for s in os.getenv("SEED_COMPETITORS", "").split(",") if s.strip()]
