import os, shutil, subprocess, tempfile, zipfile, math, json, re
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

app = FastAPI(title="Drama & Entertainment Shorts Cutter")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if x.strip()],
    allow_methods=["*"], allow_headers=["*"]
)

@app.get("/health")
def health():
    return {"status": "ok", "captions": "local-faster-whisper", "emergency_llm_configured": bool(os.getenv("LLM_API_KEY") and os.getenv("LLM_API_URL") and os.getenv("LLM_MODEL_ID"))}

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

@app.post("/api/shorts")
async def shorts(
    file: UploadFile = File(...),
    captions_enabled: bool = Form(True),
    caption_language: str = Form("original"),
    caption_style: str = Form("auto"),
    caption_color: str = Form("white"),
    caption_size: str = Form("medium")
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}:
        raise HTTPException(415, "Upload MP4, MOV, MKV, WEBM or M4V.")
    if caption_language not in {"original", "english", "hindi"} or caption_style not in {"auto", "classic", "bold", "minimal"} or caption_color not in {"white", "yellow", "cyan", "pink"} or caption_size not in {"small", "medium", "large"}:
        raise HTTPException(400, "Invalid caption setting.")
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
        if captions_enabled:
            try:
                from faster_whisper import WhisperModel
                model_name = os.getenv("WHISPER_MODEL", "base")
                model = WhisperModel(model_name, device=os.getenv("WHISPER_DEVICE", "cpu"), compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"))
                task = "translate" if caption_language == "english" else "transcribe"
                recognized, info = model.transcribe(str(source), task=task, vad_filter=True, beam_size=3)
                segments = [(float(s.start), float(s.end), s.text.strip()) for s in recognized if s.text.strip()]
                if not segments: raise RuntimeError("No speech was detected. Try another video or turn captions off.")
                if caption_language == "hindi" and (info.language or "").lower() not in {"hi", "ur"}:
                    # This is the only condition that may invoke the optional LLM: local recognition succeeded,
                    # but local Whisper cannot translate non-Hindi speech into Hindi.
                    translated = emergency_translate([s[2] for s in segments], "Hindi")
                    segments = [(s[0], s[1], translated[i]) for i, s in enumerate(segments)]
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(422, "Automatic captions failed: " + str(exc)[:500] + ". Check backend dependencies/model download, or disable captions.") from exc

        clips = work / "clips"; clips.mkdir()
        count = max(1, math.ceil(duration / 60))
        color = {"white": "&H00FFFFFF", "yellow": "&H0000FFFF", "cyan": "&H00FFFF00", "pink": "&H00C0A0FF"}[caption_color]
        size_px = {"small": 42, "medium": 54, "large": 66}[caption_size]
        outline = 3 if caption_style in {"auto", "bold"} else 2
        if caption_style == "minimal": outline = 1
        for i in range(count):
            start = i * 60; length = min(60, duration - start)
            if length <= 0: continue
            output = clips / f"short_{i+1:03d}.mp4"
            filters = ["scale=1080:1920:force_original_aspect_ratio=increase", "crop=1080:1920", "setsar=1"]
            if captions_enabled:
                local = [(max(0, a-start), min(length, b-start), t) for a,b,t in segments if b > start and a < start+length]
                srt = work / f"captions_{i+1:03d}.srt"
                make_srt(local, srt)
                escaped = str(srt).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
                style = f"FontName=Arial,FontSize={size_px},PrimaryColour={color},OutlineColour=&H000000,BorderStyle=1,Outline={outline},Shadow=1,Alignment=2,MarginV=140"
                filters.append(f"subtitles='{escaped}':force_style='{style}'")
            filters.append("drawtext=text='Drama & Entertainment':fontcolor=white:fontsize=42:box=1:boxcolor=black@0.55:boxborderw=14:x=w-tw-44:y=h-th-54")
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start), "-i", str(source), "-t", str(length), "-map", "0:v:0", "-map", "0:a:0?", "-vf", ",".join(filters), "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode: raise HTTPException(422, "FFmpeg error: " + result.stderr[-1000:])
        archive = work / "drama-entertainment-shorts.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for clip in sorted(clips.glob("*.mp4")): z.write(clip, clip.name)
        return FileResponse(str(archive), media_type="application/zip", filename=archive.name, background=BackgroundTask(shutil.rmtree, work, ignore_errors=True))
    except HTTPException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(work, ignore_errors=True)
        raise HTTPException(500, "Processing failed: " + str(exc)[:400]) from exc
    finally:
        await file.close()
