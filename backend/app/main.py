import os, shutil, subprocess, tempfile, zipfile, math, json, re, asyncio, threading, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError
from urllib.parse import urlencode, urlparse
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Header, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask


def require_admin(authorization: str | None = Header(default=None)):
    """Validate a Supabase access token and allow only the configured admin email."""
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    publishable_key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
    admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    if not (supabase_url and publishable_key and admin_email):
        raise HTTPException(503, "Admin authentication is not configured on the backend.")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in with the admin account to continue.")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(401, "Missing access token.")
    req = Request(
        supabase_url + "/auth/v1/user",
        headers={"apikey": publishable_key, "Authorization": "Bearer " + token},
        method="GET",
    )
    try:
        with urlopen(req, timeout=10) as response:
            user = json.loads(response.read().decode("utf-8"))
    except Exception:
        raise HTTPException(401, "Your session is invalid or expired. Sign in again.")
    if str(user.get("email") or "").strip().lower() != admin_email:
        raise HTTPException(403, "Admin access only.")
    return {"id": user.get("id"), "email": admin_email}

app = FastAPI(title="Drama & Entertainment Shorts Cutter")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if x.strip()],
    allow_methods=["*"], allow_headers=["*"]
)

@app.get("/health")
def health():
    return {
        "status": "ok",
        "captions": "local-faster-whisper",
        "watermark": "Drama & Entertainment",
        "emergency_llm_configured": bool(os.getenv("LLM_API_KEY") and os.getenv("LLM_API_URL") and os.getenv("LLM_MODEL_ID")),
        "recaptcha_configured": bool(os.getenv("RECAPTCHA_SECRET_KEY", "").strip()),
    }


