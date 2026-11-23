# IG Reach — grow an Instagram page with evidence

Simple Flask web app. Log in with an Instagram Business/Creator account and it will:

1. **Dashboard** — your Instagram Insights (views, reach, saves, shares, follower change, audience age/gender/city) + per-post stats.
2. **Compare** — benchmark you against 3–8 similar pages. Shows a scorecard, charts, each competitor's habits and their top posts as **evidence**, and a prioritised **action plan**.
3. **Captions & SEO** — keywords competitors rank on that you don't, a Name-field suggestion, hashtags scored by how much they lift competitor posts (max 5, Instagram's limit), and a caption/hook generator (AI if you add an Anthropic key).
4. **Upload** — publish an image, Reel or carousel straight to Instagram, with a pre-publish checklist and best-time-to-post.

Uses only Meta's official API (no scraping), so it won't get the account flagged.

## 📱 Mobile app (APK)
See **MOBILE-SETUP.md**: host on Render → build the APK on GitHub → send the client one link.

## Run it locally (2 minutes, demo mode)
```bash
cd ig-reach
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py            # open http://localhost:5000 → "Try the demo"
```

## Connect real Instagram accounts
1. The Instagram account must be **Professional (Business or Creator)** and **linked to a Facebook Page**.
2. Go to developers.facebook.com → Create App → type **Business** → add product **Instagram** → choose **"API setup with Facebook login"**.
3. In **Facebook Login for Business → Settings**, add the redirect URI: `http://localhost:5000/auth/callback`.
4. Copy **App ID** and **App Secret** into `.env`.
5. While the app is in **Development mode**, only people added under **App roles** (admin/developer/tester) can log in. Fine for you + a few clients.
6. To let any client log in, submit **App Review** for: `instagram_basic`, `instagram_manage_insights`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`, `business_management`, plus **Business Verification**.

## Uploading files
Instagram pulls media from a **public URL**. Two options:
- Paste a public link (S3, Cloudinary, Google Cloud Storage, etc.), or
- Upload in the app and run `ngrok http 5000`, then set `PUBLIC_BASE_URL=https://<your-id>.ngrok-free.app` in `.env`.

Formats: JPEG images; MP4/MOV (H.264 + AAC) Reels. Limit: 100 API posts per 24h per account.

## Good to know
- Competitor data works only for **public Business/Creator accounts** (Business Discovery API). Personal accounts can't be analysed.
- Some insights need **100+ followers**; missing metrics show as "—".
- Graph API version is set in `.env` (`GRAPH_API_VERSION`, default v25.0).
- Times are shown in `APP_TIMEZONE` (default Asia/Kolkata).

## Files
| File | What it does |
|---|---|
| `app.py` | Routes, login, API endpoints |
| `ig_client.py` | Instagram Graph API calls (insights, discovery, publishing) |
| `analyzer.py` | Benchmarks, evidence, recommendations, hashtags, SEO, timing |
| `captions.py` | Caption/hook generator (Claude or templates) |
| `demo_data.py` | Sample data for demo mode |
| `templates/index.html` | The whole UI (phone + desktop) |
| `templates/download.html` | Phone install page (`/download`) |
| `android/` | Android app (Trusted Web Activity wrapper) |
| `.github/workflows/build-apk.yml` | Builds + publishes the APK in the cloud |
| `render.yaml` | One-click hosting on Render |
| `tools/make_icons.py` | Regenerates icons |

## Next upgrades (if needed)
- Save tokens + history in SQLite so clients don't re-login and you can track growth weekly.
- Scheduled posting (APScheduler) — the API publishes instantly, so scheduling must be done by the app.
- Hashtag Search API for tag-level top posts (30 unique tags / 7 days limit).
- Multi-client agency view.
