# Product Specification — Clip AI

## Product definition
Clip AI is a focused video-to-shorts processing workspace. The current repository implements deterministic segmentation and export rather than AI-powered highlight discovery. The product name must not imply that virality ranking, semantic scene selection, or automatic speaker tracking is already available.

## Primary workflow
1. Administrator signs in.
2. Selects a local video and reviews its preview.
3. Chooses caption language/style, output resolution, encoding priority, and framing.
4. Uploads the source; the API returns a job identifier.
5. Backend probes the media, optionally transcribes/translates speech, cuts clips at 60-second boundaries, reframes, watermarks, and encodes.
6. Backend packages MP4 outputs and optional caption status into a ZIP.
7. Frontend polls job status and downloads the archive when complete.

## Feature inventory

| Capability | Current state |
|---|---|
| Admin-only login | Implemented; requires backend password hash and session secret |
| Upload validation | Implemented; extension, empty file, 2 GiB application cap |
| 60-second sequential splitting | Implemented |
| 9:16 portrait crop / padded framing | Implemented |
| 480p–2160p output presets | Implemented |
| H.264 / AAC / 30 fps | Implemented |
| Permanent watermark | Implemented |
| Whisper captions | Optional; runtime model/dependency required |
| English translation | Whisper translation task |
| Hindi translation | Native Hindi/Urdu recognition or optional external LLM fallback |
| Background job polling | Implemented; in-process only |
| ZIP export | Implemented |
| AI highlight selection / virality score | Not implemented |
| Face tracking / active speaker reframing | Not implemented |
| Manual clip editor | Not implemented |
| Cloud object storage / distributed queue | Not implemented |
| Social publishing | Not implemented |

## UX principles
- Make upload, settings, job progress, and download states explicit.
- Never present an unavailable feature as active.
- Distinguish caption failure from video-processing failure.
- Explain output settings in plain language.
- Provide accessible labels, keyboard operation, and mobile-friendly controls.
- Keep the current admin-only access boundary visible.

## Product roadmap
### P0 — Reliability and safety
Automated API tests, deterministic dependency management, upload limits, job ownership, cleanup/retention, logging, and deployment health checks.

### P1 — Durable processing
Move job state to a database and work dispatch to a durable queue; store source/output assets in object storage; add retries, cancellation, and recovery.

### P2 — AI-assisted clip discovery
Transcribe and segment speech, score candidate moments using transparent signals, preserve complete thoughts, and let the operator review/edit timestamps before rendering. Treat scores as recommendations, not guaranteed virality.

### P3 — Advanced creator workflow
Speaker-aware reframing, word-level caption editing, reusable brand presets, batch jobs, and export presets.

### P4 — Integrations
Authenticated API/webhooks and optional social publishing only after provider permissions and platform policies are implemented.

## Success measures
- Successful processing rate on supported media.
- Median time to first completed clip and total job duration.
- Caption availability and correction rate by language.
- Failed-job recovery rate.
- Storage consumed per completed job and cleanup compliance.
- Human acceptance rate of any future AI-selected clip candidates.
