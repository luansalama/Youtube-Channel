$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = if (Test-Path "$RepoRoot\.venv\Scripts\python.exe") { "$RepoRoot\.venv\Scripts\python.exe" } else { "python" }
& $Python -m mcstudio --root $RepoRoot @args
exit $LASTEXITCODE
