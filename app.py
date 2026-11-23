"""IG Reach — grow an Instagram page with competitor evidence, insights and publishing."""
import os
import secrets
import uuid
from pathlib import Path

from dotenv import load_dotenv
from datetime import timedelta

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename

load_dotenv()

import analyzer  # noqa: E402
import captions  # noqa: E402
import demo_data  # noqa: E402
from ig_client import GraphError, IGClient, exchange_code, login_url  # noqa: E402

APP_ID = os.getenv("META_APP_ID", "")
APP_SECRET = os.getenv("META_APP_SECRET", "")
REDIRECT_URI = os.getenv("META_REDIRECT_URI", "")  # blank = auto from the site URL
ANDROID_PACKAGE = os.getenv("ANDROID_PACKAGE", "com.igreach.app")
ANDROID_SHA256 = [x.strip() for x in os.getenv("ANDROID_SHA256", "").split(",") if x.strip()]
APK_URL = os.getenv("APK_URL", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
UPLOAD_DIR = Path(__file__).parent / "static" / "uploads"
ALLOWED = {".jpg", ".jpeg", ".png", ".mp4", ".mov"}

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # correct https URLs behind a host
app.secret_key = os.getenv("FLASK_SECRET", secrets.token_hex(16))
app.config.update(
    MAX_CONTENT_LENGTH=300 * 1024 * 1024,
    PERMANENT_SESSION_LIFETIME=timedelta(days=55),  # stay logged in on the phone (token lasts ~60 days)
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("HTTPS_ONLY", "0") == "1",  # set 1 on the hosted server
)


def redirect_uri():
    return REDIRECT_URI or url_for("callback", _external=True)


# ---------------- helpers ----------------
def is_demo():
    return session.get("demo", False)


def client():
    tok = session.get("token")
    return IGClient(tok) if tok else None


def need_login():
    if is_demo():
        return None
    if not session.get("token") or not session.get("ig_id"):
        return jsonify({"error": "Please log in with Facebook first."}), 401
    return None


@app.errorhandler(GraphError)
def graph_error(e):
    return jsonify({"error": f"Instagram API: {e}"}), 400


# ---------------- pages & auth ----------------
@app.route("/")
def index():
    return render_template("index.html", configured=bool(APP_ID and APP_SECRET),
                           logged_in=bool(session.get("token")) or is_demo(),
                           demo=is_demo(), username=session.get("username"))


@app.route("/login")
def login():
    if not (APP_ID and APP_SECRET):
        return redirect(url_for("index"))
    session.permanent = True
    session["state"] = secrets.token_urlsafe(16)
    return redirect(login_url(APP_ID, redirect_uri(), session["state"]))


@app.route("/auth/callback")
def callback():
    if request.args.get("state") != session.get("state"):
        return "Login state mismatch. Please try again.", 400
    if "error" in request.args:
        return f"Login cancelled: {request.args.get('error_description', '')}", 400
    session["token"] = exchange_code(APP_ID, APP_SECRET, redirect_uri(), request.args["code"])
    session.pop("demo", None)
    session.permanent = True
    accts = client().ig_accounts()
    if len(accts) >= 1:
        session["ig_id"], session["username"] = accts[0]["ig_id"], accts[0]["username"]
    return redirect(url_for("index"))


@app.route("/demo")
def demo():
    session.clear()
    session.permanent = True
    session["demo"], session["username"] = True, "demo_bakehouse"
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ---------------- mobile / app install ----------------
@app.route("/download")
def download():
    return render_template("download.html", apk_url=APK_URL)


@app.route("/.well-known/assetlinks.json")
def assetlinks():
    """Proves the Android app owns this site, so it opens full-screen (no URL bar)."""
    if not ANDROID_SHA256:
        return jsonify([])
    return jsonify([{"relation": ["delegate_permission/common.handle_all_urls"],
                     "target": {"namespace": "android_app", "package_name": ANDROID_PACKAGE,
                                "sha256_cert_fingerprints": ANDROID_SHA256}}])


@app.route("/sw.js")
def service_worker():
    resp = send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/healthz")
def healthz():
    return "ok"


# ---------------- API ----------------
@app.get("/api/accounts")
def accounts():
    if is_demo():
        return jsonify([{"ig_id": "demo", "username": "demo_bakehouse", "page": "Demo"}])
    if not session.get("token"):
        return jsonify({"error": "Please log in with Facebook first."}), 401
    return jsonify(client().ig_accounts())


@app.post("/api/select")
def select():
    body = request.get_json(force=True)
    session["ig_id"], session["username"] = body["ig_id"], body.get("username")
    return jsonify({"ok": True})


def _own():
    """Profile + recent media for the logged-in account."""
    if is_demo():
        return demo_data.own()
    c, ig = client(), session["ig_id"]
    return c.profile(ig), c.media(ig, limit=30)


@app.get("/api/dashboard")
def dashboard():
    if r := need_login():
        return r
    profile, media = _own()
    if is_demo():
        ins = demo_data.insights()
    else:
        c = client()
        ins = c.account_insights(session["ig_id"])
        for m in media[:12]:  # per-post insights for the latest posts
            m["insights"] = c.media_insights(m["id"])
    acc = analyzer.analyze_account(profile, media)
    posts = [{"permalink": m.get("permalink"), "fmt": analyzer.media_format(m),
              "date": m.get("timestamp", "")[:10], "likes": m.get("like_count"),
              "comments": m.get("comments_count"), "insights": m.get("insights", {}),
              "caption": (m.get("caption") or "")[:90]} for m in media[:12]]
    return jsonify({"account": analyzer.public(acc), "insights": ins, "posts": posts})


@app.post("/api/compare")
def compare():
    if r := need_login():
        return r
    names = [n.strip().lstrip("@") for n in request.get_json(force=True).get("competitors", []) if n.strip()]
    if is_demo() and not names:
        names = demo_data.DEMO_COMPETITORS
    if not names:
        return jsonify({"error": "Add at least one competitor username."}), 400
    profile, media = _own()
    own = analyzer.analyze_account(profile, media)
    comps, errors = [], []
    for n in names[:8]:
        try:
            p, m = demo_data.competitor(n) if is_demo() else client().discover(session["ig_id"], n)
            comps.append(analyzer.analyze_account(p, m))
        except GraphError as e:
            errors.append(f"@{n}: {e} (must be a public Business/Creator account)")
    result = analyzer.compare(own, comps)
    result["you"] = analyzer.public(own)
    result["errors"] = errors
    session["last_context"] = {"hashtags": result.get("hashtags", {}).get("ready_set", []),
                               "keywords": result.get("seo", {}).get("missing_keywords", [])[:6]}
    return jsonify(result)


@app.post("/api/captions")
def caption_ideas():
    b = request.get_json(force=True)
    ctx = session.get("last_context", {})
    kws = [k.strip() for k in (b.get("keywords") or "").split(",") if k.strip()] or ctx.get("keywords", [])
    tags = [t if t.startswith("#") else "#" + t for t in (b.get("hashtags") or "").split() if t] or ctx.get("hashtags", [])
    return jsonify(captions.generate(b.get("topic", "my latest post"), kws, tags, b.get("tone", "friendly"), ctx))


@app.post("/api/upload-file")
def upload_file():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file"}), 400
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED:
        return jsonify({"error": f"Use one of {', '.join(sorted(ALLOWED))}"}), 400
    name = f"{uuid.uuid4().hex[:10]}_{secure_filename(f.filename)}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    f.save(UPLOAD_DIR / name)
    base = PUBLIC_BASE_URL or request.host_url.rstrip("/")
    url = f"{base}/static/uploads/{name}"
    local = any(h in base for h in ("localhost", "127.0.0.1", "192.168.", "10.0."))
    warn = ("Instagram must download the file from a public URL. Host the app online, "
            "set PUBLIC_BASE_URL, or paste a public link.") if local else None
    return jsonify({"url": url, "type": "VIDEO" if ext in {".mp4", ".mov"} else "IMAGE", "warning": warn})


@app.post("/api/publish")
def publish():
    if r := need_login():
        return r
    b = request.get_json(force=True)
    kind, caption, items = b.get("kind"), b.get("caption", ""), b.get("items", [])
    if caption.count("#") > analyzer.HASHTAG_CAP:
        return jsonify({"error": f"Instagram allows max {analyzer.HASHTAG_CAP} hashtags."}), 400
    if not items:
        return jsonify({"error": "Add at least one media URL."}), 400
    if is_demo():
        return jsonify({"ok": True, "id": "demo_" + uuid.uuid4().hex[:8],
                        "message": "Demo mode: nothing was posted. Log in to publish for real."})
    c, ig = client(), session["ig_id"]
    if kind == "image":
        mid = c.publish_image(ig, items[0]["url"], caption, b.get("alt_text"))
    elif kind == "reel":
        mid = c.publish_reel(ig, items[0]["url"], caption, b.get("cover_url") or None)
    elif kind == "carousel":
        mid = c.publish_carousel(ig, items, caption)
    else:
        return jsonify({"error": "Unknown post type"}), 400
    return jsonify({"ok": True, "id": mid, "message": "Published to Instagram."})


@app.get("/api/publish-limit")
def publish_limit():
    if is_demo():
        return jsonify({"used": 2, "limit": 100})
    if r := need_login():
        return r
    return jsonify(client().publishing_limit(session["ig_id"]))


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", port=int(os.getenv("PORT", 5000)))
