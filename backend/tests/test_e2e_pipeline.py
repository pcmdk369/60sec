import hashlib
import io
import json
import subprocess
import time
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient


def test_authenticated_video_to_zip_pipeline(tmp_path, monkeypatch):
    password = "E2E-Test-Password-Only"
    salt = "0123456789abcdef0123456789abcdef"
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 310000).hex()
    monkeypatch.setenv("ADMIN_USERNAME", "E2EAdmin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", f"pbkdf2_sha256$310000$" + salt + "$" + digest)
    monkeypatch.setenv("SESSION_SECRET", "e2e-test-session-secret-0123456789abcdef")
    monkeypatch.setenv("JOB_STORAGE_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("VIDEO_WORKERS", "1")

    import app.main as main

    client = TestClient(main.app)
    health = client.get("/health")
    assert health.status_code == 200
    assert set(health.json()["caption_languages"]) >= {
        "english", "hindi", "burmese", "thai", "spanish", "french"
    }
    assert client.get("/api/jobs/not-a-real-job").status_code == 401

    login = client.post("/api/auth/login", json={"username": "E2EAdmin", "password": password})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    session = client.get("/api/auth/session", headers=headers)
    assert session.status_code == 200
    assert session.json()["username"] == "E2EAdmin"

    source = tmp_path / "e2e-source.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=24:duration=65",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=65",
            "-shortest", "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
        ],
        check=True,
        timeout=90,
    )

    with source.open("rb") as handle:
        queued = client.post(
            "/api/jobs",
            headers=headers,
            files={"file": ("e2e-source.mp4", handle, "video/mp4")},
            data={
                "captions_enabled": "false",
                "caption_language": "original",
                "caption_style": "auto",
                "caption_color": "white",
                "caption_size": "medium",
                "output_resolution": "480p",
                "encoding_priority": "fast",
                "framing": "portrait",
            },
        )
    assert queued.status_code == 202, queued.text
    job_id = queued.json()["job_id"]

    deadline = time.time() + 150
    job = None
    while time.time() < deadline:
        response = client.get(f"/api/jobs/{job_id}", headers=headers)
        assert response.status_code == 200, response.text
        job = response.json()
        if job["status"] in {"completed", "failed"}:
            break
        time.sleep(0.5)

    assert job and job["status"] == "completed", json.dumps(job, indent=2)
    archive_response = client.get(f"/api/jobs/{job_id}/download", headers=headers)
    assert archive_response.status_code == 200
    assert archive_response.headers["content-type"].startswith("application/zip")

    with zipfile.ZipFile(io.BytesIO(archive_response.content)) as archive:
        clips = sorted(name for name in archive.namelist() if name.endswith(".mp4"))
        assert clips == ["short_001.mp4", "short_002.mp4"]
        for name, expected_duration in zip(clips, (60, 5)):
            clip_path = tmp_path / name
            clip_path.write_bytes(archive.read(name))
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", str(clip_path),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            assert abs(float(probe.stdout.strip()) - expected_duration) < 0.8

    source_code = Path(main.__file__).read_text(encoding="utf-8")
    assert 'watermark_file.write_text("Drama Clip AI"' in source_code
