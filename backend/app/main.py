import os, shutil, subprocess, tempfile, zipfile, math, json, re, asyncio, threading, uuid, base64, hashlib, hmac, time, secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Header, Depends, Body, Request as FastAPIRequest, Request as FastAPIRequest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask


SESSION_TTL_SECONDS = 12 * 60 * 60
LOGIN_ATTEMPTS = {}
LOGIN_ATTEMPTS_LOCK = threading.Lock()

def _password_matches(password: str, encoded: str) -> bool:
    """Verify PBKDF2-SHA256 format: pbkdf2_sha256$iterations$salt_hex$digest_hex."""
    try:
        scheme, iterations, salt_hex, expected_hex = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        rounds = int(iterations)
        if rounds < 200_000 or rounds > 2_000_000:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), rounds).hex()
        return hmac.compare_digest(actual, expected_hex)
    except (ValueError, TypeError):
        return False

def _session_secret() -> bytes:
    secret = os.getenv("SESSION_SECRET", "").strip()
    if len(secret) < 32:
        raise HTTPException(503, "Admin authentication is not configured. Set a strong SESSION_SECRET on the backend.")
    return secret.encode("utf-8")

def _issue_token(username: str) -> str:
    payload = {"sub": username, "exp": int(time.time()) + SESSION_TTL_SECONDS, "nonce": secrets.token_hex(8)}
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=")
    signature = hmac.new(_session_secret(), body, hashlib.sha256).digest()
    return body.decode() + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()

def _verify_token(token: str) -> dict:
    try:
        body_text, signature_text = token.split(".", 1)
        body = body_text.encode()
        signature = base64.urlsafe_b64decode(signature_text + "=" * (-len(signature_text) % 4))
        expected = hmac.new(_session_secret(), body, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid signature")
        payload = json.loads(base64.urlsafe_b64decode(body_text + "=" * (-len(body_text) % 4)))
        if payload.get("sub") != os.getenv("ADMIN_USERNAME", "Admin").strip() or int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("expired session")
        return payload
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(401, "Your session is invalid or expired. Sign in again.")

SESSION_TTL_SECONDS = 12 * 60 * 60
LOGIN_ATTEMPTS = {}
LOGIN_ATTEMPTS_LOCK = threading.Lock()

def _password_matches(password: str, encoded: str) -> bool:
    try:
        scheme, iterations, salt_hex, expected_hex = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        rounds = int(iterations)
        if rounds < 200_000 or rounds > 2_000_000:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), rounds).hex()
        return hmac.compare_digest(actual, expected_hex)
    except (ValueError, TypeError):
        return False

def _session_secret() -> bytes:
    secret = os.getenv("SESSION_SECRET", "").strip()
    if len(secret) < 32:
        raise HTTPException(503, "Admin authentication is not configured. Set a strong SESSION_SECRET on the backend.")
    return secret.encode("utf-8")

def _issue_token(username: str) -> str:
    payload = {"sub": username, "exp": int(time.time()) + SESSION_TTL_SECONDS, "nonce": secrets.token_hex(8)}
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=")
    signature = hmac.new(_session_secret(), body, hashlib.sha256).digest()
    return body.decode() + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()

