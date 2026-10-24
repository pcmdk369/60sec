# Drama & Entertainment Shorts Cutter

A Next.js frontend and FastAPI backend that splits an uploaded video into consecutive clips of up to 60 seconds, crops each clip to vertical 9:16 (1080×1920), adds the “Drama & Entertainment” watermark, and returns the MP4 clips in one ZIP.

## Requirements

- Node.js 20+
- Python 3.10+
- FFmpeg and FFprobe installed and available in `PATH`

Install FFmpeg:
- Ubuntu/Debian: `sudo apt-get update && sudo apt-get install -y ffmpeg`
- macOS: `brew install ffmpeg`
- Windows: install FFmpeg and add its `bin` folder to `PATH`
- Termux: `pkg install ffmpeg python nodejs`

## Start the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Backend health check: http://127.0.0.1:8000/health

## Start the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000, select a video, and click **CREATE SHORTS**.

## Deployment configuration

- Frontend environment variable: `NEXT_PUBLIC_API_URL` — public base URL of the deployed FastAPI service, without a trailing slash.
- Backend environment variable: `CORS_ORIGINS` — comma-separated list of trusted frontend origins, for example `https://your-frontend.example`.
- The backend host must have FFmpeg and FFprobe installed. Confirm the host's request-body, execution-time, and temporary-disk limits can support large video uploads.
- Do not put private API keys or secrets in `NEXT_PUBLIC_*` variables; these values are exposed to the browser.

## Current processing behavior

- Fixed-duration cuts only; no scene detection, AI processing, or automatic captions.
- Maximum upload size is 2 GB at the application level, but the deployment host may impose a lower limit.
- The final clip may be shorter than 60 seconds.
