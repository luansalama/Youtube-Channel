$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$Host.UI.RawUI.WindowTitle = 'Studio Assistant · Codex · gpt-5.6-sol · Focused proposal'
$stdoutPath = 'K:\Minecraft Narrative Studio\exports\runner-logs\20260715-222129-564874-studio-assistant-codex-gpt-5.stdout.log'
$stderrPath = 'K:\Minecraft Narrative Studio\exports\runner-logs\20260715-222129-564874-studio-assistant-codex-gpt-5.stderr.log'
$logPath = 'K:\Minecraft Narrative Studio\exports\runner-logs\20260715-222129-564874-studio-assistant-codex-gpt-5.log'
$startedPath = 'K:\Minecraft Narrative Studio\exports\runner-logs\20260715-222129-564874-studio-assistant-codex-gpt-5.started'
$donePath = 'K:\Minecraft Narrative Studio\exports\runner-logs\20260715-222129-564874-studio-assistant-codex-gpt-5.done'
$exitPath = 'K:\Minecraft Narrative Studio\exports\runner-logs\20260715-222129-564874-studio-assistant-codex-gpt-5.exit'
$timeoutSeconds = 1800
$jsonEventStream = $true
$stdoutPosition = 0
$stderrPosition = 0

function Write-Display([string]$Message, [ConsoleColor]$Colour) {
    if ([string]::IsNullOrWhiteSpace($Message)) { return }
    Write-Host $Message -ForegroundColor $Colour
    Add-Content -LiteralPath $logPath -Value $Message -Encoding utf8
}

function Convert-EventText($Value) {
    if ($null -eq $Value) { return "" }
    if ($Value -is [string]) { return $Value }
    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [pscustomobject])) {
        $parts = @($Value | ForEach-Object { Convert-EventText $_ } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
        return ($parts -join "`n").Trim()
    }
    foreach ($name in @("text", "summary", "content", "message", "explanation", "delta")) {
        $property = $Value.PSObject.Properties[$name]
        if ($null -ne $property) {
            $text = Convert-EventText $property.Value
            if (-not [string]::IsNullOrWhiteSpace($text)) { return $text }
        }
    }
    return ""
}

function Show-CodexEvent([string]$Line) {
    if ([string]::IsNullOrWhiteSpace($Line)) { return }
    try {
        $event = $Line | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Write-Display $Line DarkGray
        return
    }
    $type = [string]$event.type
    $item = $event.item
    $itemType = if ($null -ne $item) { [string]$item.type } else { "" }
    switch ($type) {
        "thread.started" {
            $thread = [string]$event.thread_id
            Write-Display ("Codex session started" + $(if ($thread) { ": " + $thread } else { "" })) DarkGray
        }
        "turn.started" { Write-Display "Codex is working…" Cyan }
        "item.started" {
            switch ($itemType) {
                "reasoning" { Write-Display "Codex is reasoning…" DarkCyan }
                "agent_message" { Write-Display "Codex is composing the proposal…" Cyan }
                "command_execution" { Write-Display ("Command: " + [string]$item.command) Yellow }
                "web_search" { Write-Display "Codex started a web search." Yellow }
                "plan_update" { Write-Display "Codex updated its plan." DarkCyan }
            }
        }
        "item.completed" {
            $text = Convert-EventText $item
            switch ($itemType) {
                "reasoning" {
                    if ($text) { Write-Display ("Reasoning summary:`n" + $text) DarkCyan }
                    else { Write-Display "Codex completed a reasoning step." DarkCyan }
                }
                "agent_message" {
                    $trimmed = $text.TrimStart()
                    if ($trimmed.StartsWith("{") -or $trimmed.StartsWith("[")) {
                        Write-Display "Codex produced the structured proposal." Green
                    } elseif ($text) {
                        Write-Display $text White
                    } else {
                        Write-Display "Codex completed an assistant message." White
                    }
                }
                "command_execution" {
                    $status = [string]$item.status
                    Write-Display ("Command finished" + $(if ($status) { " · " + $status } else { "" })) Yellow
                    if ($text) { Write-Display $text DarkGray }
                }
                "web_search" { Write-Display "Codex completed a web search." Yellow }
                "plan_update" { if ($text) { Write-Display ("Plan:`n" + $text) DarkCyan } }
                "file_change" { Write-Display "Codex reported a file-change event." Yellow }
                default { if ($text -and $text.Length -lt 2000) { Write-Display $text DarkGray } }
            }
        }
        "turn.completed" {
            $usage = $event.usage
            if ($null -ne $usage) {
                Write-Display ("Codex turn completed · input " + [string]$usage.input_tokens + " · output " + [string]$usage.output_tokens + " · reasoning " + [string]$usage.reasoning_output_tokens) Green
            } else {
                Write-Display "Codex turn completed." Green
            }
        }
        "turn.failed" { Write-Display ("Codex turn failed: " + (Convert-EventText $event)) Red }
        "error" { Write-Display ("Codex error: " + (Convert-EventText $event)) Red }
    }
}

