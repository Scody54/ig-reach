"""Synthetic data so the app works before Meta credentials are set up."""
import random
from datetime import datetime, timedelta, timezone

TAGS = ["homebaker", "cakesofinstagram", "dhanbadfood", "jharkhandfoodie", "eggless",
        "customcakes", "bakingreels", "dessertlover", "birthdaycake", "chocolatecake",
        "foodblogger", "indianbaker", "cupcakes", "bakeryindia", "sweettooth"]
CAPS = [
    "Fresh out of the oven! Our eggless chocolate truffle cake for a birthday in Dhanbad.",
    "3 mistakes that make your cake dry (and how to fix them). Save this for later!",
    "Which flavour should we drop next weekend? Comment below 👇",
    "Custom cake orders open for this week. DM to book your slot.",
    "Behind the scenes: decorating a 2-tier anniversary cake.",
    "Soft, fluffy cupcakes with zero eggs. Send this to a friend who loves desserts.",
    "Our bestselling red velvet. Tag someone who deserves a slice.",
    "Weekend special: Belgian chocolate jar cakes. Link in bio to order.",
]
PROFILES = {
    "demo_bakehouse": dict(name="Demo Bakehouse", followers=2400, bio="Cakes & desserts. Orders open.",
                           ppw=1.3, fmt=[0.45, 0.2, 0.35], base_er=2.0, tags=8, cta=0.25),
    "cakecraft.dhn": dict(name="CakeCraft | Eggless Cakes Dhanbad", followers=8900,
                          bio="Eggless custom cakes in Dhanbad 🎂 Home bakery · Same-day delivery",
                          ppw=5.5, fmt=[0.65, 0.2, 0.15], base_er=4.2, tags=4, cta=0.7),
    "sugarloaf.ranchi": dict(name="Sugarloaf Bakery Ranchi · Custom Cakes",
                             bio="Custom birthday cakes & dessert boxes · Ranchi · Eggless options",
                             followers=15200, ppw=4.0, fmt=[0.55, 0.35, 0.10], base_er=3.6, tags=5, cta=0.6),
    "theeggless.oven": dict(name="The Eggless Oven | Home Bakery",
                            bio="Home bakery · eggless cakes, cupcakes & brownies · Jharkhand",
                            followers=5100, ppw=3.2, fmt=[0.5, 0.3, 0.2], base_er=5.0, tags=3, cta=0.55),
    "bokaro.bakes": dict(name="Bokaro Bakes · Custom Cakes", bio="Custom birthday cakes & cupcakes · Bokaro · eggless available",
                         followers=3900, ppw=3.0, fmt=[0.5, 0.25, 0.25], base_er=4.4, tags=4, cta=0.5),
    "dessertdiaries.jh": dict(name="Dessert Diaries Jharkhand", bio="Desserts, brownies & jar cakes · home bakery · Ranchi",
                              followers=11800, ppw=4.5, fmt=[0.6, 0.3, 0.1], base_er=3.9, tags=5, cta=0.6),
    "crumbsandco.dhn": dict(name="Crumbs & Co Dhanbad", bio="Cafe & bakery · cakes, cookies, coffee · Dhanbad",
                            followers=6700, ppw=2.6, fmt=[0.4, 0.3, 0.3], base_er=3.1, tags=4, cta=0.45),
    "thecakestudio.in": dict(name="The Cake Studio", bio="Celebration cakes · pan-India delivery",
                             followers=420000, ppw=7.0, fmt=[0.7, 0.2, 0.1], base_er=1.8, tags=5, cta=0.5),
    "fitwithrahul": dict(name="Rahul | Fitness Coach", bio="Gym workouts · fat loss · online coaching",
                         followers=9400, ppw=5.0, fmt=[0.8, 0.1, 0.1], base_er=4.0, tags=5, cta=0.6, offniche=True),
    "dhanbad.diaries": dict(name="Dhanbad Diaries", bio="City news, food & events in Dhanbad",
                            followers=25000, ppw=6.0, fmt=[0.6, 0.2, 0.2], base_er=2.2, tags=5, cta=0.3, offniche=True),
}
# who mentions whom (drives the demo "snowball" discovery)
MENTIONS = {
    "demo_bakehouse": ["cakecraft.dhn", "dhanbad.diaries"],
    "cakecraft.dhn": ["sugarloaf.ranchi", "theeggless.oven", "bokaro.bakes"],
    "sugarloaf.ranchi": ["dessertdiaries.jh", "thecakestudio.in"],
    "theeggless.oven": ["crumbsandco.dhn"],
    "dhanbad.diaries": ["fitwithrahul", "crumbsandco.dhn"],
}
OFFNICHE_CAPS = ["Leg day done. 4 sets, no excuses. Follow for more workouts.",
                 "Big news from Dhanbad today — traffic changes near the station.",
                 "Weekend events in the city you shouldn't miss."]
OFFNICHE_TAGS = ["fitness", "gym", "dhanbadnews", "workout", "dhanbadcity", "events"]


