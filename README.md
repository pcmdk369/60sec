# Clip AI — 60-Second Video Shorts Cutter

Clip AI (also branded in this repository as **FrameFlow**) is a focused video-processing workspace that turns an authorized source video into sequential short-form MP4 clips. It uses Next.js, FastAPI, FFmpeg/FFprobe, and optional faster-whisper captions.

> **Current capability boundary:** the application cuts videos at sequential 60-second boundaries. It does not yet use an AI model to discover viral moments, rank highlights, track faces, or automatically select semantic scenes.

## Features

- Admin-only workspace with password-hash authentication and expiring HMAC-signed bearer sessions.
- MP4, MOV, MKV, WEBM, and M4V uploads; application-level maximum 2 GiB.
- Sequential clips up to 60 seconds each.
- 9:16 portrait crop or padded framing.
- 480p, 720p, 1080p, and 2160p output settings.
- H.264 video, AAC audio when present, 30 fps, and fast-start MP4 output.
- Permanent lower-right Drama & Entertainment watermark.
- Optional faster-whisper captions in Original, English, and Hindi modes.
- Background job status and ZIP download.

## Technology

| Layer | Technology |
|---|---|
| Frontend | Next.js 15, React 18, TypeScript |
| Backend | Python 3.11, FastAPI |
| Video | FFmpeg, FFprobe, libx264 |
| Speech | faster-whisper (optional at runtime) |
| Jobs | Process-local ThreadPoolExecutor |
| Deployment | Vercel frontend, Render backend |

## Repository layout

```text
60sec/
├── .github/workflows/       # CI and dependency/security checks
├── backend/
│   ├── app/main.py          # API, authentication, job and media pipeline
│   ├── scripts/             # Admin password hash utility
│   ├── tests/               # Backend automated tests
│   ├── Dockerfile
│   └── requirements*.txt
├── frontend/
│   ├── app/                 # Next.js application
│   └── package.json
├── REQUIREMENTS.md
├── PRODUCT_SPEC.md
├── ARCHITECTURE.md
├── API.md
└── render.yaml
```

## Local installation

### Prerequisites
- Node.js 20+ and npm.
- Python 3.11.
- FFmpeg and FFprobe available on PATH.
- FFmpeg build with drawtext; subtitles filter/libass is needed for burned captions.

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python scripts/generate_admin_password_hash.py
```

Put the generated ADMIN_PASSWORD_HASH in backend/.env. Set ADMIN_USERNAME and a strong random SESSION_SECRET of at least 32 characters. Keep this file private and never commit it.

Start the API:

```bash
set -a
. ./.env
set +a
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Health check: http://127.0.0.1:8000/health

### Frontend

In a second terminal:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open http://localhost:3000. Set NEXT_PUBLIC_API_URL to the backend's browser-reachable URL.

### Backend tests

```bash
cd backend
python -m pip install -r requirements-dev.txt
PYTHONPATH=. python -m pytest tests -q
```

### Production frontend build

```bash
cd frontend
npm install
npm run build
```

## Environment variables

See backend/.env.example and frontend/.env.example. Backend authentication requires:
- ADMIN_USERNAME
- ADMIN_PASSWORD_HASH (generate locally with the supplied script)
- SESSION_SECRET (minimum 32 characters)
- CORS_ORIGINS

Optional caption settings: WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE. Optional Hindi translation fallback: LLM_API_KEY, LLM_API_URL, LLM_MODEL_ID. Keep all backend credentials in the backend host's secret/environment configuration. NEXT_PUBLIC_API_URL is public.

## API

See [API.md](API.md) for the current routes and request fields. FastAPI OpenAPI documentation is available at /docs.

## Deployment

- Deploy frontend/ as a Next.js project and set NEXT_PUBLIC_API_URL.
- Deploy backend/ using the included Dockerfile or a Python runtime with FFmpeg installed.
- Set CORS_ORIGINS to the exact deployed frontend origin.
- Configure ADMIN_USERNAME, ADMIN_PASSWORD_HASH, and SESSION_SECRET in the backend host.
- Use a persistent disk if generated job files must survive instance restarts.

The root render.yaml currently describes the backend service. Review the proposed infrastructure settings before applying any deployment changes.

## Security and operational limitations

- Current access is single-admin; this is not yet a multi-user SaaS.
- Login throttling and the job queue are process-local.
- Job metadata is written to a local JSON file; interrupted jobs are marked failed and are not resumed.
- Generated files use local disk; ephemeral hosts can remove them.
- A retention/cleanup policy for completed job directories is still required.
- Upstream request-body limits may be lower than the application's 2 GiB limit.
- Run media processing as a non-root user with resource limits. Treat uploaded media as untrusted input.
- A successful /health response does not prove a complete FFmpeg encode works. Validate with a real sample video in the target hosting environment.

Before exposing the service to multiple users, implement a durable queue, database-backed job ownership, private object storage, per-user authorization, quotas, rate limiting, retention, and operational monitoring.

## Product roadmap

1. Reliability: integration tests, resource limits, cleanup, monitoring.
2. Durable processing: persistent queue, database job state, private object storage.
3. AI-assisted highlight discovery with human review and editable clip boundaries.
4. Speaker-aware reframing and word-level caption editing.
5. Authenticated integrations and publishing workflows.

## License and ownership

The repository contains an MIT License in LICENSE. The code is therefore licensed under the terms in that file. PCMDK369 branding and third-party assets may have separate rights; do not assume the MIT license grants rights to external trademarks or assets.
