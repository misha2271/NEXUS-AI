# NEXUS AI v0.3 Windows builder - no GitHub or Git required.
# Uses an already installed Python 3.11-3.13 or installs Python 3.11 via winget.
# Python packages download from PyPI. Actual Windows builds run on this PC.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'Continue'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $root

function Test-Python([string]$exe, [string[]]$prefix = @()) {
    if (-not $exe) { return $false }
    try {
        $v = & $exe @prefix -c "import sys; print('%d.%d:%d' % (sys.version_info.major,sys.version_info.minor,sys.maxsize > 2**32))" 2>$null
        if ($LASTEXITCODE -ne 0) { return $false }
        return $v -match '^3\.(11|12|13):1$'
    } catch { return $false }
}

if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64' -and $env:PROCESSOR_ARCHITEW6432 -ne 'AMD64') {
    throw 'This builder requires x64 Windows.'
}

Write-Host '[1/4] Finding Python 3.11-3.13 x64...' -ForegroundColor Cyan
$python = $null
$pythonArgs = @()
$launcher = Get-Command py.exe -ErrorAction SilentlyContinue
if ($launcher) {
    foreach ($v in @('3.11','3.12','3.13')) {
        if (Test-Python $launcher.Source @("-$v")) {
            $python = $launcher.Source; $pythonArgs = @("-$v"); break
        }
    }
}
if (-not $python) {
    foreach ($candidate in @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
        'python.exe'
    )) {
        if (Test-Python $candidate) { $python = $candidate; break }
    }
}
if (-not $python) {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw 'No suitable Python was found, and winget is unavailable. Install Python 3.11 from python.org and retry.'
    }
    Write-Host 'Python is missing. Installing official Python 3.11 using winget...' -ForegroundColor Yellow
    & $winget.Source install --id Python.Python.3.11 --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw "winget installation failed (exit $LASTEXITCODE)." }
    $candidate = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'
    if (Test-Python $candidate) { $python = $candidate }
    if (-not $python -and $launcher -and (Test-Python $launcher.Source @('-3.11'))) {
        $python = $launcher.Source; $pythonArgs = @('-3.11')
    }
    if (-not $python) { throw 'Python was installed but not found. Restart Windows and run this script again.' }
}

$venvDir = Join-Path $root '.build-tools\venv-no-github'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
Write-Host '[2/4] Creating project-specific Python environment...' -ForegroundColor Cyan
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $python @pythonArgs -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python virtual environment.' }
}
Write-Host '[3/4] Installing PyInstaller, PySide6 and other packages from PyPI...' -ForegroundColor Cyan
& $venvPython -m pip --disable-pip-version-check install --retries 2 --timeout 25 -e '.[freeze,nvidia]'
if ($LASTEXITCODE -ne 0) { throw 'Package installation failed. Check access to pypi.org and files.pythonhosted.org.' }
Write-Host '[4/4] Building and smoke-testing both Windows executables...' -ForegroundColor Cyan
& $venvPython scripts\build_windows.py --mode both
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build or Windows smoke tests failed.' }
if (-not (Test-Path -LiteralPath 'dist\NEXUS-AI.exe') -or -not (Test-Path -LiteralPath 'dist\NEXUS-AI-Portable.zip')) {
    throw 'Expected output files are missing.'
}
Write-Host 'SUCCESS! Files are in the dist folder.' -ForegroundColor Green
