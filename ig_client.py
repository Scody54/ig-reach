"""Thin wrapper around the official Instagram API (with Facebook Login).

Uses only Meta-approved endpoints: no scraping.
- Your own account: profile, media, insights, publishing
- Other accounts: Business Discovery (public data of Business/Creator accounts)
"""
import os
import time
from datetime import datetime, timedelta, timezone

import requests

GRAPH_VERSION = os.getenv("GRAPH_API_VERSION", "v25.0")
GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"

SCOPES = [
    "instagram_basic",
    "instagram_manage_insights",
    "instagram_content_publish",
    "pages_show_list",
    "pages_read_engagement",
    "business_management",
]

MEDIA_FIELDS = ("id,caption,media_type,media_product_type,like_count,comments_count,"
                "timestamp,permalink,thumbnail_url,media_url")
DISCOVERY_MEDIA_FIELDS = ("caption,media_type,media_product_type,like_count,comments_count,"
                          "timestamp,permalink,view_count")


class GraphError(Exception):
    pass


def _check(resp):
    try:
        data = resp.json()
    except ValueError:
        raise GraphError(f"Bad response from Meta ({resp.status_code})")
    if isinstance(data, dict) and "error" in data:
        raise GraphError(data["error"].get("message", "Unknown Graph API error"))
    return data


# ---------------- OAuth ----------------
def login_url(app_id, redirect_uri, state):
    from urllib.parse import urlencode
    q = urlencode({"client_id": app_id, "redirect_uri": redirect_uri, "state": state,
                   "scope": ",".join(SCOPES), "response_type": "code"})
    return f"https://www.facebook.com/{GRAPH_VERSION}/dialog/oauth?{q}"


def exchange_code(app_id, app_secret, redirect_uri, code):
    """Code -> short-lived token -> long-lived (~60 day) token."""
    short = _check(requests.get(f"{GRAPH}/oauth/access_token", timeout=30, params={
        "client_id": app_id, "client_secret": app_secret,
        "redirect_uri": redirect_uri, "code": code}))["access_token"]
    long = _check(requests.get(f"{GRAPH}/oauth/access_token", timeout=30, params={
        "grant_type": "fb_exchange_token", "client_id": app_id,
        "client_secret": app_secret, "fb_exchange_token": short}))
    return long["access_token"]