function Show-NewLines([string]$Path, [ref]$Position, [ConsoleColor]$Colour, [bool]$AsCodexJson) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $lines = @(Get-Content -LiteralPath $Path -Encoding utf8 -ErrorAction SilentlyContinue)
    if ($lines.Count -gt $Position.Value) {
        $lines[$Position.Value..($lines.Count - 1)] | ForEach-Object {
            if ($AsCodexJson) { Show-CodexEvent $_ }
            else { Write-Display $_ $Colour }
        }
        $Position.Value = $lines.Count
    }
}

Clear-Host
Write-Host 'Studio Assistant · Codex · gpt-5.6-sol · Focused proposal' -ForegroundColor Green
Write-Host "PowerShell $($PSVersionTable.PSVersion) · Administrator: $(([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))" -ForegroundColor DarkGray
Write-Host "The real CLI process is running inside this elevated terminal." -ForegroundColor DarkGray
if ($jsonEventStream) {
    Write-Host "Live Codex events and safe reasoning summaries will appear below." -ForegroundColor DarkGray
} else {
    Write-Host "Live CLI output will appear below." -ForegroundColor DarkGray
}
Write-Host "This window will remain open after success or failure." -ForegroundColor DarkGray
Write-Host ""
Set-Location -LiteralPath 'C:\Users\Admin\AppData\Local\Temp\mcstudio-codex-dfv6nn99'

Set-Content -LiteralPath $startedPath -Value ([string]$PID) -Encoding ascii
Set-Content -LiteralPath $stdoutPath -Value "" -Encoding utf8
Set-Content -LiteralPath $stderrPath -Value "" -Encoding utf8
Set-Content -LiteralPath $logPath -Value ('Studio Assistant · Codex · gpt-5.6-sol · Focused proposal' + "`nWorking directory: " + 'C:\Users\Admin\AppData\Local\Temp\mcstudio-codex-dfv6nn99' + "`nCommand: " + 'K:\Applications\Codex\codex.EXE --search exec --json --ephemeral --ignore-user-config --ignore-rules --sandbox workspace-write --skip-git-repo-check --color never -C C:\Users\Admin\AppData\Local\Temp\mcstudio-codex-dfv6nn99 -c approval_policy="on-request" -c approvals_reviewer="auto_review" -c windows.sandbox="elevated" -c web_search="live" --output-schema C:\Users\Admin\AppData\Local\Temp\mcstudio-codex-dfv6nn99\proposal-schema.json -o C:\Users\Admin\AppData\Local\Temp\mcstudio-codex-dfv6nn99\proposal.json -m gpt-5.6-sol -c model_reasoning_effort="max" -c model_reasoning_summary="detailed" -' + "`n") -Encoding utf8
$exitCode = 1
try {
    $start = @{
        FilePath = 'K:\Applications\Codex\codex.EXE'
        ArgumentList = '--search exec --json --ephemeral --ignore-user-config --ignore-rules --sandbox workspace-write --skip-git-repo-check --color never -C C:\Users\Admin\AppData\Local\Temp\mcstudio-codex-dfv6nn99 -c approval_policy=\"on-request\" -c approvals_reviewer=\"auto_review\" -c windows.sandbox=\"elevated\" -c web_search=\"live\" --output-schema C:\Users\Admin\AppData\Local\Temp\mcstudio-codex-dfv6nn99\proposal-schema.json -o C:\Users\Admin\AppData\Local\Temp\mcstudio-codex-dfv6nn99\proposal.json -m gpt-5.6-sol -c model_reasoning_effort=\"max\" -c model_reasoning_summary=\"detailed\" -'
        WorkingDirectory = 'C:\Users\Admin\AppData\Local\Temp\mcstudio-codex-dfv6nn99'
        RedirectStandardOutput = $stdoutPath
        RedirectStandardError = $stderrPath
        PassThru = $true
        NoNewWindow = $true
        RedirectStandardInput = 'K:\Minecraft Narrative Studio\exports\runner-logs\20260715-222129-564874-studio-assistant-codex-gpt-5.stdin.txt'
    }
    $runner = Start-Process @start
    $clock = [Diagnostics.Stopwatch]::StartNew()
    while (-not $runner.HasExited) {
        Show-NewLines $stdoutPath ([ref]$stdoutPosition) White $jsonEventStream
        Show-NewLines $stderrPath ([ref]$stderrPosition) Red $false
        if ($clock.Elapsed.TotalSeconds -ge $timeoutSeconds) {
            Write-Display "Runner timed out after $timeoutSeconds seconds." Red
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
    Show-NewLines $stdoutPath ([ref]$stdoutPosition) White $jsonEventStream
    Show-NewLines $stderrPath ([ref]$stderrPosition) Red $false
} catch {
    $message = $_ | Out-String
    Write-Display $message Red
    Add-Content -LiteralPath $stderrPath -Value $message -Encoding utf8
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
