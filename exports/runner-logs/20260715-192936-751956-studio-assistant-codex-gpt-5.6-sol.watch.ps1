$Host.UI.RawUI.WindowTitle = 'Studio Assistant · Codex · gpt-5.6-sol'
$log = 'K:\Minecraft Narrative Studio\exports\runner-logs\20260715-192936-751956-studio-assistant-codex-gpt-5.6-sol.log'
$done = 'K:\Minecraft Narrative Studio\exports\runner-logs\20260715-192936-751956-studio-assistant-codex-gpt-5.6-sol.done'
$position = 0
Clear-Host
Write-Host 'Studio Assistant · Codex · gpt-5.6-sol' -ForegroundColor Green
Write-Host "Live runner output. This window will stay open when the task ends." -ForegroundColor DarkGray
Write-Host ""
while (-not (Test-Path -LiteralPath $done)) {
    if (Test-Path -LiteralPath $log) {
        $lines = @(Get-Content -LiteralPath $log -ErrorAction SilentlyContinue)
        if ($lines.Count -gt $position) {
            $lines[$position..($lines.Count - 1)] | ForEach-Object { Write-Host $_ }
            $position = $lines.Count
        }
    }
    Start-Sleep -Milliseconds 250
}
if (Test-Path -LiteralPath $log) {
    $lines = @(Get-Content -LiteralPath $log -ErrorAction SilentlyContinue)
    if ($lines.Count -gt $position) {
        $lines[$position..($lines.Count - 1)] | ForEach-Object { Write-Host $_ }
    }
}
Write-Host ""
Write-Host "Task finished. You may review the output above." -ForegroundColor Cyan
Write-Host "This terminal will remain open until you close it." -ForegroundColor Yellow
Set-Location -LiteralPath 'K:\Minecraft Narrative Studio'
