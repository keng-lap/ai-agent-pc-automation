$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot
$python = if (Test-Path (Join-Path $repoRoot ".venv\Scripts\python.exe")) { Join-Path $repoRoot ".venv\Scripts\python.exe" } else { (Get-Command python -ErrorAction Stop).Source }
& $python -m pip install -e "src/backend[build]"
if ($LASTEXITCODE -ne 0) { throw "Backend build dependencies failed." }
$dist = Join-Path $repoRoot "dist"
$work = Join-Path $repoRoot "build\pyinstaller-backend"
if (Test-Path $dist) { Remove-Item $dist -Recurse -Force }
if (Test-Path $work) { Remove-Item $work -Recurse -Force }
& $python -m PyInstaller --noconfirm --clean --onefile --name AgentBackend --paths "src/backend" --collect-all fastapi --collect-all starlette --collect-all uvicorn --collect-all google.genai --collect-all google.auth --collect-all qrcode --collect-all PIL --hidden-import agent_backend.main --hidden-import win32timezone --distpath $dist --workpath $work "src/backend/agent_backend/__main__.py"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller backend packaging failed." }
$exe = Join-Path $dist "AgentBackend.exe"
if (-not (Test-Path $exe)) { throw "Packaged Backend executable was not produced." }
$hash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
Write-Host "Backend package ready: $exe"
Write-Host "SHA-256: $hash"
Write-Warning "This build is unsigned. Do not provision it or use it as a trusted Helper authorization authority until signed with the enrolled project Code Signing certificate and installed at the protected Program Files path."
