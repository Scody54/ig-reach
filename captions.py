"""Caption + hook ideas. Uses Claude if ANTHROPIC_API_KEY is set, else templates."""
import json
import os
import random

import requests

HOOKS = [
    "Stop scrolling if you love {kw}.",
    "3 {kw} mistakes everyone makes (and the fix).",
    "Nobody talks about this {kw} secret.",
    "We tried 5 {kw} ideas. Here's the winner.",
    "The {kw} guide I wish I had earlier.",
    "Save this for your next {kw} plan.",
    "{Kw}: beginner vs pro.",
]
CTAS = [
    "Save this for later 📌",
    "Send this to someone who needs it.",
    "Comment '{kw}' and I'll share the full list.",
    "Which one is your favourite? Tell me below 👇",
    "Follow for more {kw} tips.",
]


def _templates(topic, keywords, hashtags):
    kw = (keywords[0] if keywords else topic).strip()
    out = []
    for hook in random.sample(HOOKS, 3):
        h = hook.format(kw=kw, Kw=kw.capitalize())
        body = f"{topic.strip().rstrip('.!?').capitalize()}. Here's what makes it worth it 👇"
        cta = random.choice(CTAS).format(kw=kw.split()[0].upper() if kw else "YES")
        out.append(f"{h}\n\n{body}\n\n{cta}\n\n{' '.join(hashtags[:5])}".strip())
    return {"source": "templates", "captions": out,
            "reel_ideas": [f"{kw}: before vs after", f"Day-in-the-life featuring {kw}",
                           f"Top 3 {kw} picks, fast cuts, text on screen"]}


def generate(topic, keywords=None, hashtags=None, tone="friendly", context=None):
    keywords = [k for k in (keywords or []) if k]
    hashtags = (hashtags or [])[:5]
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return _templates(topic, keywords, hashtags)
    prompt = (
        "You write Instagram captions that grow reach. Return JSON only: "
        '{"captions": [3 strings], "reel_ideas": [3 short strings]}.\n'
        f"Topic: {topic}\nTone: {tone}\nSearch keywords to work in naturally (first line especially): {keywords}\n"
        f"Hashtags to end with (max 5): {hashtags}\n"
        f"What works for competitors: {json.dumps(context or {})[:1500]}\n"
        "Each caption: strong first-line hook, 40-120 words, one clear call-to-action, line breaks."
    )
    try:
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=60, headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5"), "max_tokens": 1500,
                  "messages": [{"role": "user", "content": prompt}]})
        text = r.json()["content"][0]["text"]
        data = json.loads(text[text.find("{"): text.rfind("}") + 1])
        data["source"] = "claude"
        return data
    except Exception:
        return _templates(topic, keywords, hashtags)
