# Native Windows builder. No preinstalled Python, administrator account, or PATH
# changes are required. All downloaded tools stay in this checkout's .build-tools.
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Invoke-NexusCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Executable $($Arguments -join ' ')"
    }
}

function Get-UvChecksum {
    param(
        [Parameter(Mandatory = $true)]$Release,
        [Parameter(Mandatory = $true)]$Asset,
        [Parameter(Mandatory = $true)]$Headers
    )
    $digestProperty = $Asset.PSObject.Properties['digest']
    if ($null -ne $digestProperty -and [string]$digestProperty.Value -match '^sha256:([0-9a-fA-F]{64})$') {
        return $Matches[1].ToLowerInvariant()
    }
    $checksumAssets = @($Release.assets | Where-Object { $_.name -eq ($Asset.name + '.sha256') })
    if ($checksumAssets.Count -ne 1) {
        throw 'The official uv release has no SHA256 digest. Refusing to run an unverified download.'
    }
    $response = Invoke-WebRequest -UseBasicParsing -Headers $Headers -Uri $checksumAssets[0].browser_download_url
    if ($response.Content -is [byte[]]) {
        $checksumText = [Text.Encoding]::UTF8.GetString($response.Content)
    }
    else {
        $checksumText = [string]$response.Content
    }
    if ($checksumText -notmatch '(?im)^([0-9a-fA-F]{64})(?:\s|$)') {
        throw 'The official uv checksum file did not contain a valid SHA256 digest.'
    }
    return $Matches[1].ToLowerInvariant()
}

$locationChanged = $false
try {
    if ($env:OS -ne 'Windows_NT') {
        throw 'This builder must run on native x64 Windows. It does not cross-compile from Linux.'
    }
    if (-not [Environment]::Is64BitProcess) {
        throw 'Run this builder with 64-bit Windows PowerShell on x64 Windows.'
    }
    $nativeArchitecture = $env:PROCESSOR_ARCHITEW6432
    if ([string]::IsNullOrWhiteSpace($nativeArchitecture)) {
        $nativeArchitecture = $env:PROCESSOR_ARCHITECTURE
    }
    if ($nativeArchitecture -ne 'AMD64') {
        throw 'This build targets x64 Windows; ARM and 32-bit systems are not supported.'
    }

    # Windows PowerShell 5.1 can otherwise inherit obsolete TLS defaults.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $sourceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    Push-Location -LiteralPath $sourceRoot
    $locationChanged = $true
    $toolsRoot = Join-Path $sourceRoot '.build-tools'
    New-Item -ItemType Directory -Path $toolsRoot -Force | Out-Null
    $headers = @{ 'User-Agent' = 'NEXUS-AI-Windows-Builder'; 'Accept' = 'application/vnd.github+json' }

    Write-Host '[1/5] Downloading and verifying the official standalone uv build tool...'
    $release = Invoke-RestMethod -Headers $headers -Uri 'https://api.github.com/repos/astral-sh/uv/releases/latest'
    $assets = @($release.assets | Where-Object { $_.name -eq 'uv-x86_64-pc-windows-msvc.zip' })
    if ($assets.Count -ne 1) {
        throw 'The official uv release is missing its Windows x64 ZIP.'
    }
    $asset = $assets[0]
    $expectedHash = Get-UvChecksum -Release $release -Asset $asset -Headers $headers
    $uvArchive = Join-Path $toolsRoot 'uv-windows-x64.zip'
    $downloadNeeded = $true
    if (Test-Path -LiteralPath $uvArchive -PathType Leaf) {
        $downloadNeeded = (Get-FileHash -LiteralPath $uvArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash
    }
    if ($downloadNeeded) {
        Invoke-WebRequest -UseBasicParsing -Headers $headers -Uri $asset.browser_download_url -OutFile $uvArchive
    }
    if ((Get-FileHash -LiteralPath $uvArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) {
        Remove-Item -LiteralPath $uvArchive -Force
        throw 'uv SHA256 verification failed. The downloaded program was not executed.'
    }
    $uvDirectory = Join-Path $toolsRoot 'uv'
    if (Test-Path -LiteralPath $uvDirectory) {
        Remove-Item -LiteralPath $uvDirectory -Recurse -Force
    }
    Expand-Archive -LiteralPath $uvArchive -DestinationPath $uvDirectory
    $uvPrograms = @(Get-ChildItem -LiteralPath $uvDirectory -Filter 'uv.exe' -Recurse -File)
    if ($uvPrograms.Count -ne 1) {
        throw 'The verified uv ZIP did not contain exactly one uv.exe.'
    }
    $uv = $uvPrograms[0].FullName

    # These environment variables affect this PowerShell process and its children
    # only. They do not install Python globally or update the user's PATH.
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $toolsRoot 'python'
    $env:UV_PYTHON_BIN_DIR = Join-Path $toolsRoot 'bin'
    $env:UV_CACHE_DIR = Join-Path $toolsRoot 'cache'
    $env:UV_PYTHON_DOWNLOADS = 'automatic'
    $env:UV_PYTHON_PREFERENCE = 'only-managed'
    Write-Host '[2/5] Downloading private Python 3.11 (no manual Python setup needed)...'
    Invoke-NexusCommand -Executable $uv -Arguments @('python', 'install', '3.11')

    Write-Host '[3/5] Creating the private build environment...'
    $venv = Join-Path $toolsRoot 'venv'
    Invoke-NexusCommand -Executable $uv -Arguments @('venv', '--clear', '--python', '3.11', '--managed-python', $venv)
    $python = Join-Path $venv 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw 'The private Python environment was not created.'
    }

    Write-Host '[4/5] Installing PyInstaller, PySide6, and application dependencies...'
    Invoke-NexusCommand -Executable $uv -Arguments @('pip', 'install', '--python', $python, '-e', '.[dev,nvidia,freeze]')

    Write-Host '[5/5] Building onefile and onedir, then smoke-testing both Windows executables...'
    Invoke-NexusCommand -Executable $python -Arguments @('scripts\build_windows.py', '--mode', 'both')
    $onefile = Join-Path $sourceRoot 'dist\NEXUS-AI.exe'
    $portable = Join-Path $sourceRoot 'dist\NEXUS-AI-Portable.zip'
    if (-not (Test-Path -LiteralPath $onefile -PathType Leaf) -or -not (Test-Path -LiteralPath $portable -PathType Leaf)) {
        throw 'The native builder finished without both expected distribution files.'
    }
    Write-Host ''
    Write-Host 'Native Windows builds and launch smoke tests succeeded:' -ForegroundColor Green
    Write-Host $onefile
    Write-Host $portable
    exit 0
}
catch {
    Write-Host ''
    Write-Host ('Build failed: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Internet access to GitHub, Python distributions, and PyPI is required.'
    exit 1
}
finally {
    if ($locationChanged) {
        Pop-Location
    }
}
