# FAIR Risk Quantification Tool – Detailed Setup Guide

This guide walks through a clean setup of the FAIR Risk Quantification Tool on a Unix-like system (macOS/Linux).

---

## 1. Clone and Initial Layout

From your desired workspace directory:

```bash
git clone <your-repo-url> fair-simulator
cd fair-simulator
```

You should now see a structure roughly like:

```text
risk_service/
docs/
src/
shared/
package.json
vite.config.ts
tsconfig.json
start.sh
...
```

---

## 2. Python Backend Setup

### 2.1. Create and Activate Virtual Environment

From the project root:

```bash
python -m venv .venv
source .venv/bin/activate
```

You should now see `(.venv)` in your shell prompt.

If `python` points to Python 2 on your system, use `python3` instead.

### 2.2. Install Backend Dependencies

```bash
cd risk_service
pip install -r requirements.txt
cd ..
```

This installs:

- FastAPI
- Uvicorn
- NumPy / SciPy
- Pydantic v2
- Other support libraries

### 2.3. Run the Backend

From `risk_service/`:

```bash
cd risk_service
python fair_risk_engine.py
```

You should see something like:

```text
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

Useful URLs:

- Health: `http://localhost:8000/`
- Docs: `http://localhost:8000/docs`
- OpenAPI: `http://localhost:8000/openapi.json`

Alternative (more explicit) run command:

```bash
uvicorn fair_risk_engine:app --reload --host 0.0.0.0 --port 8000
```

> Keep this terminal open while developing; the frontend will talk to this server.

---

## 3. Node / Frontend Setup

### 3.1. Install Node Dependencies

From the **project root** (! not inside `risk_service`):

```bash
npm install
```

This installs React, TypeScript, Vite, Tailwind, Recharts, Lucide, etc.

### 3.2. Configure Backend URL via `.env`

Create a `.env` file in the **project root** (same level as `package.json`). This is used by Vite/TypeScript to configure the backend URL at build-time:

```bash
VITE_API_URL=http://localhost:8000
```

- The prefix `VITE_` is required or Vite will ignore the variable.
- The frontend’s API client (`src/utils/fairApi.ts`) reads `import.meta.env.VITE_API_URL` and falls back to `http://localhost:8000` if it’s missing.

If you change the backend port or host, update this value accordingly.

### 3.3. Start the Frontend (Vite)

From the **project root**:

```bash
npm start
```

You should see something like:

```text
VITE v6.x.x  ready in XXX ms
  ➜  Local:   http://localhost:5173/
```

Vite usually opens a browser window automatically; if not, just navigate to `http://localhost:5173/` manually.

> Make sure the backend (step 2.3) is running before you try to use the app fully.

---

## 4. Testing the Stack End-to-End

### 4.1. Backend Health

In a separate terminal, while the backend is running:

```bash
curl http://localhost:8000/
```

Expected JSON (shape, not exact values):

```json
{
  "service": "FAIR Risk Quantification API",
  "version": "1.0.0",
  "status": "operational"
}
```

### 4.2. IRIS 2025 Benchmarks

- LEF (frequency) benchmarks:

  ```bash
  curl "http://localhost:8000/api/benchmarks/lef?industry=Financial%20Services&revenue=%241B%20to%20%2410B"
  ```

- LM (loss magnitude) benchmarks:

  ```bash
  curl "http://localhost:8000/api/benchmarks/lm?industry=Financial%20Services&revenue=%241B%20to%20%2410B"
  ```

If the backend is correctly wired, you’ll get structured JSON with separate `industry`, `revenue`, and `overall_baseline` entries.

### 4.3. Calculation API

Run a simple Monte Carlo calculation using minimal inputs:

```bash
curl -X POST http://localhost:8000/calculate   -H "Content-Type: application/json"   -d '{
    "tef": {
      "percentiles": {"p10": 1.2, "p50": 2.5, "p90": 4.0},
      "model": "poisson"
    },
    "susceptibility": {
      "percentiles": {"p10": 20, "p50": 35, "p90": 55}
    },
    "loss_forms": {
      "productivity": {"p10": 150000, "p50": 400000, "p90": 900000},
      "response": {"p10": 150000, "p50": 250000, "p90": 500000}
    },
    "slef": {
      "percentiles": {"p10": 35, "p50": 65, "p90": 85}
    },
    "currency": "USD"
  }'
```