@app.post("/api/auth/verify-captcha")
def verify_captcha(payload: dict = Body(...)):
    """Verify Google reCAPTCHA on the server before allowing an admin sign-in attempt."""
    secret = os.getenv("RECAPTCHA_SECRET_KEY", "").strip()
    if not secret:
        raise HTTPException(503, "Robot verification is not configured on the backend. Set RECAPTCHA_SECRET_KEY in Render.")
    token = str(payload.get("token") or "").strip()
    if not token:
        raise HTTPException(400, "Complete the robot verification first.")
    verify_request = Request(
        "https://www.google.com/recaptcha/api/siteverify",
        data=urlencode({"secret": secret, "response": token}).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(verify_request, timeout=8) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception:
        raise HTTPException(502, "Could not verify the robot check. Please try again.")
    if not result.get("success"):
        raise HTTPException(400, "Robot verification expired or failed. Complete it again.")
    allowed_hosts = {
        (urlparse(origin.strip()).hostname or "").lower()
        for origin in os.getenv("CORS_ORIGINS", "").split(",")
        if origin.strip()
    }
    verified_host = str(result.get("hostname") or "").lower()
    if allowed_hosts and verified_host not in allowed_hosts:
        raise HTTPException(400, "Robot verification was issued for a different site.")
    return {"success": True}

def emergency_translate(text: str, target: str) -> str:
    """One optional OpenAI-compatible LLM call, only as fallback for local translation failure."""
    key, url, model = (os.getenv(k, "").strip() for k in ("LLM_API_KEY", "LLM_API_URL", "LLM_MODEL_ID"))
    if not (key and url and model):
        raise RuntimeError("Hindi translation needs the optional emergency LLM fallback on this server, but it is not configured. Configure the three LLM_* backend environment variables or use Original/English.")
    prompt = "Translate each subtitle segment into natural " + target + ". Keep timestamps and segment order exactly. Return ONLY JSON array of strings, one translation per input item. Input: " + json.dumps(text, ensure_ascii=False)
    payload = json.dumps({"model": model, "messages": [{"role": "system", "content": "You are a subtitle translation fallback. Follow the requested output format exactly."}, {"role": "user", "content": prompt}], "temperature": 0.1}).encode()
    req = Request(url, data=payload, headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=35) as response:
        data = json.loads(response.read().decode("utf-8"))
    content = data["choices"][0]["message"]["content"]
    match = re.search(r"\[.*\]", content, re.S)
    if not match:
        raise RuntimeError("Emergency LLM returned an invalid translation response.")
    result = json.loads(match.group(0))
    if not isinstance(result, list) or len(result) != len(text):
        raise RuntimeError("Emergency LLM returned the wrong number of caption segments.")
    return [str(x) for x in result]

def make_srt(segments, path: Path):
    def stamp(seconds):
        ms = int(seconds * 1000)
        h, rem = divmod(ms, 3600000); m, rem = divmod(rem, 60000); s, ms = divmod(rem, 1000)
        return f"{h:02}:{m:02}:{s:02},{ms:03}"
    with path.open("w", encoding="utf-8") as f:
        for idx, (start, end, text) in enumerate(segments, 1):
            clean = str(text).replace("-->", "→").strip()
            f.write(f"{idx}\n{stamp(start)} --> {stamp(max(start + .15, end))}\n{clean}\n\n")

async def _process_shorts(
    file: UploadFile = File(...),
    captions_enabled: bool = Form(True),
    caption_language: str = Form("original"),
    caption_style: str = Form("auto"),
    caption_color: str = Form("white"),
    caption_size: str = Form("medium"),
    output_resolution: str = Form("1080p"),
    encoding_priority: str = Form("balanced"),
    framing: str = Form("portrait")
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}:
        raise HTTPException(415, "Upload MP4, MOV, MKV, WEBM or M4V.")
    if caption_language not in {"original", "english", "hindi"} or caption_style not in {"auto", "classic", "bold", "minimal"} or caption_color not in {"white", "yellow", "cyan", "pink"} or caption_size not in {"small", "medium", "large"}:
        raise HTTPException(400, "Invalid caption setting.")
    if output_resolution not in {"480p", "720p", "1080p", "2160p"} or encoding_priority not in {"fast", "balanced", "quality"} or framing not in {"portrait", "pad"}:
        raise HTTPException(400, "Invalid video quality setting.")
    dimensions = {"480p": (480, 854), "720p": (720, 1280), "1080p": (1080, 1920), "2160p": (2160, 3840)}
    target_width, target_height = dimensions[output_resolution]
    encoder_profiles = {"fast": {"preset": "veryfast", "crf": "23"}, "balanced": {"preset": "fast", "crf": "21"}, "quality": {"preset": "medium", "crf": "18"}}
    encoder = encoder_profiles[encoding_priority]
    work = Path(tempfile.mkdtemp(prefix="drama-shorts-"))
    try:
        source = work / ("source" + ext)
        size = 0
        with source.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk: break
                size += len(chunk)
                if size > 2 * 1024**3: raise HTTPException(413, "Maximum upload size is 2 GB.")
                out.write(chunk)
        if not size: raise HTTPException(400, "Empty video.")
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(source)], capture_output=True, text=True)
        if probe.returncode: raise HTTPException(422, "Unable to read video. Check FFmpeg installation.")
        duration = float(probe.stdout.strip())
        if duration <= 0: raise HTTPException(422, "Invalid video duration.")

        segments = []
        captions_available = False
        captions_warning = None
        if captions_enabled:
            try:
                from faster_whisper import WhisperModel
                model_name = os.getenv("WHISPER_MODEL", "base")
                model = WhisperModel(model_name, device=os.getenv("WHISPER_DEVICE", "cpu"), compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"))
                task = "translate" if caption_language == "english" else "transcribe"
                recognized, info = model.transcribe(str(source), task=task, vad_filter=True, beam_size=3)
                segments = [(float(s.start), float(s.end), s.text.strip()) for s in recognized if s.text.strip()]
                if not segments:
                    raise RuntimeError("No speech was detected in the source audio.")
                if caption_language == "hindi" and (info.language or "").lower() not in {"hi", "ur"}:
                    translated = emergency_translate([s[2] for s in segments], "Hindi")
                    segments = [(s[0], s[1], translated[i]) for i, s in enumerate(segments)]
                captions_available = bool(segments)
            except Exception as exc:
                # Captions are optional: a speech/model/translation failure must not
                # prevent the requested video cuts, watermark, and ZIP export.
                captions_warning = str(exc)[:500]
                segments = []
                captions_available = False

        clips = work / "clips"; clips.mkdir()
        # Use a text file so punctuation such as '&' is passed literally to FFmpeg.
        watermark_file = work / "watermark.txt"
        watermark_file.write_text("Drama & Entertainment", encoding="utf-8")
        watermark_path = str(watermark_file).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        count = max(1, math.ceil(duration / 60))
        color = {"white": "&H00FFFFFF", "yellow": "&H0000FFFF", "cyan": "&H00FFFF00", "pink": "&H00C0A0FF"}[caption_color]
        size_px = {"small": 42, "medium": 54, "large": 66}[caption_size]
        outline = 3 if caption_style in {"auto", "bold"} else 2
        if caption_style == "minimal": outline = 1
        for i in range(count):
            start = i * 60; length = min(60, duration - start)
            if length <= 0: continue
            output = clips / f"short_{i+1:03d}.mp4"
            if framing == "portrait":
                filters = [f"scale={target_width}:{target_height}:force_original_aspect_ratio=increase", f"crop={target_width}:{target_height}", "setsar=1"]
            else:
                filters = [f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease", f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black", "setsar=1"]
            if captions_enabled and captions_available:
                local = [(max(0, a-start), min(length, b-start), t) for a,b,t in segments if b > start and a < start+length]
                if local:
                    srt = work / f"captions_{i+1:03d}.srt"
                    make_srt(local, srt)
                    escaped = str(srt).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
                    style = f"FontName=Arial,FontSize={size_px},PrimaryColour={color},OutlineColour=&H000000,BorderStyle=1,Outline={outline},Shadow=1,Alignment=2,MarginV=140"
                    filters.append(f"subtitles='{escaped}':force_style='{style}'")
            # Permanent, visible lower-right watermark on every exported clip.
            filters.append(f"drawtext=textfile='{watermark_path}':fontcolor=white:fontsize=42:box=1:boxcolor=black@0.60:boxborderw=14:x=w-tw-44:y=h-th-54")
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start), "-i", str(source), "-t", str(length), "-map", "0:v:0", "-map", "0:a:0?", "-vf", ",".join(filters), "-c:v", "libx264", "-preset", encoder["preset"], "-crf", encoder["crf"], "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode: raise HTTPException(422, "FFmpeg error: " + result.stderr[-1000:])
        archive = work / "drama-entertainment-shorts.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for clip in sorted(clips.glob("*.mp4")):
                z.write(clip, clip.name)
            if captions_enabled and captions_warning:
                status_file = work / "captions-status.txt"
                status_file.write_text(
                    "Video processing completed successfully, but automatic captions were skipped.\n"
                    f"Reason: {captions_warning}\n"
                    "The MP4 clips include the original audio and watermark. Try a video with clear speech, "
                    "or disable captions for videos without dialogue.\n",
                    encoding="utf-8",
                )
                z.write(status_file, status_file.name)
        return FileResponse(str(archive), media_type="application/zip", filename=archive.name, background=BackgroundTask(shutil.rmtree, work, ignore_errors=True))
    except HTTPException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(work, ignore_errors=True)
        raise HTTPException(500, "Processing failed: " + str(exc)[:400]) from exc
    finally:
        await file.close()


