param([switch]$Hidden)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:PYTHONUNBUFFERED = '1'
$logDir = Join-Path $PSScriptRoot 'exports'
$logFile = Join-Path $logDir 'launcher.log'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Show-StudioError([string]$Message) {
    Add-Type -AssemblyName PresentationFramework -ErrorAction SilentlyContinue
    [System.Windows.MessageBox]::Show($Message, 'Minecraft Narrative Studio', 'OK', 'Error') | Out-Null
}

try {
    $pythonExe = $null
    $pythonArgs = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
        if ($LASTEXITCODE -eq 0) {
            $pythonExe = 'py'
            $pythonArgs = @('-3')
        }
    }
    if (-not $pythonExe -and (Get-Command python -ErrorAction SilentlyContinue)) {
        & python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
        if ($LASTEXITCODE -eq 0) {
            $pythonExe = 'python'
            $pythonArgs = @()
        }
    }
    if (-not $pythonExe) {
        throw 'Python 3.11 or newer was not found. Install Python, then double-click START-STUDIO.vbs again.'
    }

    $maximumRestarts = 3
    $attempt = 0
    while ($true) {
        $attempt++
        "[$(Get-Date -Format o)] Starting Minecraft Narrative Studio v0.3.6 (process attempt $attempt)" | Out-File -FilePath $logFile -Append -Encoding utf8
        & $pythonExe @pythonArgs -m mcstudio studio *>> $logFile
        $exitCode = $LASTEXITCODE
        if ($exitCode -eq 0) {
            break
        }
        "[$(Get-Date -Format o)] Studio process stopped unexpectedly with exit code $exitCode." | Out-File -FilePath $logFile -Append -Encoding utf8
        if ($attempt -ge $maximumRestarts) {
            throw "Studio stopped repeatedly with exit code $exitCode. See exports\launcher.log and exports\studio-server.log."
        }
        Start-Sleep -Seconds 2
    }
}
catch {
    $_ | Out-String | Out-File -FilePath $logFile -Append -Encoding utf8
    Show-StudioError $_.Exception.Message
    exit 1
}
