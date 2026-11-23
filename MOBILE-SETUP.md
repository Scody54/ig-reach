# IG Reach — mobile app setup (one-time, ~45 min)

**Who does what**
- **You (Sunny), once:** steps 1–6 on a laptop.
- **Client, phone only:** open a link → install → log in. That's it.

---

## 1. Put the code on GitHub (5 min)
1. github.com → **New repository** → name `ig-reach` → **Public** (needed so the client's phone can download the APK without a GitHub login; the code has no secrets).
2. On your Mac:
   ```bash
   cd ig-reach
   git init && git add . && git commit -m "IG Reach"
   git branch -M main
   git remote add origin https://github.com/<you>/ig-reach.git
   git push -u origin main
   ```
   `.gitignore` already blocks `.env`, keys and the secrets file.

## 2. Host the server on Render (10 min)
1. render.com → sign in with GitHub → **New → Blueprint** → pick `ig-reach` → **Apply**.
2. It asks for values marked "sync: false". Fill `META_APP_ID` + `META_APP_SECRET` after step 3 (leave blank for now; you can edit later under **Environment**).
3. Note your URL, e.g. `https://ig-reach.onrender.com`. Open `/demo` on your phone to check it works.

> Free plan sleeps after 15 min idle. Fix (free): GitHub repo → Settings → Secrets and variables → Actions → **Variables** → add `APP_URL` = your Render URL. The **Keep app awake** workflow then pings it every 10 min. Render's free 750 hours/month covers one app running 24/7.
> Free plan bandwidth is ~5 GB/month — roughly 40–50 Reel uploads. Upgrade to Starter only if you hit that.

## 3. Meta app (15 min)
1. developers.facebook.com → **Create app** → **Business** type.
2. Add product **Instagram** → **API setup with Facebook login**.
3. **Facebook Login for Business → Settings → Valid OAuth Redirect URIs:**
   `https://ig-reach.onrender.com/auth/callback`
4. **App settings → Basic:** copy **App ID** and **App Secret** into Render → Environment. Add your Render domain under **App domains**, and a Privacy Policy URL (any page you control).
5. **App roles → Roles → Add people → Testers:** add the client's Facebook account. Client accepts the invite at developers.facebook.com/requests (works from phone).
   - In Development mode only listed testers can log in — perfect for one client. No App Review needed.

**Client's Instagram must be:** Professional (Business/Creator) **and linked to a Facebook Page** they manage.

## 4. Add the signing key to GitHub (3 min)
Open `ANDROID-SIGNING-SECRETS.txt` (sent separately, **never commit it**).
GitHub repo → **Settings → Secrets and variables → Actions → New repository secret** → add the 4 `ANDROID_*` secrets.
Back up the `.jks` file + that txt somewhere safe (Google Drive / password manager). Lose it = no app updates.

## 5. Build the APK (5 min, in the cloud)
GitHub repo → **Actions** → **Build Android APK** → **Run workflow** → paste `https://ig-reach.onrender.com` → Run.
When green, the APK is at:
`https://github.com/<you>/ig-reach/releases/latest/download/IGReach.apk`

## 6. Turn on the download page (2 min)
Render → Environment → set `APK_URL` to the link above → Save (auto-redeploys).
`ANDROID_SHA256` is already set in `render.yaml` — it makes the app open full-screen with no browser bar.
Check: `https://ig-reach.onrender.com/.well-known/assetlinks.json` shows the fingerprint.

---

## Send the client one link
**`https://ig-reach.onrender.com/download`**

On their phone they:
1. Tap **Download the app** → install (allow "Install unknown apps" for Chrome once).
2. Open **IG Reach** → **Log in with Facebook / Instagram** → approve.
3. Done. They stay logged in for ~55 days, then just tap log in again.

## Updating the app later
- **Feature/UI changes:** push to GitHub → Render redeploys. The installed app shows changes instantly. **No new APK needed.**
- **New APK** only if you change the app URL, name or icon → rerun the workflow; the client installs over the old one.

## If something breaks
| Problem | Fix |
|---|---|
| "URL blocked" / redirect error on login | Redirect URI in Meta must exactly match `https://<your-domain>/auth/callback` |
| "No Instagram account linked" | Client's IG isn't Professional or isn't linked to a Page they admin |
| Login says app not available | Client hasn't accepted the Tester invite |
| App shows a browser bar at top | `ANDROID_SHA256` missing on Render, or assetlinks not reachable; clear Chrome data and reopen |
| Upload fails "media processing failed" | Use JPEG for images, MP4 (H.264/AAC) 9:16 for Reels |
| Workflow fails | Open the failed run → copy the red log lines and send them to me |
| Needs Chrome | The app runs on Chrome. Almost every Android phone has it; if not, install from Play Store |
