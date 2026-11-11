# Clip AI — Requirements

## Product purpose
Clip AI (the existing 60sec / FrameFlow application) converts an authorized source video into sequential short-form MP4 clips, applies a permanent Drama & Entertainment watermark, optionally burns captions, and packages outputs into a ZIP.

## Users and access
- Current release is a single-owner/admin workspace, not a public multi-tenant SaaS.
- Admin sign-in is required for upload, job status, and downloads.
- Users must own or have permission to process every uploaded source.

## Functional requirements
1. Accept MP4, MOV, MKV, WEBM, and M4V uploads.
2. Reject empty files, unsupported extensions, and files larger than the configured 2 GiB application limit.
3. Split source video into sequential segments no longer than 60 seconds.
4. Support 9:16 portrait crop or padded framing.
5. Support 480p, 720p, 1080p, and 2160p output presets.
6. Encode H.264 video, AAC audio when present, and 30 fps output.
7. Apply the configured permanent lower-right watermark to every exported clip.
8. Optionally generate captions using faster-whisper; support Original, English, and Hindi modes, plus caption style, color, and size controls.
9. Return a job ID immediately after upload; expose queued, processing, completed, and failed states.
10. Provide the completed ZIP through an authenticated download endpoint.
11. Expose a health endpoint and useful operational status.
12. Provide a responsive frontend with upload validation, preview, settings, job status, and clear errors.

## Non-functional requirements
- Never expose credentials in browser bundles or source control.
- Restrict CORS to explicitly configured origins.
- Bound upload size and worker concurrency.
- Use isolated temporary directories and clean failed work.
- Provide structured, actionable errors without leaking secrets.
- Keep the API and frontend deployable independently.
- Maintain automated tests and CI build checks.
- Document all required environment variables and operational limitations.

## Current release boundaries
- Single configured administrator; no end-user accounts or tenant isolation.
- Background jobs use a process-local thread pool and JSON metadata file; this is not a distributed durable queue.
- Job artifacts rely on local filesystem storage.
- No clip-selection/virality model, face tracking, collaborative editor, social publishing, or stock-media search is currently implemented.
- Production multi-user service requires durable queue/storage, ownership-scoped jobs, quotas, rate limiting, retention, and monitoring.

## Acceptance criteria
- Frontend production build succeeds.
- Backend imports and automated auth/API tests pass.
- Unsupported inputs and unauthorized API access are rejected.
- A small valid sample video can be encoded and downloaded as a ZIP in an environment with FFmpeg installed.
- Deployment documentation accurately identifies dependencies, secrets, storage and queue limitations.
