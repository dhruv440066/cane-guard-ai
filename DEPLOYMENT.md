# Deploying CaneGuard AI to Render

This repository is **100% Render ready**. You can deploy it using any of the methods below.

---

## Deployment Options at a Glance

| Deployment Method | Best For | Complexity | Free Tier Compatible |
| :--- | :--- | :--- | :--- |
| **Option 1: Render Blueprint (`render.yaml`)** *(Recommended)* | 1-Click automated full-stack setup | Lowest | Yes (1 Web Service) |
| **Option 2: Manual Web Service (Unified Full-Stack)** | Full UI control in Render Dashboard | Low | Yes (1 Web Service) |
| **Option 3: Docker Runtime** | Exact container reproducibility | Low | Yes (1 Web Service) |
| **Option 4: Split Services (Static Site + Web Service)** | Separating CDN frontend from backend | Medium | Yes (1 Static Site + 1 Web Service) |

---

## Prerequisites

1. A [Render account](https://render.com) (free).
2. A [GitHub](https://github.com) or [GitLab](https://gitlab.com) account.
3. Push this project to your repository:
   ```bash
   git add .
   git commit -m "feat: render deployment ready"
   git branch -M main
   git remote add origin https://github.com/<your-username>/cane-guard-ai.git
   git push -u origin main
   ```

---

## Option 1: 1-Click Deploy via Render Blueprint (Recommended)

Render uses the included [`render.yaml`](render.yaml) to automatically configure everything:

1. Log in to [dashboard.render.com](https://dashboard.render.com).
2. Click **New +** in the top navigation bar and select **Blueprint**.
3. Connect your Git repository (`cane-guard-ai`).
4. Render will detect `render.yaml` and show:
   - **Service Name**: `cane-guard-ai`
   - **Runtime**: `Python`
   - **Build Command**: `bash build.sh`
   - **Start Command**: `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: `Free`
5. Click **Apply**.
6. Render will automatically build the React frontend, install backend dependencies, and launch the service!

---

## Option 2: Manual Web Service Deployment (Unified Full-Stack)

If you prefer setting up the web service manually in the Render dashboard:

1. In Render Dashboard, click **New +** -> **Web Service**.
2. Select **Build and deploy from a Git repository** and pick your repo.
3. Fill in the service configuration:
   - **Name**: `cane-guard-ai` (or your preferred name)
   - **Region**: Choose the region closest to you (e.g., *Oregon (US West)* or *Frankfurt (EU)*)
   - **Branch**: `main`
   - **Root Directory**: *(leave blank)*
   - **Runtime**: `Python`
   - **Build Command**:
     ```bash
     bash build.sh
     ```
   - **Start Command**:
     ```bash
     uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
     ```
   - **Instance Type**: `Free`
4. Expand **Advanced** -> **Add Environment Variable**:
   | Key | Value | Purpose |
   | :--- | :--- | :--- |
   | `PYTHON_VERSION` | `3.11.9` | Ensures TensorFlow compatibility |
   | `NODE_VERSION` | `20.18.0` | Node version for building React frontend |
   | `CONF_THRESHOLD` | `0.70` | Model confidence threshold |
   | `MAX_UPLOAD_MB` | `8` | Maximum upload size in MB |
   | `CORS` | `*` | Allowed CORS origins |
5. Set **Health Check Path** to:
   ```
   /health
   ```
6. Click **Create Web Service**.

---

## Option 3: Deploy via Docker

Render natively builds and runs Docker containers:

1. Click **New +** -> **Web Service**.
2. Select your repository.
3. Set **Runtime** to `Docker`.
4. Render will automatically detect the root [`Dockerfile`](Dockerfile).
5. Set **Instance Type** to `Free`.
6. Add environment variables if desired (e.g. `CONF_THRESHOLD=0.70`).
7. Click **Create Web Service**.

---

## Option 4: Split Services (Static Site + Backend Web Service)

If you prefer hosting the React frontend on Render's CDN Static Site and the backend on a Web Service:

### 1. Deploy Backend Web Service:
- **Runtime**: `Python`
- **Root Directory**: `backend`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Env Vars**:
  - `PYTHON_VERSION`: `3.11.9`
  - `CORS`: `*` (or your static site's domain)
- Note the resulting backend URL (e.g., `https://cane-guard-backend.onrender.com`).

### 2. Deploy Frontend Static Site:
- Click **New +** -> **Static Site**.
- **Root Directory**: `frontend`
- **Build Command**: `npm install && npm run build`
- **Publish Directory**: `dist`
- **Env Vars**:
  - `VITE_API_URL`: `https://cane-guard-backend.onrender.com` (your backend URL)

---

## Verification & Testing

Once deployment completes and Render shows **Live**:

1. **Health Check**:
   Open `https://<your-subdomain>.onrender.com/health` in your browser.
   Expected response:
   ```json
   {
     "status": "healthy",
     "service": "CaneGuard AI",
     "model_loaded": true
   }
   ```

2. **Web Application**:
   Open `https://<your-subdomain>.onrender.com` to see the CaneGuard AI user interface.

3. **Interactive API Documentation**:
   Open `https://<your-subdomain>.onrender.com/docs` to test endpoints via Swagger UI.

4. **Leaf Analysis**:
   - Create an account or log in.
   - Upload or snap a picture of a sugarcane leaf.
   - Click **Analyze image(s)** to run validation and model classification.

---

## Environment Variables Reference

| Variable | Default | Description |
| :--- | :--- | :--- |
| `PORT` | `8000` | Port assigned by Render automatically. |
| `PYTHON_VERSION` | `3.11.9` | Python runtime version. |
| `NODE_VERSION` | `20.18.0` | Node runtime version for frontend build. |
| `CONF_THRESHOLD` | `0.70` | Confidence cutoff below which result is marked "uncertain". |
| `MAX_UPLOAD_MB` | `8` | Maximum image size in Megabytes. |
| `MIN_GREEN_FRACTION`| `0.15` | Minimum ratio of green pixels required for leaf relevance. |
| `CORS` | `*` | Comma-separated allowed origins or `*` for all. |
| `DATA_DIR` | *(backend dir)* | Path to directory for SQLite database and uploads. Useful when mounting a Render Persistent Disk. |
| `VITE_API_URL` | `""` | Backend base URL (only required if frontend is deployed as a separate static site). |

---

## Pro Tips for Render Free Tier

- **Cold Starts**: Render free services spin down after 15 minutes of inactivity. The first request after sleep may take ~30-50 seconds to wake up.
- **Uptime Monitoring**: To keep the service responsive without manual wake-ups, you can set up a free uptime monitor (e.g. [UptimeRobot](https://uptimerobot.com) or [Cron-Job.org](https://cron-job.org)) that pings `https://<your-subdomain>.onrender.com/health` every 10-14 minutes.
