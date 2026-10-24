# Drama & Entertainment Shorts Cutter

## Requirements
- Node.js 20+
- Python 3.10+
- FFmpeg and FFprobe installed and available in PATH

## Install FFmpeg
Ubuntu/Debian: `sudo apt-get update && sudo apt-get install -y ffmpeg`
macOS: `brew install ffmpeg`
Windows: install FFmpeg and add its `bin` folder to PATH.
Termux: `pkg install ffmpeg python nodejs`

## Start backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Start frontend
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000, choose a video, and click CREATE SHORTS.
