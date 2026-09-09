$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$Host.UI.RawUI.WindowTitle = 'Studio Assistant · OpenCode · default model'
$stdoutPath = 'K:\Minecraft Narrative Studio\exports\runner-logs\20260715-205339-302067-studio-assistant-opencode-default-model.stdout.log'
$stderrPath = 'K:\Minecraft Narrative Studio\exports\runner-logs\20260715-205339-302067-studio-assistant-opencode-default-model.stderr.log'
$logPath = 'K:\Minecraft Narrative Studio\exports\runner-logs\20260715-205339-302067-studio-assistant-opencode-default-model.log'
$startedPath = 'K:\Minecraft Narrative Studio\exports\runner-logs\20260715-205339-302067-studio-assistant-opencode-default-model.started'
$donePath = 'K:\Minecraft Narrative Studio\exports\runner-logs\20260715-205339-302067-studio-assistant-opencode-default-model.done'
$exitPath = 'K:\Minecraft Narrative Studio\exports\runner-logs\20260715-205339-302067-studio-assistant-opencode-default-model.exit'
$timeoutSeconds = 1800
$stdoutPosition = 0
$stderrPosition = 0

function Show-NewLines([string]$Path, [ref]$Position, [ConsoleColor]$Colour) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $lines = @(Get-Content -LiteralPath $Path -Encoding utf8 -ErrorAction SilentlyContinue)
    if ($lines.Count -gt $Position.Value) {
        $lines[$Position.Value..($lines.Count - 1)] | ForEach-Object {
            Write-Host $_ -ForegroundColor $Colour
            Add-Content -LiteralPath $logPath -Value $_ -Encoding utf8
        }
        $Position.Value = $lines.Count
    }
}

Clear-Host
Write-Host 'Studio Assistant · OpenCode · default model' -ForegroundColor Green
Write-Host "PowerShell $($PSVersionTable.PSVersion) · Administrator: $(([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))" -ForegroundColor DarkGray
Write-Host "The real CLI process is running inside this elevated terminal." -ForegroundColor DarkGray
Write-Host "This window will remain open after success or failure." -ForegroundColor DarkGray
Write-Host ""
Set-Location -LiteralPath 'K:\Minecraft Narrative Studio'

Set-Content -LiteralPath $startedPath -Value "started" -Encoding utf8
Set-Content -LiteralPath $stdoutPath -Value "" -Encoding utf8
Set-Content -LiteralPath $stderrPath -Value "" -Encoding utf8
Set-Content -LiteralPath $logPath -Value ('Studio Assistant · OpenCode · default model' + "`nWorking directory: " + 'K:\Minecraft Narrative Studio' + "`nCommand: " + 'C:\nvm4w\nodejs\opencode.CMD run --format json --dir K:\Minecraft Narrative Studio --file C:\Users\Admin\AppData\Local\Temp\mcstudio-opencode-zank2jyc\studio-task.txt --agent studio-assistant Read the attached Studio Assistant task specification and return only the required JSON object.' + "`n") -Encoding utf8
$exitCode = 1
try {
    $start = @{
        FilePath = 'C:\nvm4w\nodejs\opencode.CMD'
        ArgumentList = 'run --format json --dir "K:\Minecraft Narrative Studio" --file C:\Users\Admin\AppData\Local\Temp\mcstudio-opencode-zank2jyc\studio-task.txt --agent studio-assistant "Read the attached Studio Assistant task specification and return only the required JSON object."'
        WorkingDirectory = 'K:\Minecraft Narrative Studio'
        RedirectStandardOutput = $stdoutPath
        RedirectStandardError = $stderrPath
        PassThru = $true
        NoNewWindow = $true
    }
    $runner = Start-Process @start
    $clock = [Diagnostics.Stopwatch]::StartNew()
    while (-not $runner.HasExited) {
        Show-NewLines $stdoutPath ([ref]$stdoutPosition) White
        Show-NewLines $stderrPath ([ref]$stderrPosition) Red
        if ($clock.Elapsed.TotalSeconds -ge $timeoutSeconds) {
            Write-Host "Runner timed out after $timeoutSeconds seconds." -ForegroundColor Red
            Stop-Process -Id $runner.Id -Force -ErrorAction SilentlyContinue
            $exitCode = 124
            break
        }
        Start-Sleep -Milliseconds 200
        $runner.Refresh()
    }
    if ($exitCode -ne 124) {
        $runner.WaitForExit()
        $exitCode = $runner.ExitCode
    }
    Show-NewLines $stdoutPath ([ref]$stdoutPosition) White
    Show-NewLines $stderrPath ([ref]$stderrPosition) Red
} catch {
    $message = $_ | Out-String
    Write-Host $message -ForegroundColor Red
    Add-Content -LiteralPath $stderrPath -Value $message -Encoding utf8
    Add-Content -LiteralPath $logPath -Value $message -Encoding utf8
    $exitCode = 1
} finally {
    Set-Content -LiteralPath $exitPath -Value ([string]$exitCode) -Encoding ascii
    Set-Content -LiteralPath $donePath -Value "done" -Encoding ascii
}
Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "Task finished successfully." -ForegroundColor Cyan
} else {
    Write-Host "Task failed with exit code $exitCode." -ForegroundColor Red
}
Write-Host "The dashboard has received the result. This terminal will stay open." -ForegroundColor Yellow
[void](Read-Host "Press Enter to close this terminal")
