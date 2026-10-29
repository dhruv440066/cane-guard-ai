import os, io, json, sqlite3, secrets, hashlib, uuid
from pathlib import Path
from typing import Optional, List, Dict, Any

import numpy as np
import cv2
from PIL import Image, ImageOps

from fastapi import FastAPI, UploadFile, File, HTTPException, Header, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
PROJECT_ROOT = ROOT.parent

# Persistent directories
DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT)))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.getenv("DB_PATH", str(DATA_DIR / "caneguard.db")))
UP_DIR = Path(os.getenv("UPLOAD_DIR", str(DATA_DIR / "uploads")))
UP_DIR.mkdir(parents=True, exist_ok=True)

# Configuration thresholds
CONF_THRESHOLD = float(os.getenv("CONF_THRESHOLD", "0.50"))
MAX_BYTES = int(os.getenv("MAX_UPLOAD_MB", "8")) * 1024 * 1024
MIN_SIDE = int(os.getenv("MIN_SIDE", "128"))
MIN_BLUR = float(os.getenv("MIN_BLUR", "35.0"))
MIN_BRIGHT = int(os.getenv("MIN_BRIGHT", "35"))
MAX_BRIGHT = int(os.getenv("MAX_BRIGHT", "225"))
MIN_PLANT = float(os.getenv("MIN_PLANT_FRACTION", "0.04"))
ENABLE_RELEVANCE = os.getenv("ENABLE_RELEVANCE_CHECK", "true").lower() in ("true", "1", "yes")
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "MPO"}

DISEASES_PATH = BASE / "diseases.json"
DISEASES: Dict[str, Any] = json.loads(DISEASES_PATH.read_text(encoding="utf-8"))

MODEL_TFLITE_PATH = ROOT / "models/model.tflite"
MODEL_KERAS_PATH = ROOT / "models/model.keras"
CLASSES_PATH = ROOT / "models/class_names.json"
METRICS_PATH = ROOT / "models/metrics.json"

app = FastAPI(
    title="CaneGuard AI - Sugarcane Disease Prediction System",
    description="Production-grade AI API for sugarcane disease detection using MobileNetV2 Deep CNN and agronomic diagnostics.",
    version="1.1.0",
)

# CORS configuration
cors_raw = os.getenv("CORS", "*").strip()
if cors_raw == "*":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    origins = [o.strip() for o in cors_raw.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

def db() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=10.0)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode = WAL;")
    c.execute("PRAGMA busy_timeout = 5000;")
    return c

# Database initialization & migrations
with db() as conn:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            pw TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NULL,
            filename TEXT NOT NULL,
            image_path TEXT NOT NULL,
            status TEXT NOT NULL,
            prediction TEXT,
            confidence REAL,
            top_predictions TEXT,
            reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # Automatic column migration if needed
    try:
        conn.execute("ALTER TABLE analyses ADD COLUMN top_predictions TEXT;")
    except sqlite3.OperationalError:
        pass

def hash_pw(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000).hex()

class CredentialPayload(BaseModel):
    email: str
    password: str
    name: Optional[str] = ""

def get_optional_user(authorization: Optional[str] = Header(None)) -> Optional[sqlite3.Row]:
    if not authorization:
        return None
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        return None
    with db() as conn:
        return conn.execute(
            "SELECT u.* FROM users u JOIN sessions s ON s.user_id = u.id WHERE s.token = ?",
            (token,),
        ).fetchone()

def get_required_user(authorization: Optional[str] = Header(None)) -> sqlite3.Row:
    u = get_optional_user(authorization)
    if not u:
        raise HTTPException(401, "Authentication required. Please log in.")
    return u

# Model Inference Engine (TFLite with Keras fallback)
_tflite_interpreter = None
_keras_model = None
_classes_cache = None
_inference_engine_name = "none"

def load_engine():
    global _tflite_interpreter, _keras_model, _classes_cache, _inference_engine_name
    if _classes_cache is None and CLASSES_PATH.exists():
        _classes_cache = json.loads(CLASSES_PATH.read_text(encoding="utf-8"))

    # Prefer lightweight TFLite (<30MB RAM)
    if _tflite_interpreter is None and MODEL_TFLITE_PATH.exists():
        try:
            import tensorflow as tf
            interp = tf.lite.Interpreter(model_path=str(MODEL_TFLITE_PATH))
            interp.allocate_tensors()
            _tflite_interpreter = interp
            _inference_engine_name = "tflite"
            return
        except Exception as ex:
            print(f"[Engine] TFLite initialization failed, falling back to Keras: {ex}")

    # Fallback to Keras model if TFLite is unavailable
    if _keras_model is None and MODEL_KERAS_PATH.exists():
        try:
            import tensorflow as tf
            _keras_model = tf.keras.models.load_model(str(MODEL_KERAS_PATH))
            _inference_engine_name = "keras"
            return
        except Exception as ex:
            print(f"[Engine] Keras initialization failed: {ex}")

