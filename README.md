# Drama & Entertainment Shorts Cutter

Next.js frontend + FastAPI video processor. Upload a video to cut it into up-to-60-second vertical 9:16 clips (1080×1920), add the watermark, optionally generate automatic captions, and download all MP4 clips as one ZIP.

## Requirements
- Node.js 20+
- Python 3.10+
- FFmpeg with FFprobe and the FFmpeg `subtitles` and `drawtext` filters (the subtitles filter needs libass)
- For automatic captions: `faster-whisper`; first run downloads the selected model (default `base`)

Install FFmpeg on Ubuntu/Debian: `sudo apt-get update && sudo apt-get install -y ffmpeg`. On Termux: `pkg install ffmpeg python nodejs`. Some Termux FFmpeg builds may lack libass; check with `ffmpeg -filters | grep subtitles`.

## Run locally
Backend:
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Frontend in another terminal:
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:3000. Health check: http://127.0.0.1:8000/health.

## Caption options
- **Original**: transcribe speech in its detected language.
- **English**: use local Whisper speech translation to English.
- **Hindi**: if the speech is already Hindi/Urdu, use local recognition; if not, the optional emergency LLM fallback can translate the recognized segments into Hindi.
- Templates: Auto recommend, Classic, Bold, Minimal. Colors: White, Yellow, Cyan, Pink. Sizes: Small, Medium, Large.
- Captions are burned into the exported video. The browser preview is a style sample, not a real-time rendered video preview.
- Automatic captioning requires model download, RAM/CPU, and FFmpeg's subtitles/libass support. For silent videos or failures, disable captions or check the backend logs.

## Emergency LLM (optional)
Configure these **only on the backend host** as environment variables:
- `LLM_API_KEY`
- `LLM_API_URL` (full chat-completions endpoint)
- `LLM_MODEL_ID`

No secret values are committed. The LLM is never called for ordinary cutting, Original captions, or English captions. It is called only when Hindi captions are requested for non-Hindi speech and the local pipeline cannot translate that language to Hindi. The LLM request has a 35-second timeout. Use a restricted key with low quota and provider-side spend limits. Never use a `NEXT_PUBLIC_*` variable for secrets.

Other deployment variables:
- Frontend: `NEXT_PUBLIC_API_URL` = public FastAPI URL, no trailing slash.
- Backend: `CORS_ORIGINS` = comma-separated frontend origins.
- Optional Whisper controls: `WHISPER_MODEL=base`, `WHISPER_DEVICE=cpu`, `WHISPER_COMPUTE_TYPE=int8`.

## Limits
The app validates uploads up to 2 GB; deployment providers may impose lower request/time/disk limits. Large videos and CPU transcription can take a long time. Only upload content you have permission to process.
