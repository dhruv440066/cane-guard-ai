# CaneGuard AI – Sugarcane Disease Detection (CNN)

CaneGuard AI is an end-to-end full-stack web application designed for sugarcane leaf disease detection. It uses a MobileNetV2 Convolutional Neural Network (CNN) with image quality and relevance heuristics, a FastAPI backend, and a React (Vite) frontend.

---

## Live Deployment on Render

This project is configured for **1-click automated deployment to Render**:

- **Blueprint File**: [`render.yaml`](render.yaml)
- **Automated Build Script**: [`build.sh`](build.sh)
- **Container Deployment**: [`Dockerfile`](Dockerfile)
- **Full Guide**: See [`DEPLOYMENT.md`](DEPLOYMENT.md) for step-by-step instructions.

### Quick Deploy:
1. Push this repository to GitHub / GitLab.
2. In Render, select **New +** -> **Blueprint**, and connect this repository.
3. Render automatically provisions the web service, builds the React UI, installs Python requirements, and launches the app!

---

## Local Development Setup

### 1. Backend (FastAPI)
```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
API Documentation will be available at [http://localhost:8000/docs](http://localhost:8000/docs).

### 2. Frontend (React + Vite)
```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173). Requests to `/api` are automatically proxied to the backend.

### 3. Model Training (Optional)
To train or fine-tune MobileNetV2 with the Kaggle sugarcane diseases dataset:
```bash
python ml/train.py --download
```
This updates `backend/models/model.keras`, `class_names.json`, and `metrics.json`.

---

## How Prediction Works

```
Image Upload -> Quality Checks (Resolution, Blur, Brightness) -> Relevance Check (Green Hue) -> MobileNetV2 CNN -> Confidence Threshold (default 0.70) -> Disease Result & Management Advice
```

---

## Limitations

- **Relevance Check**: Uses a green-vegetation HSV heuristic rather than a full plant detector. Non-sugarcane green leaves may pass the check.
- **Disease Information**: Information in `backend/app/diseases.json` provides general agricultural guidance; verify with local agricultural officers before field treatments. No pesticide dosages are prescribed.