# Lightweight in-process background job queue. Jobs continue after the browser request returns.
# For multi-instance production deployments, replace this with Redis/Celery or a durable queue.
JOB_ROOT = Path(os.getenv("JOB_STORAGE_DIR", tempfile.gettempdir())) / "drama-shorts-jobs"
JOB_ROOT.mkdir(parents=True, exist_ok=True)
JOBS = {}
JOBS_LOCK = threading.Lock()
WORKERS = ThreadPoolExecutor(max_workers=max(1, int(os.getenv("VIDEO_WORKERS", "1"))))

def _run_job(job_id: str, source_path: Path, options: dict):
    job_dir = JOB_ROOT / job_id
    with JOBS_LOCK:
        JOBS[job_id]["status"] = "processing"
        JOBS[job_id]["message"] = "Video is processing in the background."
    try:
        with source_path.open("rb") as handle:
            upload = UploadFile(filename=source_path.name, file=handle)
            response = asyncio.run(_process_shorts(
                file=upload,
                captions_enabled=options["captions_enabled"],
                caption_language=options["caption_language"],
                caption_style=options["caption_style"],
                caption_color=options["caption_color"],
                caption_size=options["caption_size"],
                output_resolution=options["output_resolution"],
                encoding_priority=options["encoding_priority"],
                framing=options["framing"]
            ))
            if not isinstance(response, FileResponse):
                raise RuntimeError("Video processor did not return a ZIP file.")
            zip_path = job_dir / "drama-entertainment-shorts.zip"
            shutil.copyfile(response.path, zip_path)
            if response.background:
                task = response.background()
                if asyncio.iscoroutine(task):
                    asyncio.run(task)
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "completed"
            JOBS[job_id]["message"] = "Your ZIP is ready to download."
            JOBS[job_id]["download_url"] = f"/api/jobs/{job_id}/download"
    except Exception as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["status"] = "failed"
                JOBS[job_id]["message"] = str(exc)[:700]
    finally:
        source_path.unlink(missing_ok=True)

