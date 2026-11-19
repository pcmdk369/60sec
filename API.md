# API Reference — Clip AI

Base URL is the deployed FastAPI origin. Interactive OpenAPI documentation is available at /docs unless disabled by deployment configuration.

All routes except GET /health and POST /api/auth/login require an Authorization: Bearer access token header.

## GET /health
Returns service and configuration indicators. A successful response confirms the API process is responding; it does not prove FFmpeg can encode a video or an external LLM is reachable.

## POST /api/auth/login
JSON body: {"username":"Admin","password":"<admin password>"}
Returns access_token, token_type, expires_in, and username. Invalid credentials return 401; missing auth configuration returns 503; repeated failures from the same process-local client IP are throttled with 429.

## GET /api/auth/session
Requires a bearer token. Returns authenticated: true and the configured username.

## POST /api/jobs
Multipart fields:
- file (required): MP4, MOV, MKV, WEBM, or M4V.
- captions_enabled: boolean, default true.
- caption_language: original, english, or hindi.
- caption_style: auto, classic, bold, or minimal.
- caption_color: white, yellow, cyan, or pink.
- caption_size: small, medium, or large.
- output_resolution: 480p, 720p, 1080p, or 2160p.
- encoding_priority: fast, balanced, or quality.
- framing: portrait or pad.

Returns HTTP 202 with job_id, status, message, and status_url. Supported extensions are checked by the application; media validity is checked with FFprobe. Maximum application upload size is 2 GiB, subject to smaller upstream host limits.

## GET /api/jobs/{job_id}
Requires admin authentication. Returns job_id, status, message, and optional download URL. Status values: queued, processing, completed, failed.

## GET /api/jobs/{job_id}/download
Requires admin authentication. Returns ZIP when complete. Returns 409 while processing and 404 if the job/archive is unavailable.

## Error responses
FastAPI returns HTTP error responses with a detail field for validation, authentication, media, and processing errors. Clients should not assume every 500-level error is retryable.

## Example
Use POST /api/auth/login with a JSON body, then send the returned token in the Authorization header for job endpoints. Do not place credentials in URLs or logs.