def _media(username, n=25):
    p = PROFILES.get(username) or dict(name=username.title(), followers=random.randint(3000, 20000),
                                       bio="Desserts & cakes · eggless options", ppw=3.5,
                                       fmt=[0.5, 0.3, 0.2], base_er=3.5, tags=4, cta=0.5)
    rnd = random.Random(username)
    now = datetime.now(timezone.utc)
    t = now - timedelta(hours=rnd.randint(2, 30))
    out = []
    for i in range(n):
        t = t.replace(hour=rnd.choice([3, 7, 12, 13, 14, 15, 16]), minute=rnd.randint(0, 59))
        kind = rnd.choices(["REELS", "CAROUSEL_ALBUM", "IMAGE"], weights=p["fmt"])[0]
        mult = {"REELS": 1.5, "CAROUSEL_ALBUM": 1.15, "IMAGE": 0.7}[kind]
        if t.weekday() in (4, 5, 6):
            mult *= 1.2
        if 12 <= t.hour <= 15:  # ~6-9pm IST
            mult *= 1.25
        eng = p["followers"] * p["base_er"] / 100 * mult * rnd.uniform(0.6, 1.4)
        cap = rnd.choice(OFFNICHE_CAPS if p.get("offniche") else CAPS)
        if rnd.random() > p["cta"]:
            cap = cap.split(".")[0] + "."
        pool = OFFNICHE_TAGS if p.get("offniche") else (TAGS[:9] if p["tags"] <= 5 else TAGS)
        tags = rnd.sample(pool, k=min(p["tags"], len(pool)))
        if MENTIONS.get(username) and i < 6:
            cap += f" Thanks @{MENTIONS[username][i % len(MENTIONS[username])]}!"
        out.append({
            "id": f"{username}_{i}", "caption": cap + "\n\n" + " ".join("#" + x for x in tags),
            "media_type": "VIDEO" if kind == "REELS" else kind,
            "media_product_type": "REELS" if kind == "REELS" else "FEED",
            "like_count": int(eng * 0.92), "comments_count": int(eng * 0.08) + 1,
            "timestamp": t.strftime("%Y-%m-%dT%H:%M:%S+0000"),
            "permalink": "https://www.instagram.com/",
            "view_count": int(eng * rnd.uniform(8, 20)) if kind == "REELS" else None,
            "media_url": "https://example.com/demo-reel.mp4" if kind == "REELS" else None,
        })
        if kind == "REELS":
            views = out[-1]["view_count"]
            hook = rnd.uniform(0.6, 1.4)
            out[-1]["insights"] = {
                "views": views, "reach": int(views * rnd.uniform(0.55, 0.75)),
                "likes": out[-1]["like_count"], "comments": out[-1]["comments_count"],
                "saved": int(eng * rnd.uniform(0.03, 0.12)), "shares": int(eng * rnd.uniform(0.02, 0.1)),
                "ig_reels_avg_watch_time": int(rnd.uniform(2500, 9000) * hook),
                "reels_skip_rate": round(min(80, max(15, 45 / hook + rnd.uniform(-8, 8))), 1),
                "follows": int(views * rnd.uniform(0.001, 0.006)),
            }
        t -= timedelta(days=7 / p["ppw"] * rnd.uniform(0.6, 1.4))
    profile = {"username": username, "name": p["name"], "biography": p["bio"],
               "followers_count": p["followers"], "media_count": rnd.randint(150, 900),
               "profile_picture_url": None, "website": None}
    return profile, out


def own():
    return _media("demo_bakehouse")


def competitor(username):
    return _media(username.strip().lstrip("@"))


DEMO_COMPETITORS = ["cakecraft.dhn", "sugarloaf.ranchi", "theeggless.oven"]


def fetch(username):
    """Business-Discovery-like lookup for demo mode."""
    u = username.strip().lstrip("@").lower()
    if u not in PROFILES:
        raise ValueError("not a demo account")
    return _media(u, n=12)


def insights():
    rnd = random.Random(7)
    base = 2400
    series = []
    for i in range(29, 0, -1):
        base += rnd.randint(-3, 9)
        series.append({"date": (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d"),
                       "value": rnd.randint(-3, 9)})
    return {
        "totals": {"views": 48210, "reach": 9120, "accounts_engaged": 610, "total_interactions": 1480,
                   "likes": 1210, "comments": 96, "shares": 74, "saves": 100, "profile_links_taps": 41,
                   "follows_and_unfollows": 118},
        "follower_change": series,
        "demographics": {
            "age": [{"key": "25-34", "value": 980}, {"key": "18-24", "value": 720},
                    {"key": "35-44", "value": 410}, {"key": "45-54", "value": 150}],
            "gender": [{"key": "F", "value": 1560}, {"key": "M", "value": 790}, {"key": "U", "value": 50}],
            "city": [{"key": "Dhanbad, Jharkhand", "value": 1120}, {"key": "Ranchi, Jharkhand", "value": 310},
                     {"key": "Bokaro, Jharkhand", "value": 190}, {"key": "Kolkata, West Bengal", "value": 140}],
        },
    }
