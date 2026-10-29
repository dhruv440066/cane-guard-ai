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
if [ -f "backend/models/model.keras" ]; then
    echo "Model file found: backend/models/model.keras"
else
    echo "WARNING: backend/models/model.keras not found."
fi

echo "=========================================="
echo " Build Completed Successfully!"
echo "=========================================="
