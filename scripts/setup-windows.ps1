$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Refresh-Path {
  $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
  $user = [Environment]::GetEnvironmentVariable("Path", "User")
  $env:Path = "$machine;$user"
  $candidates = @("$env:LOCALAPPDATA\Programs\Python\Python312","$env:LOCALAPPDATA\Programs\Python\Python312\Scripts","$env:ProgramFiles\nodejs","$env:LOCALAPPDATA\Microsoft\WinGet\Links")
  foreach ($p in $candidates) { if (Test-Path $p) { $env:Path = "$p;$env:Path" } }
}
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw "winget is missing. Install or update App Installer from Microsoft Store, then rerun." }

Write-Host "Installing local prerequisites: Python 3.12, Node.js LTS and FFmpeg..." -ForegroundColor Cyan
$packages = @(
  @{ Id = "Python.Python.3.12"; Name = "Python" },
  @{ Id = "OpenJS.NodeJS.LTS"; Name = "Node" },
  @{ Id = "Gyan.FFmpeg.Shared"; Name = "FFmpeg" }
)
foreach ($pkg in $packages) {
  if ($pkg.Name -eq "Python" -and (Get-Command py -ErrorAction SilentlyContinue)) { & py -3.12 --version 2>$null | Out-Null; if ($LASTEXITCODE -eq 0) { continue } }
  if ($pkg.Name -eq "Node" -and (Get-Command node -ErrorAction SilentlyContinue)) { continue }
  if ($pkg.Name -eq "FFmpeg" -and (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { continue }
  winget install --id $pkg.Id -e --silent --accept-package-agreements --accept-source-agreements
  if ($LASTEXITCODE -ne 0) { throw "winget could not install $($pkg.Name). Install it manually and rerun." }
}
Refresh-Path
if (-not (Get-Command py -ErrorAction SilentlyContinue) -or -not (Get-Command node -ErrorAction SilentlyContinue) -or -not (Get-Command npm -ErrorAction SilentlyContinue) -or -not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
  throw "Python, Node/npm or FFmpeg/FFprobe is not on PATH. Restart PowerShell and rerun this setup."
}

$root = Join-Path $HOME "PCMDK369-60sec-local"
if (-not (Test-Path (Join-Path $root "backend\app\main.py"))) {
  $zip = Join-Path $env:TEMP "pcmdk369-60sec-local.zip"
  $extract = Join-Path $env:TEMP "pcmdk369-60sec-extract"
  Remove-Item $extract -Recurse -Force -ErrorAction SilentlyContinue
  Invoke-WebRequest -Uri "https://github.com/pcmdk369/60sec/archive/refs/heads/feature/windows-local-six-language.zip" -OutFile $zip
  Expand-Archive -Path $zip -DestinationPath $extract -Force
  $source = Join-Path $extract "60sec-feature-windows-local-six-language"
  if (-not (Test-Path $source)) { throw "The project archive did not contain the expected folder." }
  if (Test-Path $root) { Remove-Item $root -Recurse -Force }
  Move-Item $source $root
  Remove-Item $extract -Recurse -Force
}
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

Write-Host "Create your local admin login." -ForegroundColor Cyan
$adminUser = Read-Host "Admin username (default Admin)"
if ([string]::IsNullOrWhiteSpace($adminUser)) { $adminUser = "Admin" }
$securePassword = Read-Host "Create a strong admin password" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try { $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
$env:FRAMEFLOW_ADMIN_PASSWORD = $plainPassword
$authJson = & py -3.12 -c "import os,secrets,hashlib,json; p=os.environ['FRAMEFLOW_ADMIN_PASSWORD']; s=secrets.token_bytes(16); n=310000; h=hashlib.pbkdf2_hmac('sha256',p.encode(),s,n).hex(); print(json.dumps({'password_hash':'pbkdf2_sha256$'+str(n)+'$'+s.hex()+'$'+h,'session_secret':secrets.token_urlsafe(48)}))"
Remove-Item Env:FRAMEFLOW_ADMIN_PASSWORD
if ($LASTEXITCODE -ne 0 -or -not $authJson) { throw "Could not generate secure admin credentials." }
$auth = $authJson | ConvertFrom-Json

$envFile = Join-Path $backend ".env"
if (-not (Test-Path $envFile)) {
@"
ADMIN_USERNAME=$adminUser
ADMIN_PASSWORD_HASH=$($auth.password_hash)
SESSION_SECRET=$($auth.session_secret)
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
  Write-Host "Existing backend .env found; keeping existing settings and credentials." -ForegroundColor Yellow
}
"NEXT_PUBLIC_API_URL=http://127.0.0.1:8000" | Set-Content -Path (Join-Path $frontend ".env.local") -Encoding ASCII

Write-Host "Installing Python backend packages..." -ForegroundColor Cyan
if (-not (Test-Path (Join-Path $backend ".venv\Scripts\python.exe"))) {
  & py -3.12 -m venv (Join-Path $backend ".venv")
  if ($LASTEXITCODE -ne 0) { throw "Python virtual environment creation failed." }
}
& (Join-Path $backend ".venv\Scripts\python.exe") -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
& (Join-Path $backend ".venv\Scripts\python.exe") -m pip install -r (Join-Path $backend "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Backend package installation failed." }

Write-Host "Installing frontend packages..." -ForegroundColor Cyan
Push-Location $frontend
try { npm install; if ($LASTEXITCODE -ne 0) { throw "npm install failed." } } finally { Pop-Location }

$backendStart = Join-Path $root "start-backend.ps1"
$frontendStart = Join-Path $root "start-frontend.ps1"
$backendQuoted = $backend.Replace("'","''")
$frontendQuoted = $frontend.Replace("'","''")
@("Set-Location -LiteralPath '$backendQuoted'","& '.\.venv\Scripts\Activate.ps1'","uvicorn app.main:app --host 127.0.0.1 --port 8000") | Set-Content -Path $backendStart -Encoding UTF8
@("Set-Location -LiteralPath '$frontendQuoted'","npm run dev -- --hostname 127.0.0.1") | Set-Content -Path $frontendStart -Encoding UTF8
Start-Process powershell.exe -ArgumentList "-NoExit -ExecutionPolicy Bypass -File `"$backendStart`""
Start-Sleep -Seconds 3
Start-Process powershell.exe -ArgumentList "-NoExit -ExecutionPolicy Bypass -File `"$frontendStart`""

Write-Host ""
Write-Host "PCMDK369 60sec local setup finished." -ForegroundColor Green
Write-Host "App: http://127.0.0.1:3000"
Write-Host "Backend health: http://127.0.0.1:8000/health"
Write-Host "Local project: $root"
Write-Host "Local backend settings: $envFile"
Write-Host "Cutting, watermarking and speech recognition run on this PC. Internet/API access is only needed for an explicitly selected non-English translation when the detected spoken language differs from the target."
Write-Host "To enable optional translation, add LLMS_ENGINE_API_KEY, LLMS_ENGINE_API_URL and LLMS_ENGINE_MODEL to backend\.env, then restart the backend window."
