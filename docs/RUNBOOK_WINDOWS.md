# Local runbook for Windows PowerShell

Antigravity should update these commands to match the actual package scripts after implementation. Keep the setup commands beginner-friendly and verify they work before documenting them as final.

## Prerequisites
- Python 3.11 or a compatible version selected by the implementation.
- Node.js LTS.
- Git (optional for running locally, recommended for version control).

## Expected setup pattern

```powershell
# From the project root
Copy-Item .env.example .env

# Backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
python -m uvicorn app.main:app --reload --app-dir backend
```

In a second PowerShell terminal:

```powershell
cd frontend
npm install
npm run dev
```

The exact module path, requirements file and scripts may be adjusted by Antigravity. After implementation, update this runbook and the root README with the exact tested commands and local URLs. Do not leave placeholder commands labelled as tested.
