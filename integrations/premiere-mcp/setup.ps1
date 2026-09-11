param(
    [switch]$DoctorOnly,
    [switch]$SkipCepInstall,
    [switch]$SkipPanelScrollFix
)

$ErrorActionPreference = "Stop"
$Package = "premiere-pro-mcp"
$Version = "1.15.0"

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name was not found on PATH. Install Node.js 20.19+ first."
    }
}

Require-Command "node"
Require-Command "npm"

$nodeVersion = (& node --version).Trim().TrimStart('v')
Write-Host "Node.js: $nodeVersion"
if ([version]$nodeVersion -lt [version]"20.19.0") {
    throw "Node.js 20.19+ is required by the pinned Premiere MCP release."
}

if (-not $DoctorOnly) {
    Write-Host "Installing pinned $Package@$Version ..."
    & npm install -g "$Package@$Version"
    if ($LASTEXITCODE -ne 0) { throw "npm install failed with exit code $LASTEXITCODE" }

    if (-not $SkipCepInstall) {
        Require-Command "premiere-pro-mcp"
        Write-Host "Installing/updating the Premiere CEP connector ..."
        & premiere-pro-mcp --install-cep
        if ($LASTEXITCODE -ne 0) { throw "CEP connector install failed with exit code $LASTEXITCODE" }
    }

    if (-not $SkipPanelScrollFix) {
        $ScrollFix = Join-Path $PSScriptRoot "fix-panel-scroll.ps1"
        if (-not (Test-Path -LiteralPath $ScrollFix)) {
            throw "Docked-panel scroll fixer was not found at '$ScrollFix'."
        }
        Write-Host "Applying docked Premiere panel scroll compatibility fix ..."
        & $ScrollFix
        if ($LASTEXITCODE -ne 0) { throw "Panel scroll fix failed with exit code $LASTEXITCODE" }
    }
}

Require-Command "premiere-pro-mcp"
Write-Host "Running local readiness diagnostics (this does not prove a live Premiere connection) ..."
& premiere-pro-mcp --doctor
exit $LASTEXITCODE