You should see a response with `ale`, `lef`, `lm`, and `loss_forms` blocks.

### 4.4. Frontend Behaviour

In the browser at `http://localhost:5173/`:

1. Check that the backend status indicator in the header shows **Connected** when the backend is running.
2. On the dashboard:
   - The pre-seeded scenarios should show stable Monte Carlo results (because the backend simulation uses a fixed seed).
3. In the scenario wizard:
   - Select **Industry** + **Annual revenue** → IRIS 2025 benchmark hints should appear.
   - Fill in TEF, susceptibility, and loss ranges → the preview section should show LEF and LM approximations.

---

## 5. Configuration Details

### 5.1. Environment Variables (Frontend)

- File: `.env` (project root)
- Variable:

  ```bash
  VITE_API_URL=http://localhost:8000
  ```

For production deployments, you might use `.env.production` or your hosting platform’s env management, but the variable key stays the same.

### 5.2. Backend Port/Host

To run the backend on another port (e.g. 8001), update the run command:

```bash
uvicorn fair_risk_engine:app --reload --host 0.0.0.0 --port 8001
```

Then update `.env`:

```bash
VITE_API_URL=http://localhost:8001
```

Restart the frontend dev server after changing `.env`.

---

## 6. Production Deployment (High Level/Theoretical)

- This was not intended as a production tool, see limitations. However, this section gives a high-level overview of the steps needed for this. 
### 6.1. Build Frontend

From the project root:

```bash
npm run build
```

This produces a `dist/` folder with static assets you can serve via:

- Nginx
- Apache
- A cloud static host (S3 + CloudFront, Netlify, Vercel, etc.)

### 6.2. Run Backend with Gunicorn + Uvicorn Worker

On the server:

```bash
cd risk_service
pip install gunicorn uvicorn
gunicorn api:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

You would typically put this behind a reverse proxy (Nginx/Traefik) and configure HTTPS there.

### 6.3. Point Frontend to Production Backend

Set `VITE_API_URL` to your public backend URL before building, for example:

```bash
VITE_API_URL=https://api.yourdomain.com
```

Then rebuild the frontend:

```bash
npm run build
```

Deploy the new `dist/` to your static host.

---

## 7. Common Issues & Fixes

### 7.1. Frontend Cannot Reach Backend

- Make sure backend is running: `curl http://localhost:8000/`
- Confirm `VITE_API_URL` is correct in `.env`
- Restart the Vite dev server after changing `.env`

### 7.2. CORS Errors

The backend includes:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

For local development this should “just work”. For production, tighten `allow_origins` to your real frontend origin (e.g. `["https://app.yourdomain.com"]`).

### 7.3. TypeScript Errors About `import.meta.env`

Ensure `src/vite-env.d.ts` contains:

```ts
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
```

### 7.4. Vite Not Auto-Opening Browser

Some terminals / environments don’t auto-open on `npm start`. This is normal; just open `http://localhost:5173/` manually. You can also add `--open` to the dev script in `package.json` if desired.

### 7.5. Port Already in Use

If port 8000 or 5173 is in use:

```bash
# Example for macOS/Linux, kill whatever is using 8000
lsof -ti:8000 | xargs kill -9
```

Then restart the backend.

---

## 8. Unix Convenience Script (Optional)

If you want a single command to start both backend and frontend, you can adapt the existing `start.sh` (in project root) or create one like:

```bash
#!/usr/bin/env bash
set -e

# Start risk_service in background
cd risk_service
uvicorn fair_risk_engine:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd ..

# Start frontend (blocking)
npm start

# When frontend exits, stop risk_service
kill "$BACKEND_PID"
```

Make it executable:

```bash
chmod +x start.sh
```

Then run:

```bash
./start.sh
```

This is purely optional; using two terminals works just as well.

---