def run_cnn_inference(img_rgb: np.ndarray) -> tuple[int, float, List[float]]:
    """Runs inference on a 224x224 RGB image and returns (best_index, best_confidence, all_probabilities)."""
    load_engine()
    target_size = (224, 224)
    resized = cv2.resize(img_rgb, target_size)
    # MobileNetV2 preprocessing: scale to [-1, 1]
    normalized = (resized.astype(np.float32) / 127.5) - 1.0

    if _tflite_interpreter is not None:
        input_details = _tflite_interpreter.get_input_details()
        output_details = _tflite_interpreter.get_output_details()
        batch_input = np.expand_dims(normalized, axis=0)
        _tflite_interpreter.set_tensor(input_details[0]["index"], batch_input)
        _tflite_interpreter.invoke()
        output = _tflite_interpreter.get_tensor(output_details[0]["index"])[0]
    elif _keras_model is not None:
        batch_input = np.expand_dims(normalized, axis=0)
        output = _keras_model.predict(batch_input, verbose=0)[0]
    else:
        raise HTTPException(503, "Neural network model artifact not found. Please train or verify models directory.")

    probs = [float(p) for p in output]
    best_idx = int(np.argmax(probs))
    best_conf = float(probs[best_idx])
    return best_idx, best_conf, probs

def validate_image_heuristics(img: np.ndarray) -> tuple[Optional[str], Optional[str]]:
    """Quality and agricultural tissue heuristics."""
    h, w = img.shape[:2]
    if min(h, w) < MIN_SIDE:
        return "low_resolution", f"Image resolution ({w}x{h}) is too low. Minimum required is {MIN_SIDE}x{MIN_SIDE}px."

    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    mean_bright = float(gray.mean())
    if mean_bright < MIN_BRIGHT:
        return "under_exposed", "Image is too dark or poorly lit. Please provide a well-lit leaf photograph."
    if mean_bright > MAX_BRIGHT:
        return "over_exposed", "Image is overexposed or has excessive glare. Please avoid direct sunlight flash."

    blur_variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if blur_variance < MIN_BLUR:
        return "too_blurry", f"Image appears blurry (clarity score: {blur_variance:.1f} < {MIN_BLUR}). Hold camera steady and refocus."

    if ENABLE_RELEVANCE and MIN_PLANT > 0:
        hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
        # 1. Green foliage
        green = (hsv[..., 0] >= 20) & (hsv[..., 0] <= 95) & (hsv[..., 1] > 30)
        # 2. Sugarcane stalks, dry cane fiber & chlorosis (yellow/tan/cream)
        cane_tan = (hsv[..., 0] >= 10) & (hsv[..., 0] < 25) & (hsv[..., 1] > 15)
        # 3. Disease lesions (Red Rot red/maroon, rust pustules, brown necrotic margins)
        disease_tones = ((hsv[..., 0] < 12) | (hsv[..., 0] > 165)) & (hsv[..., 1] > 25) & (hsv[..., 2] > 30)

        plant_fraction = float((green | cane_tan | disease_tones).mean())
        if plant_fraction < MIN_PLANT:
            return "not_relevant", f"Image contains insufficient plant or sugarcane symptom tissue ({plant_fraction*100:.1f}% detected). Please photograph a sugarcane leaf, midrib, or stalk."

    return None, None

