# Architecture — Clip AI

## System context
The application has two independently deployed components:
- **Next.js frontend** (frontend/): admin UI, file selection/preview, upload, polling, and ZIP download.
- **FastAPI backend** (backend/): authentication, upload validation, job state, speech recognition, FFmpeg processing, and archive delivery.

## Current request flow
Browser -> Next.js UI -> FastAPI API -> process-local ThreadPoolExecutor -> FFprobe -> optional faster-whisper -> FFmpeg segments -> local job directory -> ZIP -> browser download.

## Backend modules
- backend/app/main.py: FastAPI routes, PBKDF2 password verification, HMAC-signed expiring admin tokens, in-memory login throttling, upload/job handling, Whisper and FFmpeg pipeline.
- backend/scripts/generate_admin_password_hash.py: generates a salted PBKDF2-SHA256 password hash without printing the plaintext password.
- backend/Dockerfile: Python runtime plus FFmpeg and fonts.

## Frontend modules
- frontend/app/page.tsx: admin session, upload/preview, options, job polling and download.
- frontend/app/globals.css: responsive UI.
- frontend/app/layout.tsx: metadata and root layout.

## Configuration
Frontend public variable: NEXT_PUBLIC_API_URL (public backend base URL).

Backend variables:
- ADMIN_USERNAME
- ADMIN_PASSWORD_HASH
- SESSION_SECRET (at least 32 characters)
- CORS_ORIGINS
- VIDEO_WORKERS
- JOB_STORAGE_DIR
- WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE
- Optional Hindi fallback: LLM_API_KEY, LLM_API_URL, LLM_MODEL_ID

## Security boundaries
- Bearer token is HMAC-SHA256 signed and expires after 12 hours.
- Password hashes use PBKDF2-SHA256; generate them locally using the supplied script.
- Keep SESSION_SECRET, password hash, and LLM key only in backend secret storage.
- NEXT_PUBLIC_* values are public and must never contain secrets.
- CORS is configured through an explicit origin allowlist.
- Video files are untrusted input. FFmpeg and FFprobe execute as subprocesses; run the backend as a non-root user with bounded CPU, memory, disk, and network access.
- Current login throttling and job state are process-local. They do not coordinate across replicas.

## Known operational limitations
- ThreadPoolExecutor jobs are lost on process restart; persisted metadata marks interrupted jobs failed but does not resume them.
- Local filesystem artifacts disappear when the host's ephemeral disk is cleared.
- No scheduled cleanup/retention policy currently removes completed job directories.
- Upload body limits may be enforced by the reverse proxy before application-level 2 GiB validation.
- The current app is single-admin and does not provide tenant isolation.
- Synchronous FFmpeg work runs in worker threads; capacity must be sized conservatively.

## Target production architecture
For multi-user scale, replace the in-process queue with a durable queue, persist job metadata in a database, store assets in private object storage, scope every job to an authenticated owner, use short-lived signed download URLs, implement quotas/rate limits/retention, and add metrics/log aggregation. Do not claim these target components are deployed until they are configured and tested.
