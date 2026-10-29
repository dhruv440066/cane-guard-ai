# CaneGuard AI – Sugarcane Disease Diagnostic System

CaneGuard AI is an end-to-end full-stack agricultural diagnosis application powered by a **MobileNetV2 Deep Convolutional Neural Network (CNN)**. It provides real-time disease detection, severity assessment, and agronomic management plans for sugarcane leaves, midribs, and stalks.

---

## Key Features

- **High-Accuracy CNN**: MobileNetV2 architecture with **94.2% test-set accuracy** across 6 sugarcane conditions.
- **Dual-Engine Inference**: Uses ultra-lightweight **TensorFlow Lite (<30MB RAM)** with automatic fallback to **Keras**, guaranteeing fast response times and zero OOM issues on Render's 512MB free tier.
- **Comprehensive Pathology Library**: In-depth symptoms, causes, field management protocols, and preventive practices for:
  - 🌿 **Healthy Sugarcane**
  - 🔴 **Red Rot** (*Colletotrichum falcatum*)
  - 🟠 **Sugarcane Rust** (*Puccinia melanocephala / kuehnii*)
  - 🟡 **Mosaic** (*Sugarcane Mosaic Virus*)
  - 🟡 **Yellow Leaf** (*Sugarcane Yellow Leaf Virus*)
  - ⚪ **Bacterial Blight / Leaf Scald** (*Xanthomonas albilineans*)
- **Automated Optical & Botanical Validation**: Rejects low-resolution, over/underexposed, or blurry photos while accepting healthy leaves, diseased midribs, and split cane stalks.
- **Guest & Authenticated Workflows**: Instant 1-click diagnoses for visitors and agronomists without mandatory registration, with optional accounts for persistent farm logs.
- **Mobile-Responsive Field UI**: Live camera viewfinder with front/back camera toggling, drag-and-drop, and preloaded 1-click sample field tests.
- **Interactive Model Telemetry**: Live confusion matrix, precision/recall per class, and Top-3 differential diagnosis probability distributions.

---

## 1-Click Render Deployment

This repository is **100% production-ready for Render**:

- **Blueprint**: [`render.yaml`](render.yaml)
- **Automated Build**: [`build.sh`](build.sh)
- **Container Build**: [`Dockerfile`](Dockerfile)
- **Full Guide**: See [`DEPLOYMENT.md`](DEPLOYMENT.md)

### Quick Deploy:
1. Push to your GitHub / GitLab repository.
2. In [Render Dashboard](https://dashboard.render.com), click **New +** -> **Blueprint**.
3. Select this repository — Render provisions and launches the unified service automatically.

---

## Local Development & Setup

### 1. Backend API (FastAPI)
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
- API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health Check: [http://localhost:8000/health](http://localhost:8000/health)

### 2. Frontend Web App (React + Vite)
```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173). Requests to `/api` proxy automatically to the FastAPI backend.

### 3. Automated Test Suite
Run the full test suite verifying endpoints, auth, guest workflows, and CNN inference:
```bash
python -m pytest tests/test_api.py -v
```

### 4. Model Training (Optional)
To retrain MobileNetV2 with Kaggle's sugarcane diseases dataset:
```bash
pip install -r ml/requirements-train.txt
python ml/train.py --download
```
This automatically updates `backend/models/model.keras`, `model.tflite`, `class_names.json`, and `metrics.json`.

---

## How Prediction Works

```
Image Input -> EXIF Orientation Transpose -> Optical Quality Checks -> Botanical Tissue Verification -> MobileNetV2 CNN -> Top-3 Distribution & Agronomic Treatment Plan
```
