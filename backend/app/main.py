import os, shutil, subprocess, tempfile, zipfile, math
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
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
    return {"status": "ok"}

@app.post("/api/shorts")
async def shorts(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}:
        raise HTTPException(415, "Upload MP4, MOV, MKV, WEBM or M4V.")
    work = Path(tempfile.mkdtemp(prefix="drama-shorts-"))
    try:
        source = work / ("source" + ext)
        size = 0
        with source.open("wb") as out:
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
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(source)],
            capture_output=True, text=True
        )
        if probe.returncode:
            raise HTTPException(422, "Unable to read video. Check FFmpeg installation.")
        duration = float(probe.stdout.strip())
        if duration <= 0:
            raise HTTPException(422, "Invalid video duration.")

        clips = work / "clips"
        clips.mkdir()
        count = max(1, math.ceil(duration / 60))
        vf = (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,setsar=1,"
            "drawtext=text='Drama & Entertainment':fontcolor=white:"
            "fontsize=42:box=1:boxcolor=black@0.55:boxborderw=14:"
            "x=w-tw-44:y=h-th-54"
        )
        for i in range(count):
            start = i * 60
            length = min(60, duration - start)
            if length <= 0:
                continue
            output = clips / f"short_{i+1:03d}.mp4"
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", str(start), "-i", str(source), "-t", str(length),
                "-map", "0:v:0", "-map", "0:a:0?", "-vf", vf,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p", "-r", "30",
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                str(output)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode:
                raise HTTPException(422, "FFmpeg error: " + result.stderr[-1200:])

        archive = work / "drama-entertainment-shorts.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for clip in sorted(clips.glob("*.mp4")):
                z.write(clip, clip.name)
        return FileResponse(
            str(archive), media_type="application/zip",
            filename="drama-entertainment-shorts.zip",
            background=BackgroundTask(shutil.rmtree, work, ignore_errors=True)
        )
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise
    finally:
        await file.close()
