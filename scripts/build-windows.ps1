# Slim BeanRead Windows bundle — PyInstaller one-dir + zip installer.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Venv = Join-Path $Root ".venv-pack"
$Py = Join-Path $Venv "Scripts\python.exe"
$Pip = Join-Path $Venv "Scripts\pip.exe"

function Fail($msg) { Write-Error "ERROR: $msg" }

if (Test-Path (Join-Path $Root ".env.example")) {
    $envEx = Get-Content (Join-Path $Root ".env.example") -Raw
    if ($envEx -match 'LLM_API_KEY=sk-') { Fail ".env.example contains a real API key — use placeholder only" }
}

if (-not (Test-Path $Py)) {
    Write-Host "Creating pack venv at .venv-pack ..."
    python -m venv $Venv
}

Write-Host "Installing pack dependencies ..."
& $Pip install -q -U pip
& $Pip install -q -r requirements-pack.txt
& $Pip install -q pyinstaller

Write-Host "Building (slim) ..."
if (Test-Path (Join-Path $Root "build")) { Remove-Item -Recurse -Force (Join-Path $Root "build") }
if (Test-Path (Join-Path $Root "dist")) { Remove-Item -Recurse -Force (Join-Path $Root "dist") }

& $Py -m PyInstaller --noconfirm --clean beanread-windows.spec

$AppDir = Join-Path $Root "dist\BeanRead"
$Exe = Join-Path $AppDir "BeanRead.exe"
if (-not (Test-Path $Exe)) { Fail "missing $Exe" }

$Version = & $Py -c "from book_compiler import __version__; print(__version__)"
$ZipName = "BeanRead-$Version-Windows.zip"
$ZipPath = Join-Path $Root "dist\$ZipName"

Write-Host "Creating installer zip ..."
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path $AppDir -DestinationPath $ZipPath -Force

$Size = [math]::Round((Get-Item $ZipPath).Length / 1MB, 1)
Write-Host ""
Write-Host "Built: $ZipPath (${Size} MB)"
Write-Host "Usage: unzip, open dist\BeanRead\BeanRead.exe"
Write-Host "Data:  %LOCALAPPDATA%\BeanRead\"
Write-Host "Note:  Users configure API Key in Settings; dev .env is not bundled."