# ---------------- Client ----------------
class IGClient:
    def __init__(self, token):
        self.token = token

    def _get(self, path, **params):
        params["access_token"] = self.token
        return _check(requests.get(f"{GRAPH}/{path}", params=params, timeout=45))

    def _post(self, path, **data):
        data["access_token"] = self.token
        return _check(requests.post(f"{GRAPH}/{path}", data=data, timeout=60))

    # ----- accounts -----
    def ig_accounts(self):
        """Instagram professional accounts linked to the user's Facebook Pages."""
        res = self._get("me/accounts", fields="id,name,instagram_business_account"
                        "{id,username,profile_picture_url}", limit=100)
        out = []
        for page in res.get("data", []):
            ig = page.get("instagram_business_account")
            if ig:
                out.append({"ig_id": ig["id"], "username": ig.get("username"),
                            "picture": ig.get("profile_picture_url"), "page": page.get("name")})
        return out

    def profile(self, ig_id):
        return self._get(ig_id, fields="username,name,biography,website,followers_count,"
                                       "follows_count,media_count,profile_picture_url")

    def media(self, ig_id, limit=30):
        return self._get(f"{ig_id}/media", fields=MEDIA_FIELDS, limit=limit).get("data", [])

    # ----- insights -----
    def account_insights(self, ig_id, days=28):
        """Totals for the last `days` (max 30). Each metric fetched separately so one
        unsupported metric does not break the rest."""
        until = datetime.now(timezone.utc)
        since = until - timedelta(days=min(days, 30))
        totals = {}
        for metric in ["views", "reach", "accounts_engaged", "total_interactions", "likes",
                       "comments", "shares", "saves", "profile_links_taps", "follows_and_unfollows"]:
            try:
                d = self._get(f"{ig_id}/insights", metric=metric, period="day",
                              metric_type="total_value", since=int(since.timestamp()),
                              until=int(until.timestamp()))
                for row in d.get("data", []):
                    totals[row["name"]] = row.get("total_value", {}).get("value")
            except GraphError:
                totals.setdefault(metric, None)

        series = []
        try:  # daily follower change (last 30 days, excludes today)
            d = self._get(f"{ig_id}/insights", metric="follower_count", period="day",
                          since=int((until - timedelta(days=29)).timestamp()),
                          until=int((until - timedelta(days=1)).timestamp()))
            for row in d.get("data", []):
                series = [{"date": v["end_time"][:10], "value": v["value"]} for v in row["values"]]
        except GraphError:
            pass

        demographics = {}
        for bd in ["age", "gender", "city"]:
            try:
                d = self._get(f"{ig_id}/insights", metric="follower_demographics",
                              period="lifetime", metric_type="total_value",
                              timeframe="this_month", breakdown=bd)
                rows = d["data"][0]["total_value"]["breakdowns"][0]["results"]
                demographics[bd] = sorted(
                    [{"key": r["dimension_values"][0], "value": r["value"]} for r in rows],
                    key=lambda x: -x["value"])[:8]
            except (GraphError, KeyError, IndexError):
                pass
        return {"totals": totals, "follower_change": series, "demographics": demographics}

    def media_insights(self, media_id, reel=False):
        out = {}
        metrics = ["reach", "views", "saved", "shares", "total_interactions", "likes", "comments"]
        if reel:
            metrics += ["ig_reels_avg_watch_time", "ig_reels_video_view_total_time", "reels_skip_rate", "follows"]
        try:  # one call for everything; fall back to one-by-one if any metric is rejected
            d = self._get(f"{media_id}/insights", metric=",".join(metrics))
            for row in d.get("data", []):
                out[row["name"]] = row["values"][0]["value"]
            return out
        except GraphError:
            pass
        for metric in metrics:
            try:
                d = self._get(f"{media_id}/insights", metric=metric)
                for row in d.get("data", []):
                    out[row["name"]] = row["values"][0]["value"]
            except GraphError:
                pass
        return out

    # ----- discovery sources -----
    def tagged_by(self, ig_id, limit=50):
        """Usernames of accounts that tagged this account in their posts."""
        try:
            d = self._get(f"{ig_id}/tags", fields="username,caption", limit=limit)
            return d.get("data", [])
        except GraphError:
            return []

    def hashtag_top_captions(self, ig_id, tag):
        """Captions of top posts under a hashtag (no usernames are returned by Meta)."""
        try:
            hid = self._get("ig_hashtag_search", user_id=ig_id, q=tag.lstrip("#"))["data"][0]["id"]
            d = self._get(f"{hid}/top_media", user_id=ig_id, fields="caption,like_count,comments_count", limit=30)
            return [m.get("caption") or "" for m in d.get("data", [])]
        except (GraphError, KeyError, IndexError):
            return []

    # ----- competitors -----
    def discover(self, ig_id, username, limit=25):
        username = username.strip().lstrip("@")
        fields = (f"business_discovery.username({username})"
                  "{username,name,biography,website,followers_count,media_count,profile_picture_url,"
                  f"media.limit({limit}){{{DISCOVERY_MEDIA_FIELDS}}}}}")
        bd = self._get(ig_id, fields=fields)["business_discovery"]
        media = bd.pop("media", {}).get("data", [])
        return bd, media

    # ----- publishing -----
    def publishing_limit(self, ig_id):
        d = self._get(f"{ig_id}/content_publishing_limit", fields="config,quota_usage")
        row = (d.get("data") or [{}])[0]
        return {"used": row.get("quota_usage"), "limit": row.get("config", {}).get("quota_total")}

    def _wait(self, container_id, timeout=300):
        start = time.time()
        while time.time() - start < timeout:
            st = self._get(container_id, fields="status_code,status").get("status_code")
            if st == "FINISHED":
                return
            if st in ("ERROR", "EXPIRED"):
                raise GraphError(f"Media processing failed ({st}). Check file format/size.")
            time.sleep(5)
        raise GraphError("Media still processing after 5 minutes. Try again later.")

    def _publish(self, ig_id, creation_id):
        return self._post(f"{ig_id}/media_publish", creation_id=creation_id)["id"]

    def publish_image(self, ig_id, image_url, caption, alt_text=None):
        data = {"image_url": image_url, "caption": caption}
        if alt_text:
            data["alt_text"] = alt_text
        cid = self._post(f"{ig_id}/media", **data)["id"]
        self._wait(cid)
        return self._publish(ig_id, cid)

    def publish_reel(self, ig_id, video_url, caption, cover_url=None, share_to_feed=True, trial=False):
        """trial=True publishes a Trial Reel: shown to non-followers first, auto-shared to
        followers if it performs well (graduation_strategy SS_PERFORMANCE)."""
        data = {"media_type": "REELS", "video_url": video_url, "caption": caption,
                "share_to_feed": "true" if share_to_feed else "false"}
        if cover_url:
            data["cover_url"] = cover_url
        if trial:
            import json as _json
            data["trial_params"] = _json.dumps({"graduation_strategy": "SS_PERFORMANCE"})
            data.pop("share_to_feed", None)
        cid = self._post(f"{ig_id}/media", **data)["id"]
        self._wait(cid)
        return self._publish(ig_id, cid)

    def publish_carousel(self, ig_id, items, caption):
        """items: [{"type": "IMAGE"|"VIDEO", "url": "..."}], 2-10 items."""
        if not 2 <= len(items) <= 10:
            raise GraphError("A carousel needs 2 to 10 items.")
        children = []
        for it in items:
            data = {"is_carousel_item": "true"}
            if it["type"] == "VIDEO":
                data.update(media_type="VIDEO", video_url=it["url"])
            else:
                data["image_url"] = it["url"]
            cid = self._post(f"{ig_id}/media", **data)["id"]
            self._wait(cid)
            children.append(cid)
        cid = self._post(f"{ig_id}/media", media_type="CAROUSEL",
                         children=",".join(children), caption=caption)["id"]
        self._wait(cid)
        return self._publish(ig_id, cid)
