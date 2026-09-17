# Deploy a free test copy on Render

Result: a public HTTPS link such as `https://sustainzone-eudr-gateway.onrender.com`.

## Free-tier limits (fine for testing, not for real client data)
- The app sleeps after ~15 minutes without visitors; the next visit takes about a minute to wake it.
- The free database expires after 30 days (then deleted after a 14-day grace period).
- Uploaded evidence files are lost whenever the app restarts or redeploys (no persistent disk on free).
- Emails are not sent; invitation links are shown on screen after you invite someone.

## Steps
1. Create a free GitHub account and a new **private** repository, e.g. `eudr-gateway`.
2. Push this folder to it:
   ```bash
   cd eudr-gateway
   git init && git add . && git commit -m "Stage 1"
   git branch -M main
   git remote add origin https://github.com/<you>/eudr-gateway.git
   git push -u origin main
   ```
3. Sign up at render.com (log in with GitHub).
4. In Render: **New → Blueprint**, pick the repository. Render reads `render.yaml` and proposes a web service
   and a database.
5. It asks for three values:
   - `SZ_ADMIN_EMAIL`: your email
   - `SZ_ADMIN_NAME`: your name
   - `SZ_ADMIN_PASSWORD`: at least 12 characters, not a common password
6. Click **Apply**. The first build takes roughly 5–10 minutes. When the service shows **Live**, open its URL and
   sign in with the email and password from step 5.

After signing in, you can delete `SZ_ADMIN_PASSWORD` from the service's Environment settings; it is only used
when no admin exists yet.

## Updating
Every `git push` to `main` redeploys automatically.

## If something fails
Open the service → **Logs**. Common causes:
- "SZ_ADMIN_PASSWORD rejected": choose a longer / less common password, save, and redeploy.
- Build out of memory or timeout: click **Manual Deploy → Clear build cache & deploy**.
