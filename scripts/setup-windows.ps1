$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Refresh-Path {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
    $extra = @("$env:LOCALAPPDATA\Programs\Python\Python312", "$env:LOCALAPPDATA\Programs\Python\Python312\Scripts", "$env:ProgramFiles\nodejs", "$env:LOCALAPPDATA\Microsoft\WinGet\Links")
    foreach ($folder in $extra) { if (Test-Path $folder) { $env:Path = "$folder;$env:Path" } }
}

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "winget is missing. Install or update App Installer from Microsoft Store, then run this script again."
}

Write-Host "Installing local prerequisites..." -ForegroundColor Cyan
$packages = @(
    @{ Id = "Python.Python.3.12"; Name = "Python 3.12" },
    @{ Id = "OpenJS.NodeJS.LTS"; Name = "Node.js LTS" },
    @{ Id = "Gyan.FFmpeg.Shared"; Name = "FFmpeg" }
)
foreach ($package in $packages) {
    $install = $true
    if ($package.Name -eq "Python 3.12" -and (Get-Command py -ErrorAction SilentlyContinue)) {
        & py -3.12 --version 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $install = $false }
    }
    if ($package.Name -eq "Node.js LTS" -and (Get-Command node -ErrorAction SilentlyContinue)) { $install = $false }
    if ($package.Name -eq "FFmpeg" -and (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { $install = $false }
    if ($install) {
        winget install --id $package.Id -e --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw "Could not install $($package.Name). Install it manually and run this script again." }
    }
}
Refresh-Path

foreach ($name in @("py", "node", "npm", "ffmpeg", "ffprobe")) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        throw "$name is not available on PATH yet. Restart PowerShell and run this script again."
    }
}
& py -3.12 --version
if ($LASTEXITCODE -ne 0) { throw "Python 3.12 is required. Install Python 3.12 and rerun." }

$root = Join-Path $HOME "PCMDK369-60sec-local"
$zipPath = Join-Path $env:TEMP "pcmdk369-60sec-local.zip"
$extractPath = Join-Path $env:TEMP "pcmdk369-60sec-extract"
if (Test-Path $extractPath) { Remove-Item $extractPath -Recurse -Force }
Write-Host "Downloading the latest local application..." -ForegroundColor Cyan
Invoke-WebRequest -Uri "https://github.com/pcmdk369/60sec/archive/refs/heads/feature/windows-local-six-language.zip" -OutFile $zipPath
Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force
$source = Get-ChildItem -Path $extractPath -Directory | Select-Object -First 1
if (-not $source -or -not (Test-Path (Join-Path $source.FullName "backend\app\main.py"))) {
    throw "The downloaded repository archive is invalid or missing backend/app/main.py."
}
New-Item -ItemType Directory -Path $root -Force | Out-Null
Copy-Item -Path (Join-Path $source.FullName "*") -Destination $root -Recurse -Force
Remove-Item $extractPath -Recurse -Force
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

$envFile = Join-Path $backend ".env"
if (-not (Test-Path $envFile)) {
    Write-Host "Create your local admin login." -ForegroundColor Cyan
    $adminUser = Read-Host "Admin username (default Admin)"
    if ([string]::IsNullOrWhiteSpace($adminUser)) { $adminUser = "Admin" }
    $securePassword = Read-Host "Create a strong admin password" -AsSecureString
    $passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
    try { $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer) }
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $salt = New-Object byte[] 16
    $secretBytes = New-Object byte[] 48
    $rng.GetBytes($salt)
    $rng.GetBytes($secretBytes)
    $rng.Dispose()
    $iterations = 310000
    $derive = [System.Security.Cryptography.Rfc2898DeriveBytes]::new($plainPassword, $salt, $iterations, [System.Security.Cryptography.HashAlgorithmName]::SHA256)
    try { $digest = $derive.GetBytes(32) }
    finally { $derive.Dispose(); $plainPassword = $null }
    $saltHex = [BitConverter]::ToString($salt).Replace("-","").ToLowerInvariant()
    $digestHex = [BitConverter]::ToString($digest).Replace("-","").ToLowerInvariant()
    $dollar = [char]36
    $passwordHash = "pbkdf2_sha256" + $dollar + $iterations + $dollar + $saltHex + $dollar + $digestHex
    $sessionSecret = [Convert]::ToBase64String($secretBytes).TrimEnd('=').Replace('+','-').Replace('/','_')
@"
ADMIN_USERNAME=$adminUser
ADMIN_PASSWORD_HASH=$passwordHash
SESSION_SECRET=$sessionSecret
CORS_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
VIDEO_WORKERS=1
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
LLMS_ENGINE_API_KEY=
LLMS_ENGINE_API_URL=
LLMS_ENGINE_MODEL=
"@ | Set-Content -Path $envFile -Encoding ASCII
} else {
    Write-Host "Existing local admin credentials and LLM settings will be preserved." -ForegroundColor Yellow
}
"NEXT_PUBLIC_API_URL=http://127.0.0.1:8000" | Set-Content -Path (Join-Path $frontend ".env.local") -Encoding ASCII

Write-Host "Preparing Python backend..." -ForegroundColor Cyan
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    & py -3.12 -m venv (Join-Path $backend ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Python virtual environment." }
}
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
& $venvPython -m pip install -r (Join-Path $backend "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Backend dependency installation failed." }

Write-Host "Preparing Next.js frontend..." -ForegroundColor Cyan
Push-Location $frontend
try { npm install; if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." } }
finally { Pop-Location }

$backendStart = Join-Path $root "start-backend.ps1"
$frontendStart = Join-Path $root "start-frontend.ps1"
$backendQuoted = $backend.Replace("'","''")
$frontendQuoted = $frontend.Replace("'","''")
@"
Set-Location -LiteralPath '$backendQuoted'
& '.\.venv\Scripts\Activate.ps1'
uvicorn app.main:app --host 127.0.0.1 --port 8000
"@ | Set-Content -Path $backendStart -Encoding UTF8
@"
Set-Location -LiteralPath '$frontendQuoted'
npm run dev -- --hostname 127.0.0.1
"@ | Set-Content -Path $frontendStart -Encoding UTF8

$backendArgs = '-NoExit -ExecutionPolicy Bypass -File "' + $backendStart + '"'
$frontendArgs = '-NoExit -ExecutionPolicy Bypass -File "' + $frontendStart + '"'
Start-Process -FilePath "powershell.exe" -ArgumentList $backendArgs
Start-Sleep -Seconds 2
Start-Process -FilePath "powershell.exe" -ArgumentList $frontendArgs

Write-Host ""
Write-Host "PCMDK369 60sec local setup completed." -ForegroundColor Green
Write-Host "Application: http://127.0.0.1:3000"
Write-Host "Backend health: http://127.0.0.1:8000/health"
Write-Host "Local project folder: $root"
Write-Host "Backend settings: $envFile"
Write-Host "Video cutting, watermarking and Whisper speech recognition run locally. The optional LLM is only used for selected Hindi, Spanish, Chinese, Thai or Indonesian translations when needed."
Write-Host "To enable translation, add LLMS_ENGINE_API_KEY, LLMS_ENGINE_API_URL and LLMS_ENGINE_MODEL to backend\.env, then restart the backend window."
