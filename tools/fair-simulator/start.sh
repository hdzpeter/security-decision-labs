#!/bin/bash

# FAIR Risk Quantification Tool - Quick Start Script
# Starts risk_service (FastAPI) + frontend (Vite)

set -e

echo "Starting FAIR Risk Quantification Tool..."
echo ""

# --- FRONTEND DEPENDENCIES -------------------------------------------------

if [ ! -d "node_modules" ]; then
  echo "First-time setup detected - installing frontend dependencies..."
  npm install
  echo ""
fi

# --- BACKEND DEPENDENCIES --------------------------------------------------

if [ ! -d "backend/.venv" ]; then
  echo "Creating backend virtual environment and installing dependencies..."
  cd risk_service
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -r requirements.txt
  deactivate
  cd ..
  echo ""
fi

echo "Dependencies ready!"
echo ""
echo "Starting services..."
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop both services"
echo ""

# --- START BACKEND ---------------------------------------------------------

cd risk_service
# shellcheck disable=SC1091
source .venv/bin/activate

# Option 1: use fair_risk_engine.py
python fair_risk_engine.py &
BACKEND_PID=$!

cd ..

# Give risk_service a moment to start
sleep 2

# --- START FRONTEND --------------------------------------------------------

# Vite dev server (npm start -> vite)
npm start &
FRONTEND_PID=$!

# --- OPTIONAL: OPEN BROWSER ------------------------------------------------

# Try to open browser automatically if possible
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://localhost:5173" >/dev/null 2>&1 || true
elif [[ "$OSTYPE" == "darwin"* ]]; then
  open "http://localhost:5173" >/dev/null 2>&1 || true
fi

# --- WAIT FOR BOTH PROCESSES ----------------------------------------------

wait $BACKEND_PID $FRONTEND_PID