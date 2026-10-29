import os, io, json, sqlite3, secrets, hashlib, uuid
from pathlib import Path
import numpy as np, cv2
from PIL import Image
from fastapi import FastAPI, UploadFile, File, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
PROJECT_ROOT = ROOT.parent

DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT)))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB = Path(os.getenv("DB_PATH", str(DATA_DIR / "caneguard.db")))
UP = Path(os.getenv("UPLOAD_DIR", str(DATA_DIR / "uploads")))
UP.mkdir(parents=True, exist_ok=True)

CONF_THRESHOLD = float(os.getenv("CONF_THRESHOLD", "0.70"))
MAX_BYTES = int(os.getenv("MAX_UPLOAD_MB", "8")) * 1024 * 1024
MIN_SIDE, MIN_BLUR, MIN_BRIGHT, MAX_BRIGHT = 128, 40.0, 40, 220
MIN_GREEN = float(os.getenv("MIN_GREEN_FRACTION", "0.15"))
ALLOWED = {"JPEG", "PNG", "WEBP"}
DISEASES = json.loads((BASE / "diseases.json").read_text())
MODEL_PATH, CLASSES_PATH = ROOT / "models/model.keras", ROOT / "models/class_names.json"

app = FastAPI(title="CaneGuard AI")

# Configure CORS
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

def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c
with db() as c:
    c.executescript("""create table if not exists users(id integer primary key,name text,email text unique,pw text,salt text,created_at text default current_timestamp);
    create table if not exists sessions(token text primary key,user_id integer);
    create table if not exists analyses(id integer primary key,user_id integer,filename text,image_path text,status text,prediction text,confidence real,reason text,created_at text default current_timestamp);""")

def hp(pw, salt): return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()
class Cred(BaseModel): email: str; password: str; name: str = ""

def user(authorization: str = Header(None)):
    t = (authorization or "").replace("Bearer ", "")
    r = db().execute("select u.* from users u join sessions s on s.user_id=u.id where token=?", (t,)).fetchone()
    if not r: raise HTTPException(401, "Please log in.")
    return r

@app.get("/health")
def health():
    return {"status": "healthy", "service": "CaneGuard AI", "model_loaded": MODEL_PATH.exists()}

@app.post("/api/auth/register")
def register(c: Cred):
    if len(c.password) < 8: raise HTTPException(400, "Password must be at least 8 characters.")
    salt = secrets.token_hex(8)
    try:
        with db() as d: d.execute("insert into users(name,email,pw,salt) values(?,?,?,?)", (c.name, c.email.lower(), hp(c.password, salt), salt))
    except sqlite3.IntegrityError: raise HTTPException(400, "Email already registered.")
    return login(c)

@app.post("/api/auth/login")
def login(c: Cred):
    d = db(); u = d.execute("select * from users where email=?", (c.email.lower(),)).fetchone()
    if not u or not secrets.compare_digest(u["pw"], hp(c.password, u["salt"])): raise HTTPException(401, "Invalid email or password.")
    t = secrets.token_urlsafe(32); d.execute("insert into sessions values(?,?)", (t, u["id"])); d.commit()
    return {"token": t, "name": u["name"]}

@app.get("/api/auth/me")
def me(u=Depends(user)): return {"name": u["name"], "email": u["email"], "created_at": u["created_at"]}

_model = None; _classes = None
def get_model():
    global _model, _classes
    if _model is None:
        if not MODEL_PATH.exists() or not CLASSES_PATH.exists(): return None, None
        import tensorflow as tf
        _model = tf.keras.models.load_model(MODEL_PATH); _classes = json.loads(CLASSES_PATH.read_text())
    return _model, _classes

def validate(img: np.ndarray):
    """Quality + relevance heuristics. Relevance is a green-pixel check, NOT a trained sugarcane detector."""
    h, w = img.shape[:2]
    if min(h, w) < MIN_SIDE: return "low_quality", "Image resolution is too low."
    g = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    if not MIN_BRIGHT < g.mean() < MAX_BRIGHT: return "low_quality", "Image is too dark or too bright."
    if cv2.Laplacian(g, cv2.CV_64F).var() < MIN_BLUR: return "low_quality", "Image is too blurry."
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    veg = ((hsv[..., 0] > 20) & (hsv[..., 0] < 95) & (hsv[..., 1] > 40)).mean()
    if veg < MIN_GREEN: return "not_relevant", "This does not appear to be a suitable sugarcane leaf image."
    return None, None

