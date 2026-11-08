$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$EnvFile = Join-Path $Backend ".env"
$BackendPython = Join-Path $Backend ".venv\Scripts\python.exe"
if (-not (Test-Path $EnvFile) -or -not (Test-Path $BackendPython)) { throw "Run .\setup.ps1 first." }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) { throw "FFmpeg/FFprobe are not on PATH. Install them and reopen PowerShell." }
$BackendCommand = 'Set-Location "' + $Backend + '"; Get-Content "' + $EnvFile + '" | ForEach-Object { $parts = $_.Split("=",2); if ($parts.Length -eq 2) { [Environment]::SetEnvironmentVariable($parts[0],$parts[1],"Process") } }; & "' + $BackendPython + '" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1'
$FrontendCommand = 'Set-Location "' + $Frontend + '"; npm run dev -- --hostname 127.0.0.1'
Start-Process powershell.exe -ArgumentList @("-NoExit","-ExecutionPolicy","Bypass","-Command",$BackendCommand)
Start-Sleep -Seconds 2
Start-Process powershell.exe -ArgumentList @("-NoExit","-ExecutionPolicy","Bypass","-Command",$FrontendCommand)
Write-Host "Backend:  http://127.0.0.1:8000/health"
Write-Host "Frontend: http://127.0.0.1:3000"
Write-Host "Keep both terminal windows open while using the app." -ForegroundColor Green