def _verify_token(token: str) -> dict:
    try:
        body_text, signature_text = token.split(".", 1)
        body = body_text.encode()
        signature = base64.urlsafe_b64decode(signature_text + "=" * (-len(signature_text) % 4))
        expected = hmac.new(_session_secret(), body, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid signature")
        payload = json.loads(base64.urlsafe_b64decode(body_text + "=" * (-len(body_text) % 4)))
        if payload.get("sub") != os.getenv("ADMIN_USERNAME", "Admin").strip() or int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("expired session")
        return payload
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(401, "Your session is invalid or expired. Sign in again.")

def require_admin(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in with the admin account to continue.")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(401, "Missing access token.")
    payload = _verify_token(token)
    return {"username": payload["sub"]}

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
        "admin_auth_configured": bool(os.getenv("ADMIN_USERNAME") and os.getenv("ADMIN_PASSWORD_HASH") and len(os.getenv("SESSION_SECRET", "")) >= 32),
    }

@app.post("/api/auth/login")
def admin_login(request: FastAPIRequest, payload: dict = Body(...)):
    username = str(payload.get("username") or "")
    password = str(payload.get("password") or "")
    configured_username = os.getenv("ADMIN_USERNAME", "Admin").strip()
    password_hash = os.getenv("ADMIN_PASSWORD_HASH", "").strip()
    if not password_hash or len(os.getenv("SESSION_SECRET", "").strip()) < 32:
        raise HTTPException(503, "Admin authentication is not configured on the backend. Set ADMIN_PASSWORD_HASH and SESSION_SECRET.")
    if not username or not password or len(password) > 1024:
        raise HTTPException(400, "Enter the admin username and password.")
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    with LOGIN_ATTEMPTS_LOCK:
        recent = [stamp for stamp in LOGIN_ATTEMPTS.get(client_ip, []) if now - stamp < 300]
        if len(recent) >= 10:
            LOGIN_ATTEMPTS[client_ip] = recent
            raise HTTPException(429, "Too many login attempts. Wait five minutes and try again.")
        recent.append(now)
        LOGIN_ATTEMPTS[client_ip] = recent
    username_ok = hmac.compare_digest(username.casefold(), configured_username.casefold())
    password_ok = _password_matches(password, password_hash)
    if not (username_ok and password_ok):
        raise HTTPException(401, "Invalid username or password.")
    with LOGIN_ATTEMPTS_LOCK:
        LOGIN_ATTEMPTS.pop(client_ip, None)
    return {"access_token": _issue_token(configured_username), "token_type": "bearer", "expires_in": SESSION_TTL_SECONDS, "username": configured_username}

@app.get("/api/auth/session")
def current_admin_session(admin: dict = Depends(require_admin)):
    return {"authenticated": True, "username": admin["username"]}


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
JOB_STATE_FILE = JOB_ROOT / "jobs.json"
JOBS = {}
JOBS_LOCK = threading.Lock()

def _persist_jobs_locked():
    """Persist job metadata so ordinary process restarts do not erase status records."""
    temp_path = JOB_STATE_FILE.with_suffix(".tmp")
    try:
        temp_path.write_text(json.dumps(JOBS, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(JOB_STATE_FILE)
    except OSError:
        # Do not crash video processing if the ephemeral filesystem is temporarily unavailable.
        pass

try:
    if JOB_STATE_FILE.is_file():
        stored_jobs = json.loads(JOB_STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(stored_jobs, dict):
            JOBS.update(stored_jobs)
            for _job_id, _job in JOBS.items():
                if _job.get("status") in {"queued", "processing"}:
                    _job["status"] = "failed"
                    _job["message"] = "Backend restarted while this job was running. Please submit the video again."
            with JOBS_LOCK:
                _persist_jobs_locked()
except (OSError, ValueError, TypeError):
    JOBS = {}

WORKERS = ThreadPoolExecutor(max_workers=max(1, int(os.getenv("VIDEO_WORKERS", "1"))))

def _run_job(job_id: str, source_path: Path, options: dict):
    job_dir = JOB_ROOT / job_id
    with JOBS_LOCK:
        JOBS[job_id]["status"] = "processing"
        JOBS[job_id]["message"] = "Video is processing in the background."
        _persist_jobs_locked()
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
            _persist_jobs_locked()
    except Exception as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["status"] = "failed"
                JOBS[job_id]["message"] = str(exc)[:700]
                _persist_jobs_locked()
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
        _persist_jobs_locked()
    WORKERS.submit(_run_job, job_id, source_path, options)
    return {"job_id": job_id, "status": "queued", "message": "Upload complete. Processing will continue in the background.", "status_url": f"/api/jobs/{job_id}"}

@app.get("/api/jobs/{job_id}")
def get_background_job(job_id: str, _admin: dict = Depends(require_admin)):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found. This job record is not available on the current backend instance.")
        return {"job_id": job_id, **job}

@app.get("/api/jobs/{job_id}/download")
def download_background_job(job_id: str, _admin: dict = Depends(require_admin)):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found. This job record is not available on the current backend instance.")
        if job["status"] != "completed":
            raise HTTPException(409, "The ZIP is not ready yet.")
    zip_path = JOB_ROOT / job_id / "drama-entertainment-shorts.zip"
    if not zip_path.is_file():
        raise HTTPException(404, "Generated ZIP is no longer available.")
    return FileResponse(str(zip_path), media_type="application/zip", filename="drama-entertainment-shorts.zip")