def analyze_bytes(name: str, data: bytes, uid: int):
    out = {"filename": name}
    def fin(status, **kw):
        out.update(status=status, **kw)
        path = UP / f"{uuid.uuid4().hex}.jpg"
        try: Image.open(io.BytesIO(data)).convert("RGB").save(path)
        except Exception: path = ""
        with db() as d: d.execute("insert into analyses(user_id,filename,image_path,status,prediction,confidence,reason) values(?,?,?,?,?,?,?)",
            (uid, name, str(path), status, out.get("prediction"), out.get("confidence"), out.get("reason")))
        return out
    if len(data) > MAX_BYTES: return {**out, "status": "rejected", "reason": "too_large", "message": "Image exceeds the maximum allowed size."}
    try:
        im = Image.open(io.BytesIO(data)); fmt = im.format; im.load()
    except Exception: return {**out, "status": "rejected", "reason": "corrupted", "message": "This image could not be read."}
    if fmt not in ALLOWED: return {**out, "status": "rejected", "reason": "unsupported", "message": "This file format is not supported."}
    arr = np.array(im.convert("RGB"))
    reason, msg = validate(arr)
    if reason: return fin("rejected", reason=reason, message=msg)
    model, classes = get_model()
    if model is None: raise HTTPException(503, "Model not found. Train it first (see README) so models/model.keras exists.")
    size = model.input_shape[1:3]
    x = cv2.resize(arr, (size[1], size[0])).astype("float32")[None]
    p = model.predict(x, verbose=0)[0]; i = int(p.argmax()); conf = float(p[i])
    if conf < CONF_THRESHOLD: return fin("uncertain", reason="low_confidence", confidence=conf, message="The model could not make a reliable prediction.")
    cls = classes[i]
    return fin("success", prediction=cls, confidence=conf, info=DISEASES.get(cls, {"description": "Information not available for this class."}))

@app.post("/api/analyze/batch")
async def batch(files: list[UploadFile] = File(...), u=Depends(user)):
    if len(files) > 20: raise HTTPException(400, "Maximum 20 images per request.")
    try:
        return [analyze_bytes(Path(f.filename or "image").name, await f.read(), u["id"]) for f in files]
    except HTTPException: raise
    except Exception: raise HTTPException(500, "Something went wrong while analyzing the image. Please try again.")

@app.post("/api/analyze")
async def single(file: UploadFile = File(...), u=Depends(user)): return (await batch([file], u))[0]

@app.get("/api/analyses")
def history(u=Depends(user)):
    return [dict(r) for r in db().execute("select id,filename,status,prediction,confidence,reason,created_at from analyses where user_id=? order by id desc", (u["id"],))]

@app.get("/api/diseases")
def diseases():
    _, cls = get_model(); return {k: DISEASES.get(k, {}) for k in (cls or DISEASES.keys())}

@app.get("/api/model/info")
def info():
    m, c = get_model()
    return {"loaded": m is not None, "classes": c, "input_shape": m.input_shape if m else None, "confidence_threshold": CONF_THRESHOLD,
            "metrics": json.loads((ROOT / "models/metrics.json").read_text()) if (ROOT / "models/metrics.json").exists() else "Not available"}

# Static Frontend mounting (if built)
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
    def serve_index():
        return FileResponse(DIST_DIR / "index.html")

    @app.get("/{full_path:path}")
    async def serve_spa_or_static(full_path: str):
        if full_path.startswith("api/") or full_path in {"docs", "redoc", "openapi.json", "health"}:
            raise HTTPException(404, "Endpoint not found")
        static_file = DIST_DIR / full_path
        if full_path and static_file.is_file():
            return FileResponse(static_file)
        return FileResponse(DIST_DIR / "index.html")
else:
    @app.get("/")
    def root():
        return {"app": "CaneGuard AI", "docs": "/docs", "model_loaded": MODEL_PATH.exists()}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