@app.post("/api/jobs", status_code=202)
async def create_background_job(
    file: UploadFile = File(...),
    captions_enabled: bool = Form(True),
    caption_language: str = Form("original"),
    caption_style: str = Form("auto"),
    caption_color: str = Form("white"),
    caption_size: str = Form("medium"),
    output_resolution: str = Form("1080p"),
    encoding_priority: str = Form("balanced"),
    framing: str = Form("portrait"),
    _admin: dict = Depends(require_admin),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}:
        raise HTTPException(415, "Upload MP4, MOV, MKV, WEBM or M4V.")
    if caption_language not in {"original", "english", "hindi"} or caption_style not in {"auto", "classic", "bold", "minimal"} or caption_color not in {"white", "yellow", "cyan", "pink"} or caption_size not in {"small", "medium", "large"}:
        raise HTTPException(400, "Invalid caption setting.")
    if output_resolution not in {"480p", "720p", "1080p", "2160p"} or encoding_priority not in {"fast", "balanced", "quality"} or framing not in {"portrait", "pad"}:
        raise HTTPException(400, "Invalid video quality setting.")
    dimensions = {"480p": (480, 854), "720p": (720, 1280), "1080p": (1080, 1920), "2160p": (2160, 3840)}
    target_width, target_height = dimensions[output_resolution]
    encoder_profiles = {"fast": {"preset": "veryfast", "crf": "23"}, "balanced": {"preset": "fast", "crf": "21"}, "quality": {"preset": "medium", "crf": "18"}}
    encoder = encoder_profiles[encoding_priority]
    job_id = uuid.uuid4().hex
    job_dir = JOB_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    source_path = job_dir / ("upload" + ext)
    size = 0
    try:
        with source_path.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > 2 * 1024**3:
                    raise HTTPException(413, "Maximum upload size is 2 GB.")
                out.write(chunk)
        if not size:
            raise HTTPException(400, "Empty video.")
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    finally:
        await file.close()
    options = {
        "captions_enabled": captions_enabled,
        "caption_language": caption_language,
        "caption_style": caption_style,
        "caption_color": caption_color,
        "caption_size": caption_size,
        "output_resolution": output_resolution,
        "encoding_priority": encoding_priority,
        "framing": framing,
    }
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "queued", "message": "Upload received. Waiting for a processing worker.", "download_url": None}
    WORKERS.submit(_run_job, job_id, source_path, options)
    return {"job_id": job_id, "status": "queued", "message": "Upload complete. Processing will continue in the background.", "status_url": f"/api/jobs/{job_id}"}

@app.get("/api/jobs/{job_id}")
def get_background_job(job_id: str, _admin: dict = Depends(require_admin)):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found. Jobs are stored in memory and may be lost if the backend restarts.")
        return {"job_id": job_id, **job}

@app.get("/api/jobs/{job_id}/download")
def download_background_job(job_id: str, _admin: dict = Depends(require_admin)):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found. The backend may have restarted.")
        if job["status"] != "completed":
            raise HTTPException(409, "The ZIP is not ready yet.")
    zip_path = JOB_ROOT / job_id / "drama-entertainment-shorts.zip"
    if not zip_path.is_file():
        raise HTTPException(404, "Generated ZIP is no longer available.")
    return FileResponse(str(zip_path), media_type="application/zip", filename="drama-entertainment-shorts.zip")
