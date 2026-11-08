$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$EnvFile = Join-Path $Backend ".env"
$BackendPython = Join-Path $Backend ".venv\Scripts\python.exe"

if (-not (Test-Path $EnvFile) -or -not (Test-Path $BackendPython)) { throw "Run .\setup.ps1 first." }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) { throw "FFmpeg/FFprobe are not on PATH. Install them and reopen PowerShell." }

# Build the frontend once and run Next.js in production mode, not its development server.
Push-Location $Frontend
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed. Fix the build output before launching." }
} finally { Pop-Location }

$BackendCommand = 'Set-Location "' + $Backend + '"; Get-Content "' + $EnvFile + '" | ForEach-Object { $parts = $_ -split "=",2; if ($parts.Length -eq 2) { [Environment]::SetEnvironmentVariable($parts[0].Trim(),$parts[1],"Process") } }; & "' + $BackendPython + '" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1'
$FrontendCommand = 'Set-Location "' + $Frontend + '"; npm start -- --hostname 127.0.0.1'
Start-Process powershell.exe -ArgumentList @("-NoExit","-ExecutionPolicy","Bypass","-Command",$BackendCommand)
Start-Sleep -Seconds 2
Start-Process powershell.exe -ArgumentList @("-NoExit","-ExecutionPolicy","Bypass","-Command",$FrontendCommand)

Write-Host "Backend:  http://127.0.0.1:8000/health"
Write-Host "Frontend: http://127.0.0.1:3000"
Write-Host "Production-mode local launch started. Keep both terminal windows open." -ForegroundColor Green
