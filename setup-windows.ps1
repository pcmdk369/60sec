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
    $installExit = $LASTEXITCODE
    Refresh-Path
    if ($installExit -ne 0) {
        throw "winget could not install $Name (exit code $installExit). Install it manually and rerun."
    }
}

function Resolve-Python311 {
    Refresh-Path
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        $candidate = & $launcher.Source -3.11 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $candidate -and (Test-Path $candidate.Trim())) {
            return $candidate.Trim()
        }
    }
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $candidate = & $pythonCommand.Source -c "import sys; print(sys.executable if sys.version_info >= (3,11) else '')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $candidate -and (Test-Path $candidate.Trim())) {
            return $candidate.Trim()
        }
    }
    return $null
}

function Invoke-Checked([string]$Executable, [string[]]$Arguments, [string]$Task) {
    Write-Host $Task -ForegroundColor Cyan
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Task failed with exit code $LASTEXITCODE."
    }
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
Write-Host "===== PCMDK369 60sec Windows setup =====" -ForegroundColor Cyan

if (-not (Get-Command node.exe -ErrorAction SilentlyContinue)) {
    Ensure-WingetPackage "OpenJS.NodeJS.LTS" "Node.js LTS"
}
Refresh-Path

$pythonExe = Resolve-Python311
if (-not $pythonExe) {
    Ensure-WingetPackage "Python.Python.3.11" "Python 3.11"
    $pythonExe = Resolve-Python311
}
if (-not $pythonExe) {
    throw "Python 3.11 was installed but could not be located. Close PowerShell, reopen it, and rerun this script."
}

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw "npm is not available on PATH. Restart PowerShell after installing Node.js, then rerun this script."
}

if (-not (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue)) {
    Ensure-WingetPackage "Gyan.FFmpeg.Shared" "FFmpeg"
}
Refresh-Path
if (-not (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe.exe -ErrorAction SilentlyContinue)) {
    throw "FFmpeg/FFprobe are not available on PATH. Restart PowerShell and rerun this script."
}

$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$venv = Join-Path $backend ".venv"
$venvPython = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Invoke-Checked $pythonExe @("-m", "venv", $venv) "Creating Python virtual environment"
}
Invoke-Checked $venvPython @("-m", "pip", "install", "--upgrade", "pip") "Upgrading pip"
Invoke-Checked $venvPython @("-m", "pip", "install", "-r", (Join-Path $backend "requirements.txt")) "Installing backend dependencies"

Push-Location $frontend
try {
    Invoke-Checked (Get-Command npm.cmd).Source @("install") "Installing frontend dependencies"
} finally {
    Pop-Location
}

$alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%*-_"
$adminPassword = -join (1..24 | ForEach-Object { $alphabet[(Get-Random -Minimum 0 -Maximum $alphabet.Length)] })
$saltBytes = New-Object byte[] 16
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($saltBytes)
$salt = ([BitConverter]::ToString($saltBytes)).Replace("-", "").ToLowerInvariant()
$passwordHash = & $venvPython -c 'import hashlib,sys; print("pbkdf2_sha256$310000$"+sys.argv[2]+"$"+hashlib.pbkdf2_hmac("sha256",sys.argv[1].encode(),bytes.fromhex(sys.argv[2]),310000).hex())' $adminPassword $salt
if ($LASTEXITCODE -ne 0 -or -not $passwordHash) {
    throw "Could not generate the local admin password hash."
}
$secretBytes = New-Object byte[] 48
$rng.GetBytes($secretBytes)
$sessionSecret = ([BitConverter]::ToString($secretBytes)).Replace("-", "").ToLowerInvariant()
$rng.Dispose()

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
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
PCMDK369 60sec LOCAL ADMIN
Username: Admin
Password: $adminPassword

Keep this file private. Do not upload it or commit it to Git.
"@ | Set-Content -Path (Join-Path $root "local-admin-credentials.txt") -Encoding UTF8

$backendEscaped = $backend.Replace("'", "''")
$frontendEscaped = $frontend.Replace("'", "''")
$venvPythonEscaped = $venvPython.Replace("'", "''")
$backendCommand = "Set-Location '$backendEscaped'; & '$venvPythonEscaped' -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
$frontendCommand = "Set-Location '$frontendEscaped'; npm run dev -- --hostname 127.0.0.1"

Start-Process powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand)
Start-Sleep -Seconds 4
Start-Process powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $frontendCommand)

Write-Host "Waiting for backend health check..." -ForegroundColor Cyan
$backendHealthy = $false
for ($attempt = 1; $attempt -le 20; $attempt++) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 3
        if ($health.status -eq "ok") {
            $backendHealthy = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}

Write-Host "===== SETUP RESULT =====" -ForegroundColor Cyan
if ($backendHealthy) {
    Write-Host "Backend health: PASS" -ForegroundColor Green
} else {
    Write-Warning "Backend health check did not pass yet. Inspect the backend PowerShell window."
}
Write-Host "Frontend: http://127.0.0.1:3000"
Write-Host "Backend:  http://127.0.0.1:8000"
Write-Host "API docs: http://127.0.0.1:8000/docs"
Write-Host "Admin credentials: $root\local-admin-credentials.txt"
Write-Host "Keep the credentials file private."
