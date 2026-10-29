import io
import sys
from pathlib import Path
import pytest
import numpy as np
from PIL import Image

# Ensure backend package is in python path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient
from app.main import app, DISEASES

client = TestClient(app)

def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "CaneGuard AI"
    assert data["model_loaded"] is True
    assert data["inference_engine"] in ("tflite", "keras")

def test_diseases():
    res = client.get("/api/diseases")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 6
    assert "Healthy" in data
    assert "RedRot" in data
    assert "Rust" in data
    assert "Mosaic" in data
    assert "Yellow" in data
    assert "BacterialBlight" in data

def test_model_info():
    res = client.get("/api/model/info")
    assert res.status_code == 200
    data = res.json()
    assert data["loaded"] is True
    assert len(data["classes"]) == 6
    assert data["confidence_threshold"] == 0.50

def test_samples():
    res = client.get("/api/samples")
    assert res.status_code == 200
    samples = res.json()
    assert len(samples) >= 4
    for s in samples:
        img_res = client.get(s["url"])
        assert img_res.status_code == 200
        assert "image/jpeg" in img_res.headers["content-type"]

def test_auth_and_me():
    email = "test_farmer_qa@example.com"
    pwd = "password12345"
    reg_res = client.post("/api/auth/register", json={"name": "QA Farmer", "email": email, "password": pwd})
    assert reg_res.status_code in (200, 400)
    
    login_res = client.post("/api/auth/login", json={"email": email, "password": pwd})
    assert login_res.status_code == 200
    token = login_res.json()["token"]
    assert token

    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["email"] == email

def test_guest_image_analysis():
    # Generate synthetic green textured leaf
    img = np.full((224, 224, 3), (45, 130, 50), dtype=np.uint8)
    noise = np.random.randint(-15, 15, (224, 224, 3))
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="JPEG")
    buf.seek(0)

    # Guest call without auth token
    res = client.post("/api/analyze", files={"file": ("guest_leaf.jpg", buf, "image/jpeg")})
    assert res.status_code == 200
    data = res.json()
    assert data["filename"] == "guest_leaf.jpg"
    assert data["status"] in ("success", "uncertain")
    assert "top_predictions" in data
    assert len(data["top_predictions"]) >= 1

def test_stalk_image_analysis():
    # Sample 2: Red Rot Stalk (tan cane + red internal rot)
    img = np.full((224, 224, 3), (210, 195, 165), dtype=np.uint8)
    img[:, 95:135] = (175, 40, 35) # Red rot core
    
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="JPEG")
    buf.seek(0)

    res = client.post("/api/analyze", files={"file": ("red_rot_stalk.jpg", buf, "image/jpeg")})
    assert res.status_code == 200
    data = res.json()
    # Must NOT be rejected as non-plant
    assert data["status"] != "rejected"
    assert "confidence" in data

def test_rejected_blurry_image():
    # Solid black image has 0 variance (blurry) and low brightness
    solid = np.zeros((150, 150, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(solid).save(buf, format="JPEG")
    buf.seek(0)

    res = client.post("/api/analyze", files={"file": ("dark_blurry.jpg", buf, "image/jpeg")})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "rejected"