def process_image_bytes(name: str, data: bytes, uid: Optional[int]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"filename": name}

    def record_result(status: str, **kwargs) -> Dict[str, Any]:
        out.update(status=status, **kwargs)
        stored_path = ""
        try:
            stored_path = str(UP_DIR / f"{uuid.uuid4().hex}.jpg")
            with open(stored_path, "wb") as f:
                f.write(data)
        except Exception:
            stored_path = ""

        top_preds_json = json.dumps(out.get("top_predictions", []))
        try:
            with db() as conn:
                conn.execute(
                    """INSERT INTO analyses (user_id, filename, image_path, status, prediction, confidence, top_predictions, reason)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        uid,
                        name,
                        stored_path,
                        status,
                        out.get("prediction"),
                        out.get("confidence"),
                        top_preds_json,
                        out.get("reason"),
                    ),
                )
                conn.commit()
        except Exception as e:
            print(f"[DB Error] Could not record analysis: {e}")

        return out

    # File size validation
    if len(data) > MAX_BYTES:
        return {
            **out,
            "status": "rejected",
            "reason": "file_too_large",
            "message": f"Image exceeds maximum permitted size of {MAX_BYTES // (1024*1024)} MB.",
        }

    # Format and corruption validation
    try:
        raw_im = Image.open(io.BytesIO(data))
        raw_im.load()
        fmt = raw_im.format
        if fmt not in ALLOWED_FORMATS:
            return {
                **out,
                "status": "rejected",
                "reason": "unsupported_format",
                "message": f"Format '{fmt}' is not supported. Please upload JPEG, PNG, or WebP images.",
            }
        # EXIF orientation correction for mobile cameras
        im = ImageOps.exif_transpose(raw_im).convert("RGB")
    except Exception:
        return {
            **out,
            "status": "rejected",
            "reason": "corrupted_file",
            "message": "File could not be parsed as a valid image. It may be corrupted.",
        }

    arr = np.array(im)
    reason, msg = validate_image_heuristics(arr)
    if reason:
        return record_result("rejected", reason=reason, message=msg)

    # Run inference
    load_engine()
    if _classes_cache is None:
        raise HTTPException(503, "Class names configuration missing. Ensure backend/models/class_names.json exists.")

    best_idx, best_conf, probs = run_cnn_inference(arr)
    classes = _classes_cache

    # Build Top-3 probabilities distribution
    sorted_indices = np.argsort(probs)[::-1]
    top_predictions = [
        {
            "class": classes[idx],
            "name": DISEASES.get(classes[idx], {}).get("name", classes[idx]),
            "pathogen": DISEASES.get(classes[idx], {}).get("pathogen", ""),
            "confidence": round(float(probs[idx]), 4),
            "percentage": round(float(probs[idx]) * 100, 1),
        }
        for idx in sorted_indices[:3]
    ]

    predicted_class = classes[best_idx]
    disease_info = DISEASES.get(predicted_class, {
        "name": predicted_class,
        "pathogen": "Unknown Pathogen",
        "description": "Diagnostic information currently unavailable for this category.",
        "symptoms": [],
        "causes": [],
        "management": ["Consult a local agricultural officer."],
        "prevention": ["Use certified disease-free planting material."],
        "when_to_seek_help": "Seek expert extension help for unverified symptoms."
    })

    if best_conf < CONF_THRESHOLD:
        return record_result(
            "uncertain",
            reason="low_confidence",
            confidence=best_conf,
            prediction=predicted_class,
            top_predictions=top_predictions,
            message=f"Model confidence ({best_conf*100:.1f}%) is below the diagnostic threshold ({CONF_THRESHOLD*100:.0f}%).",
            info=disease_info,
        )

    return record_result(
        "success",
        prediction=predicted_class,
        confidence=best_conf,
        top_predictions=top_predictions,
        info=disease_info,
    )

# ==============================================================================
# API Endpoints
# ==============================================================================

@app.get("/health")
def health_check():
    load_engine()
    return {
        "status": "healthy",
        "service": "CaneGuard AI",
        "version": "1.1.0",
        "inference_engine": _inference_engine_name,
        "model_loaded": _tflite_interpreter is not None or _keras_model is not None,
        "classes_count": len(_classes_cache) if _classes_cache else 0,
        "confidence_threshold": CONF_THRESHOLD,
    }

# Authentication
@app.post("/api/auth/register")
def register(c: CredentialPayload):
    if len(c.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters long.")
    salt = secrets.token_hex(16)
    name = (c.name or "").strip() or c.email.split("@")[0].title()
    try:
        with db() as conn:
            conn.execute(
                "INSERT INTO users (name, email, pw, salt) VALUES (?, ?, ?, ?)",
                (name, c.email.lower().strip(), hash_pw(c.password, salt), salt),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(400, "This email is already registered. Please log in.")
    return login(c)

@app.post("/api/auth/login")
def login(c: CredentialPayload):
    with db() as conn:
        u = conn.execute("SELECT * FROM users WHERE email = ?", (c.email.lower().strip(),)).fetchone()
    if not u or not secrets.compare_digest(u["pw"], hash_pw(c.password, u["salt"])):
        raise HTTPException(401, "Invalid email or password.")
    token = secrets.token_urlsafe(32)
    with db() as conn:
        conn.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, u["id"]))
        conn.commit()
    return {"token": token, "name": u["name"], "email": u["email"]}

@app.get("/api/auth/me")
def me(u: sqlite3.Row = Depends(get_required_user)):
    return {"name": u["name"], "email": u["email"], "created_at": u["created_at"]}

# Core Prediction Endpoints
@app.post("/api/analyze/batch")
async def analyze_batch(
    files: List[UploadFile] = File(...),
    u: Optional[sqlite3.Row] = Depends(get_optional_user),
):
    if len(files) == 0:
        raise HTTPException(400, "No files received for analysis.")
    if len(files) > 20:
        raise HTTPException(400, "Maximum 20 images per batch request.")

    uid = u["id"] if u else None
    results = []
    for f in files:
        data = await f.read()
        safe_name = Path(f.filename or "image.jpg").name
        results.append(process_image_bytes(safe_name, data, uid))
    return results

@app.post("/api/analyze")
async def analyze_single(
    file: UploadFile = File(...),
    u: Optional[sqlite3.Row] = Depends(get_optional_user),
):
    res = await analyze_batch([file], u)
    return res[0]

# History
@app.get("/api/analyses")
def get_analyses_history(
    u: Optional[sqlite3.Row] = Depends(get_optional_user),
    limit: int = Query(25, ge=1, le=100),
):
    with db() as conn:
        if u:
            rows = conn.execute(
                """SELECT id, filename, status, prediction, confidence, top_predictions, reason, created_at
                   FROM analyses WHERE user_id = ? ORDER BY id DESC LIMIT ?""",
                (u["id"], limit),
            ).fetchall()
        else:
            # Guest sees recent public analyses
            rows = conn.execute(
                """SELECT id, filename, status, prediction, confidence, top_predictions, reason, created_at
                   FROM analyses ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()

    items = []
    for r in rows:
        d = dict(r)
        if d.get("top_predictions"):
            try:
                d["top_predictions"] = json.loads(d["top_predictions"])
            except Exception:
                pass
        items.append(d)
    return items

# Disease Library & Model Info
@app.get("/api/samples")
def get_sample_images():
    samples_dir = BASE / "samples"
    if not samples_dir.exists():
        return []
    manifest = [
        {"id": "healthy", "title": "Healthy Sugarcane Leaf", "filename": "healthy_leaf.jpg", "url": "/api/samples/healthy_leaf.jpg"},
        {"id": "redrot", "title": "Red Rot Diseased Stalk", "filename": "red_rot_stalk.jpg", "url": "/api/samples/red_rot_stalk.jpg"},
        {"id": "rust", "title": "Sugarcane Rust Foliage", "filename": "rust_leaf.jpg", "url": "/api/samples/rust_leaf.jpg"},
        {"id": "yellow", "title": "Yellow Leaf Syndrome", "filename": "yellow_leaf.jpg", "url": "/api/samples/yellow_leaf.jpg"},
    ]
    return manifest

@app.get("/api/samples/{filename}")
def serve_sample_image(filename: str):
    path = BASE / "samples" / filename
    if not path.is_file():
        raise HTTPException(404, "Sample image not found.")
    return FileResponse(path, media_type="image/jpeg")

@app.get("/api/diseases")
def get_diseases():
    return DISEASES

@app.get("/api/model/info")
def get_model_info():
    load_engine()
    metrics = None
    if METRICS_PATH.exists():
        try:
            metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
        except Exception:
            metrics = "Metrics file present but unparseable."

    return {
        "loaded": _tflite_interpreter is not None or _keras_model is not None,
        "inference_engine": _inference_engine_name,
        "classes": _classes_cache or list(DISEASES.keys()),
        "input_shape": [1, 224, 224, 3],
        "confidence_threshold": CONF_THRESHOLD,
        "min_plant_fraction": MIN_PLANT,
        "relevance_heuristic_enabled": ENABLE_RELEVANCE,
        "metrics": metrics,
    }

# ==============================================================================
# Static Frontend Serving (Vite SPA)
# ==============================================================================

DIST_DIR = Path(os.getenv("FRONTEND_DIST", str(PROJECT_ROOT / "frontend" / "dist")))
if not DIST_DIR.exists():
    for candidate in [ROOT / "static", BASE / "static"]:
        if candidate.exists():
            DIST_DIR = candidate
            break

if DIST_DIR.exists() and (DIST_DIR / "index.html").exists():
    assets_dir = DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/")
    def serve_frontend_root():
        return FileResponse(DIST_DIR / "index.html")

    @app.get("/{full_path:path}")
    async def serve_spa_fallback(full_path: str):
        if full_path.startswith("api/") or full_path in {"docs", "redoc", "openapi.json", "health"}:
            raise HTTPException(404, "Endpoint not found")
        target_file = DIST_DIR / full_path
        if full_path and target_file.is_file():
            return FileResponse(target_file)
        return FileResponse(DIST_DIR / "index.html")
else:
    @app.get("/")
    def api_root():
        load_engine()
        return {
            "app": "CaneGuard AI - Sugarcane Disease Prediction System",
            "status": "online",
            "docs": "/docs",
            "health": "/health",
            "model_loaded": _tflite_interpreter is not None or _keras_model is not None,
            "inference_engine": _inference_engine_name,
        }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
