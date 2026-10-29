#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "=========================================="
echo " CaneGuard AI - Render Build Process"
echo "=========================================="

echo ">>> 1. Building React Frontend..."
cd frontend
npm install
npm run build
cd ..

echo ">>> 2. Installing Backend Dependencies..."
python -m pip install --upgrade pip
pip install -r backend/requirements.txt

echo ">>> 3. Checking ML Model artifacts..."
if [ -f "backend/models/model.tflite" ]; then
    echo "✓ TFLite model found: backend/models/model.tflite"
elif [ -f "backend/models/model.keras" ]; then
    echo "✓ Keras model found: backend/models/model.keras"
else
    echo "WARNING: No model artifact found in backend/models/."
fi

echo "=========================================="
echo " Build Completed Successfully!"
echo "=========================================="
