$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
Write-Host "FRAMEFLOW / 60sec - Windows local setup" -ForegroundColor Cyan
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw "Install Node.js 20 LTS or newer, then reopen PowerShell." }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "npm was not found. Reinstall Node.js." }
$Python = $null
foreach ($Candidate in @(@("py", "-3.12"), @("py", "-3.11"), @("python"))) {
    try {
        if ($Candidate.Count -eq 2) { & $Candidate[0] $Candidate[1] --version *> $null } else { & $Candidate[0] --version *> $null }
        if ($LASTEXITCODE -eq 0) { $Python = $Candidate; break }
    } catch {}
}
if (-not $Python) { throw "Python 3.11 or 3.12 is required. Install Python and enable the Python Launcher." }
$VenvPython = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Push-Location (Join-Path $Root "backend")
    try { if ($Python.Count -eq 2) { & $Python[0] $Python[1] -m venv .venv } else { & $Python[0] -m venv .venv }; if ($LASTEXITCODE -ne 0) { throw "Could not create Python virtual environment." } }
    finally { Pop-Location }
}
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
& $VenvPython -m pip install -r (Join-Path $Root "backend\requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Backend dependency installation failed." }
Push-Location (Join-Path $Root "frontend")
try { npm install; if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." } }
finally { Pop-Location }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) { winget install --id Gyan.FFmpeg.Shared --exact --accept-package-agreements --accept-source-agreements; Write-Host "If FFmpeg is not detected, reopen PowerShell and rerun setup." -ForegroundColor Yellow }
    else { throw "Install FFmpeg and FFprobe, add their bin directory to PATH, then rerun setup." }
}
$BackendEnv = Join-Path $Root "backend\.env"
if (-not (Test-Path $BackendEnv)) {
    $AdminUser = Read-Host "Choose local admin username"
    if ([string]::IsNullOrWhiteSpace($AdminUser)) { $AdminUser = "Admin" }
    $HashOutput = & $VenvPython (Join-Path $Root "backend\scripts\generate_admin_password_hash.py")
    if ($LASTEXITCODE -ne 0 -or -not $HashOutput) { throw "Could not create admin password hash." }
    $Secret = (& $VenvPython -c "import secrets; print(secrets.token_urlsafe(48))").Trim()
    @("ADMIN_USERNAME=$AdminUser", $HashOutput.Trim(), "SESSION_SECRET=$Secret", "CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000", "LLM_API_KEY=", "LLM_API_URL=", "LLM_MODEL_ID=") | Set-Content -Path $BackendEnv -Encoding utf8
    Write-Host "Created private backend/.env." -ForegroundColor Green
}
$FrontendEnv = Join-Path $Root "frontend\.env.local"
if (-not (Test-Path $FrontendEnv)) { "NEXT_PUBLIC_API_URL=http://127.0.0.1:8000" | Set-Content -Path $FrontendEnv -Encoding ascii }
Write-Host "Setup finished. Run .\start.ps1 and open http://127.0.0.1:3000" -ForegroundColor Green
