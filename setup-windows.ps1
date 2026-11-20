$ErrorActionPreference = "Stop"

function Refresh-Path {
  $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
  $user = [Environment]::GetEnvironmentVariable("Path", "User")
  $env:Path = "$machine;$user"
}

function Ensure-WingetPackage([string]$Id, [string]$Name) {
  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "winget is unavailable. Install App Installer, then rerun this script."
  }
  Write-Host "Installing $Name..." -ForegroundColor Cyan
  winget install --id $Id --exact --silent --accept-package-agreements --accept-source-agreements
  if ($LASTEXITCODE -ne 0) { throw "winget could not install $Name. Install it manually and rerun." }
  Refresh-Path
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Ensure-WingetPackage "OpenJS.NodeJS.LTS" "Node.js LTS" }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Refresh-Path }
if (Get-Command py -ErrorAction SilentlyContinue) {
  & py -3.11 --version 2>$null
  if ($LASTEXITCODE -ne 0) { Ensure-WingetPackage "Python.Python.3.11" "Python 3.11" }
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
  $pythonVersionText = & python --version
  if ($pythonVersionText -notmatch "3\\.(1[1-9]|[2-9][0-9])") { Ensure-WingetPackage "Python.Python.3.11" "Python 3.11" }
} else {
  Ensure-WingetPackage "Python.Python.3.11" "Python 3.11"
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Ensure-WingetPackage "Gyan.FFmpeg.Shared" "FFmpeg" }

$python = if (Get-Command py -ErrorAction SilentlyContinue) { (Get-Command py).Source } else { (Get-Command python).Source }
$pythonArgs = if ((Split-Path $python -Leaf) -eq "py.exe") { @("-3.11") } else { @() }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "npm is not on PATH. Close this window, open PowerShell again, and rerun setup-windows.ps1." }
if (-not (Get-Command ffprobe -ErrorAction SilentlyContinue)) { throw "ffprobe is not on PATH. Reopen PowerShell after FFmpeg installation, then rerun setup-windows.ps1." }

$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$venv = Join-Path $backend ".venv"
if (-not (Test-Path $venv)) { & $python @pythonArgs -m venv $venv }
$venvPython = Join-Path $venv "Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $backend "requirements.txt")

Push-Location $frontend
npm install
if ($LASTEXITCODE -ne 0) { throw "npm install failed." }
Pop-Location

$alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%*-_"
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$adminPassword = -join (1..24 | ForEach-Object { $alphabet[(Get-Random -Minimum 0 -Maximum $alphabet.Length)] })
$saltBytes = New-Object byte[] 16
$rng.GetBytes($saltBytes)
$salt = ([BitConverter]::ToString($saltBytes)).Replace("-", "").ToLowerInvariant()
$passwordHash = & $venvPython -c 'import hashlib,sys; print("pbkdf2_sha256$310000$"+sys.argv[2]+"$"+hashlib.pbkdf2_hmac("sha256",sys.argv[1].encode(),bytes.fromhex(sys.argv[2]),310000).hex())' $adminPassword $salt
$secretBytes = New-Object byte[] 48
$rng.GetBytes($secretBytes)
$sessionSecret = ([BitConverter]::ToString($secretBytes)).Replace("-", "").ToLowerInvariant()
$rng.Dispose()

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$backendEnv = @"
ADMIN_USERNAME=Admin
ADMIN_PASSWORD_HASH=$passwordHash
SESSION_SECRET=$sessionSecret
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
VIDEO_WORKERS=1
JOB_STORAGE_DIR=$backend
"@
[System.IO.File]::WriteAllText((Join-Path $backend ".env"), $backendEnv, $utf8NoBom)
[System.IO.File]::WriteAllText((Join-Path $frontend ".env.local"), "NEXT_PUBLIC_API_URL=http://127.0.0.1:8000", $utf8NoBom)
@"
FRAMEFLOW LOCAL ADMIN
Username: Admin
Password: $adminPassword

Keep this file private. Do not upload it or commit it to Git.
"@ | Set-Content -Path (Join-Path $root "local-admin-credentials.txt") -Encoding UTF8

$backendEscaped = $backend.Replace("'", "''")
$frontendEscaped = $frontend.Replace("'", "''")
$backendCommand = "Set-Location '$backendEscaped'; & '.venv\Scripts\Activate.ps1'; uvicorn app.main:app --host 127.0.0.1 --port 8000"
$frontendCommand = "Set-Location '$frontendEscaped'; npm run dev -- --hostname 127.0.0.1"
Start-Process powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand)
Start-Sleep -Seconds 3
Start-Process powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $frontendCommand)

Write-Host ""
Write-Host "FRAMEFLOW setup completed. Local servers are starting." -ForegroundColor Green
Write-Host "Website: http://localhost:3000"
Write-Host "Backend health: http://127.0.0.1:8000/health"
Write-Host "Admin credentials saved in local-admin-credentials.txt"
Write-Host "The first caption run may download the Whisper model and Argos translation packages."
