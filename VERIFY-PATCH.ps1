$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Minecraft Narrative Studio tests failed." }
Write-Host "Patch verified: all tests passed." -ForegroundColor Green
