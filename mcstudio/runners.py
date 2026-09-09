from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .core import StudioError

RUNNER_LABELS = {
    "codex": "Codex CLI",
    "opencode": "OpenCode CLI",
    "openai": "OpenAI API",
}

TASK_GROUPS = {
    "creative": {"direction", "story", "script"},
    "production": {"production", "edit", "release", "learn"},
}

# Codex uses strict structured outputs. Strict schemas cannot contain a free-form
# object map, so files travel as path/content entries and are normalised back to
# the dashboard's {path: content} contract after parsing.
PROPOSAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "document": {"type": "string"},
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
        "questions": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "document", "files", "questions", "warnings"],
    "additionalProperties": False,
}


def _creationflags() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0


def _cleanup_temp_workspace(path: Path) -> None:
    """Remove a runner workspace without turning successful work into failure.

    On Windows an elevated terminal or bootstrap process can briefly retain a
    directory handle after the CLI exits. Cleanup is therefore retried and, if
    Windows still reports a sharing violation, continued in a daemon thread.
    """
    delays = (0.0, 0.1, 0.25, 0.5, 1.0, 2.0)
    for delay in delays:
        if delay:
            time.sleep(delay)
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            continue

    def deferred_cleanup() -> None:
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            try:
                shutil.rmtree(path)
                return
            except FileNotFoundError:
                return
            except OSError:
                time.sleep(2)

    threading.Thread(
        target=deferred_cleanup,
        name=f"mcstudio-temp-cleanup-{path.name}",
        daemon=True,
    ).start()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _runner_archive_dir(root: Path, label: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("-").lower() or "runner"
    path = root / "exports" / "runner-runs" / f"{stamp}-{safe}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def _extract_codex_session_id(*texts: str) -> str:
    patterns = (
        r"(?im)^session id:\s*([0-9a-f]{8}-[0-9a-f-]{27,})\s*$",
        r'"type"\s*:\s*"thread\.started"[^\n]*?"thread_id"\s*:\s*"([0-9a-f-]{36})"',
    )
    for text in texts:
        for pattern in patterns:
            match = re.search(pattern, str(text or ""), re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(1)
    return ""


def _write_codex_resume_script(
    *,
    path: Path,
    base: list[str],
    session_id: str,
    archive_dir: Path,
    schema_path: Path,
    model: str,
    effort: str,
    use_web_search: bool,
    full_output: bool,
) -> None:
    recovery_workspace = archive_dir / "resume-workspace"
    recovered_output = archive_dir / "recovered-proposal.json"
    recovery_workspace.mkdir(parents=True, exist_ok=True)
    command = [*base]
    if use_web_search:
        command.append("--search")
    command.append("exec")
    if not full_output:
        command.append("--json")
    command.extend([
        "--ignore-user-config",
        "--ignore-rules",
        "--sandbox",
        "workspace-write",
        "--skip-git-repo-check",
        "--color",
        "never",
        "-C",
        str(recovery_workspace),
        "-c",
        'approval_policy="on-request"',
        "-c",
        'approvals_reviewer="auto_review"',
        "-c",
        'windows.sandbox="elevated"',
        "-c",
        f'web_search="{"live" if use_web_search else "disabled"}"',
        "--output-schema",
        str(schema_path),
        "-o",
        str(recovered_output),
    ])
    if model:
        command.extend(["-m", model])
    if effort:
        command.extend(["-c", f'model_reasoning_effort="{effort}"'])
    command.extend([
        "-c",
        'model_reasoning_summary="detailed"',
        "resume",
        session_id,
        (
            "Continue the interrupted Minecraft Narrative Studio proposal from exactly where you stopped. "
            "Do not restart the analysis. Finish the pending strict structured JSON response using the "
            "same schema and requirements from the existing session."
        ),
    ])
    command_lines = ",\n    ".join(_ps_quote(item) for item in command)
    script = f'''$ErrorActionPreference = "Stop"
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {{
    $pwsh = (Get-Process -Id $PID).Path
    $arguments = '-NoLogo -NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '"'
    Start-Process -FilePath $pwsh -ArgumentList $arguments -Verb RunAs | Out-Null
    exit
}}
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$Host.UI.RawUI.WindowTitle = "Resume Studio Assistant · Codex"
$command = @(
    {command_lines}
)
Set-Location -LiteralPath {_ps_quote(str(recovery_workspace))}
Write-Host "Resuming Codex session {session_id}" -ForegroundColor Green
Write-Host "Recovered proposal will be written to:" -ForegroundColor DarkGray
Write-Host {_ps_quote(str(recovered_output))} -ForegroundColor Cyan
Write-Host ""
& $command[0] $command[1..($command.Count - 1)]
$exitCode = $LASTEXITCODE
Write-Host ""
if ($exitCode -eq 0) {{
    Write-Host "Resume finished successfully." -ForegroundColor Green
    Write-Host "Import recovered-proposal.json through Studio Assistant → Import work from another AI." -ForegroundColor Cyan
}} else {{
    Write-Host "Resume failed with exit code $exitCode." -ForegroundColor Red
}}
[void](Read-Host "Press Enter to close this terminal")
exit $exitCode
'''
    path.write_text(script, encoding="utf-8-sig")


def _command_parts(raw: str, default: str) -> list[str]:
    value = str(raw or default).strip()
    if not value:
        raise StudioError(f"No command configured for {default}.")
    unquoted = value.strip('"')
    candidate = Path(unquoted).expanduser()
    if candidate.is_file():
        return [str(candidate)]
    parts = [part.strip('"') for part in shlex.split(value, posix=os.name != "nt")]
    if not parts:
        raise StudioError(f"No command configured for {default}.")
    executable = shutil.which(parts[0])
    if executable:
        parts[0] = executable
        return parts
    if Path(parts[0]).expanduser().is_file():
        parts[0] = str(Path(parts[0]).expanduser())
        return parts
    raise StudioError(f"{RUNNER_LABELS.get(default, default)} is not installed or is not on PATH.")


def _ps_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _powershell_763() -> str:
    """Return PowerShell 7.6.3+ for elevated visible runner terminals."""
    if os.name != "nt":
        raise StudioError("Administrator runner terminals are only available on Windows.")
    candidates: list[str] = []
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    candidates.append(str(Path(program_files) / "PowerShell" / "7" / "pwsh.exe"))
    for name in ("pwsh.exe", "pwsh"):
        found = shutil.which(name)
        if found and found not in candidates:
            candidates.append(found)
    for candidate in candidates:
        path = Path(candidate)
        if not path.is_file():
            continue
        try:
            completed = subprocess.run(
                [str(path), "-NoLogo", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=_creationflags(),
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        version_text = (completed.stdout or completed.stderr or "").strip().splitlines()
        version = version_text[-1].strip() if version_text else ""
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
        if completed.returncode == 0 and match and tuple(map(int, match.groups())) >= (7, 6, 3):
            return str(path)
    raise StudioError(
        "PowerShell 7.6.3 or newer is required for visible Administrator runner terminals. "
        "Install/update PowerShell 7, then retry."
    )


def _windows_terminal() -> str | None:
    """Return the Windows Terminal launcher when its execution alias is available."""
    if os.name != "nt":
        return None
    candidates: list[str] = []
    found = shutil.which("wt.exe") or shutil.which("wt")
    if found:
        candidates.append(found)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(str(Path(local_app_data) / "Microsoft" / "WindowsApps" / "wt.exe"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate))
    return None


def _write_elevated_runner_script(
    *,
    script_path: Path,
    command: list[str],
    cwd: Path,
    timeout: int,
    input_path: Path | None,
    stdout_path: Path,
    stderr_path: Path,
    log_path: Path,
    started_path: Path,
    done_path: Path,
    exit_path: Path,
    session_path: Path,
    partial_path: Path,
    title: str,
    env: dict[str, str] | None,
    json_event_stream: bool = False,
) -> None:
    executable = command[0]
    argument_line = subprocess.list2cmdline(command[1:])
    env_lines: list[str] = []
    if env:
        for key, value in sorted(env.items()):
            if os.environ.get(key) != value:
                env_lines.append(f"$env:{key} = {_ps_quote(value)}")
    env_block = "\n".join(env_lines)
    input_setting = (
        f"        RedirectStandardInput = {_ps_quote(str(input_path))}\n" if input_path is not None else ""
    )
    json_stream_value = "$true" if json_event_stream else "$false"
    script = f'''$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$Host.UI.RawUI.WindowTitle = {_ps_quote(title)}
$stdoutPath = {_ps_quote(str(stdout_path))}
$stderrPath = {_ps_quote(str(stderr_path))}
$logPath = {_ps_quote(str(log_path))}
$startedPath = {_ps_quote(str(started_path))}
$donePath = {_ps_quote(str(done_path))}
$exitPath = {_ps_quote(str(exit_path))}
$sessionPath = {_ps_quote(str(session_path))}
$partialPath = {_ps_quote(str(partial_path))}
$resultPath = Join-Path (Split-Path -Parent $logPath) "terminal-result.json"
$timeoutSeconds = {max(10, int(timeout))}
$jsonEventStream = {json_stream_value}
$stdoutPosition = 0
$stderrPosition = 0
$stderrColour = if ($jsonEventStream) {{ [ConsoleColor]::Red }} else {{ [ConsoleColor]::White }}

function Write-Display([string]$Message, [ConsoleColor]$Colour) {{
    if ([string]::IsNullOrWhiteSpace($Message)) {{ return }}
    Write-Host $Message -ForegroundColor $Colour
    Add-Content -LiteralPath $logPath -Value $Message -Encoding utf8
}}

function Capture-SessionId([string]$Line) {{
    if ([string]::IsNullOrWhiteSpace($Line)) {{ return }}
    if ($Line -match '(?i)session id:\\s*([0-9a-f]{{8}}-[0-9a-f-]{{27,}})') {{
        Set-Content -LiteralPath $sessionPath -Value $Matches[1] -Encoding ascii
    }}
}}

function Convert-EventText($Value) {{
    if ($null -eq $Value) {{ return "" }}
    if ($Value -is [string]) {{ return $Value }}
    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [pscustomobject])) {{
        $parts = @($Value | ForEach-Object {{ Convert-EventText $_ }} | Where-Object {{ -not [string]::IsNullOrWhiteSpace($_) }})
        return ($parts -join "`n").Trim()
    }}
    foreach ($name in @("text", "summary", "content", "message", "explanation", "delta")) {{
        $property = $Value.PSObject.Properties[$name]
        if ($null -ne $property) {{
            $text = Convert-EventText $property.Value
            if (-not [string]::IsNullOrWhiteSpace($text)) {{ return $text }}
        }}
    }}
    return ""
}}

function Show-CodexEvent([string]$Line) {{
    if ([string]::IsNullOrWhiteSpace($Line)) {{ return }}
    try {{
        $event = $Line | ConvertFrom-Json -ErrorAction Stop
    }} catch {{
        Write-Display $Line DarkGray
        return
    }}
    $type = [string]$event.type
    $item = $event.item
    $itemType = if ($null -ne $item) {{ [string]$item.type }} else {{ "" }}
    switch ($type) {{
        "thread.started" {{
            $thread = [string]$event.thread_id
            if ($thread) {{ Set-Content -LiteralPath $sessionPath -Value $thread -Encoding ascii }}
            Write-Display ("Codex session started" + $(if ($thread) {{ ": " + $thread }} else {{ "" }})) DarkGray
        }}
        "turn.started" {{ Write-Display "Codex is working…" Cyan }}
        "item.started" {{
            switch ($itemType) {{
                "reasoning" {{ Write-Display "Codex is reasoning…" DarkCyan }}
                "agent_message" {{ Write-Display "Codex is composing the proposal…" Cyan }}
                "command_execution" {{ Write-Display ("Command: " + [string]$item.command) Yellow }}
                "web_search" {{ Write-Display "Codex started a web search." Yellow }}
                "plan_update" {{ Write-Display "Codex updated its plan." DarkCyan }}
            }}
        }}
        "item.completed" {{
            $text = Convert-EventText $item
            switch ($itemType) {{
                "reasoning" {{
                    if ($text) {{ Write-Display ("Reasoning summary:`n" + $text) DarkCyan }}
                    else {{ Write-Display "Codex completed a reasoning step." DarkCyan }}
                }}
                "agent_message" {{
                    $trimmed = $text.TrimStart()
                    if ($text) {{ Set-Content -LiteralPath $partialPath -Value $text -Encoding utf8 }}
                    if ($trimmed.StartsWith("{{") -or $trimmed.StartsWith("[")) {{
                        Write-Display "Codex produced the structured proposal." Green
                    }} elseif ($text) {{
                        Write-Display $text White
                    }} else {{
                        Write-Display "Codex completed an assistant message." White
                    }}
                }}
                "command_execution" {{
                    $status = [string]$item.status
                    Write-Display ("Command finished" + $(if ($status) {{ " · " + $status }} else {{ "" }})) Yellow
                    if ($text) {{ Write-Display $text DarkGray }}
                }}
                "web_search" {{ Write-Display "Codex completed a web search." Yellow }}
                "plan_update" {{ if ($text) {{ Write-Display ("Plan:`n" + $text) DarkCyan }} }}
                "file_change" {{ Write-Display "Codex reported a file-change event." Yellow }}
                default {{ if ($text -and $text.Length -lt 2000) {{ Write-Display $text DarkGray }} }}
            }}
        }}
        "turn.completed" {{
            $usage = $event.usage
            if ($null -ne $usage) {{
                Write-Display ("Codex turn completed · input " + [string]$usage.input_tokens + " · output " + [string]$usage.output_tokens + " · reasoning " + [string]$usage.reasoning_output_tokens) Green
            }} else {{
                Write-Display "Codex turn completed." Green
            }}
        }}
        "turn.failed" {{ Write-Display ("Codex turn failed: " + (Convert-EventText $event)) Red }}
        "error" {{ Write-Display ("Codex error: " + (Convert-EventText $event)) Red }}
    }}
}}

function Show-NewLines([string]$Path, [ref]$Position, [ConsoleColor]$Colour, [bool]$AsCodexJson) {{
    if (-not (Test-Path -LiteralPath $Path)) {{ return }}
    $lines = @(Get-Content -LiteralPath $Path -Encoding utf8 -ErrorAction SilentlyContinue)
    if ($lines.Count -gt $Position.Value) {{
        $lines[$Position.Value..($lines.Count - 1)] | ForEach-Object {{
            Capture-SessionId $_
            if ($AsCodexJson) {{ Show-CodexEvent $_ }}
            else {{
                Write-Display $_ $Colour
                if ($Path -eq $stdoutPath) {{ Add-Content -LiteralPath $partialPath -Value $_ -Encoding utf8 }}
            }}
        }}
        $Position.Value = $lines.Count
    }}
}}

Clear-Host
Write-Host {_ps_quote(title)} -ForegroundColor Green
Write-Host "PowerShell $($PSVersionTable.PSVersion) · Administrator: $(([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))" -ForegroundColor DarkGray
Write-Host "The real CLI process is running inside this elevated terminal." -ForegroundColor DarkGray
if ($jsonEventStream) {{
    Write-Host "Live Codex events and safe reasoning summaries will appear below." -ForegroundColor DarkGray
}} else {{
    Write-Host "Live CLI output will appear below." -ForegroundColor DarkGray
}}
Write-Host "This window will remain open after success or failure." -ForegroundColor DarkGray
Write-Host ""
Set-Location -LiteralPath {_ps_quote(str(cwd))}
{env_block}
Set-Content -LiteralPath $startedPath -Value ([string]$PID) -Encoding ascii
Set-Content -LiteralPath $stdoutPath -Value "" -Encoding utf8
Set-Content -LiteralPath $stderrPath -Value "" -Encoding utf8
Set-Content -LiteralPath $logPath -Value ({_ps_quote(title)} + "`nWorking directory: " + {_ps_quote(str(cwd))} + "`nCommand: " + {_ps_quote(' '.join(command))} + "`n") -Encoding utf8
$exitCode = 1
try {{
    $start = @{{
        FilePath = {_ps_quote(executable)}
        ArgumentList = {_ps_quote(argument_line)}
        WorkingDirectory = {_ps_quote(str(cwd))}
        RedirectStandardOutput = $stdoutPath
        RedirectStandardError = $stderrPath
        PassThru = $true
        NoNewWindow = $true
{input_setting}    }}
    $runner = Start-Process @start
    $clock = [Diagnostics.Stopwatch]::StartNew()
    while (-not $runner.HasExited) {{
        Show-NewLines $stdoutPath ([ref]$stdoutPosition) White $jsonEventStream
        Show-NewLines $stderrPath ([ref]$stderrPosition) $stderrColour $false
        if ($clock.Elapsed.TotalSeconds -ge $timeoutSeconds) {{
            Write-Display "Runner timed out after $timeoutSeconds seconds." Red
            Stop-Process -Id $runner.Id -Force -ErrorAction SilentlyContinue
            $exitCode = 124
            break
        }}
        Start-Sleep -Milliseconds 200
        $runner.Refresh()
    }}
    if ($exitCode -ne 124) {{
        $runner.WaitForExit()
        $exitCode = $runner.ExitCode
    }}
    Show-NewLines $stdoutPath ([ref]$stdoutPosition) White $jsonEventStream
    Show-NewLines $stderrPath ([ref]$stderrPosition) $stderrColour $false
}} catch {{
    $message = $_ | Out-String
    Write-Display $message Red
    Add-Content -LiteralPath $stderrPath -Value $message -Encoding utf8
    $exitCode = 1
}} finally {{
    # Release the disposable workspace before the dashboard sees completion.
    # The terminal remains open, so leaving its current directory inside the
    # workspace would make Windows reject cleanup with WinError 32.
    try {{
        Set-Location -LiteralPath (Split-Path -Parent $logPath)
    }} catch {{
        Set-Location -LiteralPath $env:TEMP -ErrorAction SilentlyContinue
    }}
    $sessionId = if (Test-Path -LiteralPath $sessionPath) {{ (Get-Content -LiteralPath $sessionPath -Raw -ErrorAction SilentlyContinue).Trim() }} else {{ "" }}
    $terminalResult = [ordered]@{{
        exit_code = $exitCode
        status = $(if ($exitCode -eq 0) {{ "success" }} elseif ($exitCode -eq 124) {{ "timed_out" }} else {{ "failed" }})
        session_id = $sessionId
        finished_at = [DateTimeOffset]::UtcNow.ToString("o")
    }}
    $terminalResult | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding utf8
    Set-Content -LiteralPath $exitPath -Value ([string]$exitCode) -Encoding ascii
    Set-Content -LiteralPath $donePath -Value "done" -Encoding ascii
}}
Write-Host ""
if ($exitCode -eq 0) {{
    Write-Host "Task finished successfully." -ForegroundColor Cyan
}} else {{
    Write-Host "Task failed with exit code $exitCode." -ForegroundColor Red
}}
Write-Host "The dashboard has received the result. This terminal will stay open." -ForegroundColor Yellow
[void](Read-Host "Press Enter to close this terminal")
'''
    script_path.write_text(script, encoding="utf-8-sig")


def _run_visible(
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
    input_text: str | None,
    env: dict[str, str] | None,
    title: str,
    log_root: Path | None = None,
    terminal_host: str = "windows_terminal",
    json_event_stream: bool = False,
    artifact_dir: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the real CLI in an elevated PowerShell 7.6.3+ session."""
    pwsh = _powershell_763()
    if artifact_dir is not None:
        logs_dir = artifact_dir
        logs_dir.mkdir(parents=True, exist_ok=True)
        prefix = logs_dir / "runner"
    else:
        logs_dir = (log_root or cwd) / "exports" / "runner-logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        safe_title = re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip("-").lower() or "runner"
        prefix = logs_dir / f"{stamp}-{safe_title}"
    log_path = prefix.with_suffix(".log")
    stdout_path = prefix.with_suffix(".stdout.log")
    stderr_path = prefix.with_suffix(".stderr.log")
    started_path = prefix.with_suffix(".started")
    done_path = prefix.with_suffix(".done")
    exit_path = prefix.with_suffix(".exit")
    script_path = prefix.with_suffix(".run.ps1")
    session_path = logs_dir / "session-id.txt"
    partial_path = logs_dir / "partial-response.txt"
    input_path: Path | None = None
    if input_text is not None:
        input_path = (logs_dir / "prompt.txt") if artifact_dir is not None else prefix.with_suffix(".stdin.txt")
        input_path.write_text(input_text, encoding="utf-8")

    _write_elevated_runner_script(
        script_path=script_path,
        command=command,
        cwd=cwd,
        timeout=timeout,
        input_path=input_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        log_path=log_path,
        started_path=started_path,
        done_path=done_path,
        exit_path=exit_path,
        session_path=session_path,
        partial_path=partial_path,
        title=title,
        env=env,
        json_event_stream=json_event_stream,
    )

    pwsh_args = ["-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]
    requested_host = str(terminal_host or "windows_terminal").strip().lower()
    wt = _windows_terminal() if requested_host == "windows_terminal" else None
    using_windows_terminal = bool(wt)
    # Never let the long-lived terminal host or elevation bootstrap use a
    # disposable workspace as its own current directory. The runner script
    # enters that directory only for the CLI and releases it before signalling
    # completion.
    terminal_start_dir = (log_root or cwd).resolve()
    if using_windows_terminal:
        terminal_args = subprocess.list2cmdline([
            "-w", "-1", "new-tab",
            "--startingDirectory", str(terminal_start_dir),
            "--title", title,
            "--suppressApplicationTitle",
            pwsh,
            *pwsh_args,
        ])
        launch_command = (
            f"$process = Start-Process -FilePath {_ps_quote(str(wt))} "
            f"-ArgumentList {_ps_quote(terminal_args)} -Verb RunAs -PassThru; "
            "$process.WaitForExit(); exit $process.ExitCode"
        )
    else:
        elevated_args = subprocess.list2cmdline(pwsh_args)
        launch_command = (
            f"$process = Start-Process -FilePath {_ps_quote(pwsh)} "
            f"-ArgumentList {_ps_quote(elevated_args)} -Verb RunAs -PassThru -Wait; "
            "exit $process.ExitCode"
        )
    try:
        bootstrap = subprocess.Popen(
            [pwsh, "-NoLogo", "-NoProfile", "-Command", launch_command],
            cwd=terminal_start_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_creationflags(),
        )
    except OSError as exc:
        host_label = "Windows Terminal" if using_windows_terminal else "Administrator PowerShell"
        raise StudioError(f"Could not request {host_label}: {exc}") from exc

    launched_at = time.monotonic()
    startup_deadline = launched_at + 90
    deadline = launched_at + max(10, int(timeout)) + 60
    while not done_path.is_file():
        bootstrap_finished = bootstrap.poll() is not None
        if bootstrap_finished and not using_windows_terminal:
            if started_path.is_file():
                raise StudioError(
                    "The Administrator runner terminal was closed before the CLI finished. "
                    "The dashboard cleared the running task; retry when ready."
                )
            raise StudioError(
                "Administrator permission was cancelled or PowerShell could not start. "
                "Approve the Windows UAC prompt and retry."
            )
        now = time.monotonic()
        if not started_path.is_file() and now >= startup_deadline:
            try:
                bootstrap.terminate()
            except OSError:
                pass
            host_label = "Windows Terminal" if using_windows_terminal else "Administrator PowerShell"
            raise StudioError(
                f"{host_label} did not start within 90 seconds. "
                "Approve the Windows UAC prompt, confirm the Windows Terminal app execution alias is enabled, or switch the terminal host in Settings."
            )
        if now >= deadline:
            try:
                log_display = log_path.relative_to(log_root or cwd)
            except ValueError:
                log_display = log_path
            raise StudioError(
                f"The elevated runner did not report completion within {timeout + 60} seconds. "
                f"Review {log_display} and close the terminal before retrying."
            )
        time.sleep(0.2)

    try:
        returncode = int(exit_path.read_text(encoding="ascii", errors="replace").strip())
    except (OSError, ValueError):
        returncode = 1
    stdout = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.is_file() else ""
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.is_file() else ""
    completed = subprocess.CompletedProcess(command, returncode, stdout, stderr)
    completed.mcstudio_artifacts = {
        "directory": str(logs_dir),
        "terminal_log": str(log_path),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "session_id_file": str(session_path),
        "partial_response": str(partial_path),
        "runner_script": str(script_path),
    }
    return completed

def _run(
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
    visible_terminal: bool = False,
    terminal_title: str = "Studio Assistant",
    log_root: Path | None = None,
    terminal_host: str = "windows_terminal",
    json_event_stream: bool = False,
    artifact_dir: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    if visible_terminal and os.name == "nt":
        return _run_visible(
            command,
            cwd=cwd,
            timeout=timeout,
            input_text=input_text,
            env=env,
            title=terminal_title,
            log_root=log_root,
            terminal_host=terminal_host,
            json_event_stream=json_event_stream,
            artifact_dir=artifact_dir,
        )
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=max(10, int(timeout)),
            env=env,
            creationflags=_creationflags(),
        )
        if artifact_dir is not None:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            (artifact_dir / "stdout.log").write_text(completed.stdout or "", encoding="utf-8")
            (artifact_dir / "stderr.log").write_text(completed.stderr or "", encoding="utf-8")
            (artifact_dir / "terminal.log").write_text(
                "\n".join(part for part in (completed.stderr or "", completed.stdout or "") if part),
                encoding="utf-8",
            )
            completed.mcstudio_artifacts = {
                "directory": str(artifact_dir),
                "terminal_log": str(artifact_dir / "terminal.log"),
                "stdout_log": str(artifact_dir / "stdout.log"),
                "stderr_log": str(artifact_dir / "stderr.log"),
                "session_id_file": str(artifact_dir / "session-id.txt"),
                "partial_response": str(artifact_dir / "partial-response.txt"),
            }
        return completed
    except subprocess.TimeoutExpired as exc:
        if artifact_dir is not None:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else str(exc.stdout or "")
            stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else str(exc.stderr or "")
            (artifact_dir / "stdout.log").write_text(stdout, encoding="utf-8")
            (artifact_dir / "stderr.log").write_text(stderr, encoding="utf-8")
            (artifact_dir / "terminal.log").write_text("\n".join(part for part in (stderr, stdout) if part), encoding="utf-8")
            return subprocess.CompletedProcess(command, 124, stdout, stderr)
        raise StudioError(f"Runner timed out after {timeout} seconds.") from exc
    except OSError as exc:
        raise StudioError(f"Could not start runner: {exc}") from exc


def _normalise_proposal(value: dict[str, Any]) -> dict[str, Any]:
    files = value.get("files", {})
    if isinstance(files, list):
        mapped: dict[str, str] = {}
        for index, item in enumerate(files):
            if not isinstance(item, dict):
                raise StudioError(f"Runner file entry {index + 1} is not an object.")
            path = item.get("path")
            content = item.get("content")
            if not isinstance(path, str) or not path.strip() or not isinstance(content, str):
                raise StudioError(f"Runner file entry {index + 1} must contain string path and content fields.")
            if path in mapped:
                raise StudioError(f"Runner returned the same file more than once: {path}")
            mapped[path] = content
        files = mapped
    if not isinstance(files, dict):
        raise StudioError("Runner files must be an object map or a list of path/content entries.")
    value["files"] = files
    return value


ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _diagnostic_text(completed: subprocess.CompletedProcess[str], fallback: str) -> str:
    parts = [str(completed.stderr or "").strip(), str(completed.stdout or "").strip()]
    text = "\n".join(part for part in parts if part)
    return text or fallback


def _valid_opencode_model_id(value: str) -> bool:
    """OpenCode requires an exact provider/model identifier with no spaces."""
    return bool(re.fullmatch(r"[^\s/]+/[^\s]+", str(value or "").strip()))


def _list_opencode_models(base: list[str], root: Path, timeout: int) -> list[str]:
    completed = _run([*base, "models"], cwd=root, timeout=min(max(timeout, 10), 120))
    if completed.returncode != 0:
        return []
    models: list[str] = []
    for raw_line in str(completed.stdout or "").splitlines():
        line = ANSI_ESCAPE.sub("", raw_line).strip().strip("-*•> ")
        # Some OpenCode versions print metadata after the ID. The first token is
        # still the documented provider/model value.
        token = line.split()[0] if line else ""
        if _valid_opencode_model_id(token) and token not in models:
            models.append(token)
    return models


def _parse_json_text(text: str) -> dict[str, Any]:
    stripped = str(text or "").strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, re.DOTALL | re.IGNORECASE)
    if fenced:
        stripped = fenced.group(1).strip()
    candidates = [stripped]
    start, end = stripped.find("{"), stripped.rfind("}")
    if start >= 0 and end > start:
        candidates.append(stripped[start : end + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return _normalise_proposal(value)
    raise StudioError("The runner did not return the required JSON proposal.")


def _extract_openai_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    texts: list[str] = []
    for item in payload.get("output", []) if isinstance(payload.get("output"), list) else []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content", []) if isinstance(item.get("content"), list) else []:
            if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                texts.append(part["text"])
    if texts:
        return "\n".join(texts)
    raise StudioError("The OpenAI response did not contain text output.")


def _task_group(stage: str, mode: str) -> str:
    if mode == "audit":
        return "audit"
    if stage in TASK_GROUPS["creative"]:
        return "creative"
    return "production"


def runner_candidates(settings: dict[str, Any], stage: str, mode: str, force_runner: str = "") -> list[str]:
    runners = settings.get("runners", {}) if isinstance(settings.get("runners"), dict) else {}
    if force_runner:
        requested = [force_runner]
    elif settings.get("routing_mode") == "fixed":
        requested = [str(settings.get("fixed_runner") or "codex")]
    else:
        group = _task_group(stage, mode)
        routes = settings.get("routes", {}) if isinstance(settings.get("routes"), dict) else {}
        requested = [str(routes.get(group) or ("codex" if group == "creative" else "opencode"))]
    if settings.get("fallback_enabled", True) and not force_runner:
        order = settings.get("fallback_order", ["codex", "opencode", "openai"])
        if isinstance(order, str):
            order = [item.strip() for item in order.split(",")]
        requested.extend(str(item) for item in order if str(item).strip())
    result: list[str] = []
    for name in requested:
        if name not in RUNNER_LABELS or name in result:
            continue
        config = runners.get(name, {}) if isinstance(runners.get(name), dict) else {}
        if config.get("enabled", True):
            result.append(name)
    return result


def _full_prompt(instructions: str, input_text: str) -> str:
    return f"{instructions.strip()}\n\n{input_text.strip()}\n"


def _run_codex(root: Path, settings: dict[str, Any], instructions: str, input_text: str, use_web_search: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    config = settings.get("runners", {}).get("codex", {})
    base = _command_parts(str(config.get("command") or "codex"), "codex")
    model = str(config.get("model") or "gpt-5.6-luna").strip()
    effort = str(config.get("reasoning_effort") or "medium").strip()
    timeout = int(config.get("timeout_seconds") or 3600)
    full_output = bool(settings.get("codex_full_output", True))
    archive_dir = _runner_archive_dir(root, f"studio-assistant-codex-{model}")
    metadata_path = archive_dir / "metadata.json"
    schema_path = archive_dir / "proposal-schema.json"
    output_path = archive_dir / "final-proposal.json"
    command_path = archive_dir / "command.txt"
    temp_dir = Path(tempfile.mkdtemp(prefix="mcstudio-codex-"))
    started_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    metadata: dict[str, Any] = {
        "schema_version": 1,
        "runner": "codex",
        "model": model,
        "reasoning_effort": effort,
        "status": "running",
        "started_at": started_at,
        "finished_at": "",
        "timeout_seconds": timeout,
        "output_mode": "full-native" if full_output else "readable-events",
        "web_search": bool(use_web_search),
        "session_id": "",
        "temporary_workspace": str(temp_dir),
        "archive_directory": str(archive_dir),
        "final_proposal": str(output_path),
        "partial_response": str(archive_dir / "partial-response.txt"),
        "resume_script": "",
        "error": "",
    }
    _atomic_json(metadata_path, metadata)
    try:
        schema_path.write_text(json.dumps(PROPOSAL_SCHEMA, indent=2), encoding="utf-8")
        # Proposal generation is isolated from the repository, but the Codex
        # session itself is persisted. If Windows, the network, or the Studio
        # stops the run, the session ID and full terminal transcript remain in
        # exports/runner-runs and can be resumed instead of starting over.
        command = [*base]
        if use_web_search:
            command.append("--search")
        command.append("exec")
        if not full_output:
            command.append("--json")
        command.extend([
            "--ignore-user-config",
            "--ignore-rules",
            "--sandbox",
            "workspace-write",
            "--skip-git-repo-check",
            "--color",
            "never",
            "-C",
            str(temp_dir),
            "-c",
            'approval_policy="on-request"',
            "-c",
            'approvals_reviewer="auto_review"',
            "-c",
            'windows.sandbox="elevated"',
            "-c",
            f'web_search="{"live" if use_web_search else "disabled"}"',
            "--output-schema",
            str(schema_path),
            "-o",
            str(output_path),
        ])
        if model:
            command.extend(["-m", model])
        if effort:
            command.extend(["-c", f'model_reasoning_effort="{effort}"'])
        command.extend(["-c", 'model_reasoning_summary="detailed"', "-"])
        prompt = _full_prompt(instructions, input_text) + (
            "\nCODEX STRUCTURED-OUTPUT OVERRIDE\n"
            "For this Codex transport, encode files as an array of objects with exactly "
            "two string keys: path and content. Use an empty array when there are no files. "
            "All other top-level keys remain unchanged.\n"
        )
        command_path.write_text(subprocess.list2cmdline(command), encoding="utf-8")
        # prompt.txt is also written by the visible wrapper before process start;
        # write it here so headless runs and pre-launch failures are recoverable.
        (archive_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
        completed = _run(
            command,
            cwd=temp_dir,
            timeout=timeout,
            input_text=prompt,
            visible_terminal=bool(settings.get("visible_runner_terminal", True)),
            terminal_title=f"Studio Assistant · Codex · {model} · Focused proposal",
            log_root=root,
            terminal_host=str(settings.get("runner_terminal_host") or "windows_terminal"),
            json_event_stream=not full_output,
            artifact_dir=archive_dir,
        )
        session_file = archive_dir / "session-id.txt"
        session_id = session_file.read_text(encoding="ascii", errors="replace").strip() if session_file.is_file() else ""
        if not session_id:
            session_id = _extract_codex_session_id(completed.stderr or "", completed.stdout or "")
            if session_id:
                session_file.write_text(session_id, encoding="ascii")
        metadata["session_id"] = session_id
        metadata["finished_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        metadata["exit_code"] = completed.returncode

        if completed.returncode != 0:
            metadata["status"] = "timed_out" if completed.returncode == 124 else "failed"
            detail = (completed.stderr or completed.stdout or "Codex returned no diagnostic output").strip()
            metadata["error"] = detail[-5000:]
            if session_id:
                resume_path = archive_dir / "RESUME-CODEX.ps1"
                _write_codex_resume_script(
                    path=resume_path,
                    base=base,
                    session_id=session_id,
                    archive_dir=archive_dir,
                    schema_path=schema_path,
                    model=model,
                    effort=effort,
                    use_web_search=use_web_search,
                    full_output=full_output,
                )
                metadata["resume_script"] = str(resume_path)
                (archive_dir / "README.txt").write_text(
                    "This Codex run did not finish, but its session was preserved.\n\n"
                    "Run RESUME-CODEX.ps1 to continue the same Codex session. The recovered "
                    "proposal will be written to recovered-proposal.json in this folder.\n",
                    encoding="utf-8",
                )
            _atomic_json(metadata_path, metadata)
            relative = archive_dir.relative_to(root)
            recovery = (
                f" The session was preserved. Run {relative / 'RESUME-CODEX.ps1'} to continue it."
                if session_id else
                f" All available output was preserved in {relative}."
            )
            raise StudioError(f"Codex failed: {detail[-5000:]}{recovery}")

        text = output_path.read_text(encoding="utf-8", errors="replace") if output_path.is_file() else completed.stdout
        result = _parse_json_text(text)
        metadata["status"] = "success"
        metadata["error"] = ""
        _atomic_json(metadata_path, metadata)
        return result, {
            "runner": "codex",
            "model": model,
            "reasoning_effort": effort,
            "response_id": session_id,
            "execution_mode": "focused-isolated-proposal",
            "workspace": "temporary",
            "terminal_output_mode": "full-native" if full_output else "readable-events",
            "run_archive": str(archive_dir.relative_to(root)),
            "final_proposal": str(output_path.relative_to(root)),
            "stderr_tail": (completed.stderr or "")[-2000:],
        }
    except Exception as exc:
        if metadata.get("status") == "running":
            metadata["status"] = "failed"
            metadata["finished_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            metadata["error"] = str(exc)
            _atomic_json(metadata_path, metadata)
        raise
    finally:
        _cleanup_temp_workspace(temp_dir)


def _opencode_json_output(text: str) -> tuple[list[str], str]:
    texts: list[str] = []
    session_id = ""
    for line in str(text or "").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        session_id = str(event.get("sessionID") or session_id)
        part = event.get("part")
        if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
            texts.append(part["text"])
    return texts, session_id


def _collect_json_candidates(value: Any, output: list[str]) -> None:
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str) and "{" in text and "document" in text:
            output.append(text)
        for child in value.values():
            _collect_json_candidates(child, output)
    elif isinstance(value, list):
        for child in value:
            _collect_json_candidates(child, output)


def _recover_opencode_export(base: list[str], root: Path, session_id: str, timeout: int) -> str:
    if not session_id:
        return ""
    exported = _run([*base, "export", session_id], cwd=root, timeout=min(timeout, 120))
    if exported.returncode != 0 or not exported.stdout.strip():
        return ""
    try:
        payload = json.loads(exported.stdout)
    except json.JSONDecodeError:
        return exported.stdout
    candidates: list[str] = []
    _collect_json_candidates(payload, candidates)
    return candidates[-1] if candidates else ""


def _run_opencode(root: Path, settings: dict[str, Any], instructions: str, input_text: str, use_web_search: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    config = settings.get("runners", {}).get("opencode", {})
    base = _command_parts(str(config.get("command") or "opencode"), "opencode")
    requested_model = str(config.get("model") or "").strip()
    model = requested_model if _valid_opencode_model_id(requested_model) else ""
    variant = str(config.get("variant") or "").strip()
    agent = str(config.get("agent") or "studio-assistant").strip()
    timeout = int(config.get("timeout_seconds") or 3600)
    notes: list[str] = []
    if requested_model and not model:
        notes.append(
            f"Ignored invalid OpenCode model '{requested_model}'. "
            "Model IDs must use provider/model with no spaces."
        )

    with tempfile.TemporaryDirectory(prefix="mcstudio-opencode-") as temp:
        prompt_path = Path(temp) / "studio-task.txt"
        prompt = _full_prompt(instructions, input_text)
        if use_web_search:
            prompt += "\nWeb research is authorised for this task when the configured model/provider supports it.\n"
        prompt_path.write_text(prompt, encoding="utf-8")

        def build_command(selected_model: str) -> list[str]:
            command = [*base, "run", "--format", "json", "--dir", str(root), "--file", str(prompt_path)]
            if selected_model:
                command.extend(["--model", selected_model])
            if variant:
                command.extend(["--variant", variant])
            if agent:
                command.extend(["--agent", agent])
            command.append("Read the attached Studio Assistant task specification and return only the required JSON object.")
            return command

        effective_model = model
        completed = _run(build_command(effective_model), cwd=root, timeout=timeout, visible_terminal=bool(settings.get("visible_runner_terminal", True)), terminal_title=f"Studio Assistant · OpenCode · {effective_model or 'default model'}", terminal_host=str(settings.get("runner_terminal_host") or "windows_terminal"))
        detail = _diagnostic_text(completed, "OpenCode returned no diagnostic output")

        # A stale or display-name model can be saved by older dashboard builds or
        # OpenCode provider UIs. Retry once with a real ID reported by the CLI.
        if completed.returncode != 0 and "model not found" in detail.lower():
            available = _list_opencode_models(base, root, timeout)
            fallback_model = next((item for item in available if item != effective_model), "")
            if fallback_model:
                previous = effective_model or requested_model or "OpenCode default"
                notes.append(f"OpenCode rejected '{previous}'; retried with '{fallback_model}'.")
                effective_model = fallback_model
                completed = _run(build_command(effective_model), cwd=root, timeout=timeout, visible_terminal=bool(settings.get("visible_runner_terminal", True)), terminal_title=f"Studio Assistant · OpenCode · {effective_model or 'default model'}", terminal_host=str(settings.get("runner_terminal_host") or "windows_terminal"))
                detail = _diagnostic_text(completed, "OpenCode returned no diagnostic output")

        if completed.returncode != 0:
            guidance = (
                " Clear the OpenCode model field to use its default, or choose an exact "
                "provider/model value shown by `opencode models`."
                if "model not found" in detail.lower()
                else ""
            )
            raise StudioError(f"OpenCode failed: {detail[-5000:]}{guidance}")

        texts, session_id = _opencode_json_output(completed.stdout)
        candidate = texts[-1] if texts else ""
        if not candidate:
            candidate = _recover_opencode_export(base, root, session_id, timeout)
        if not candidate:
            candidate = completed.stdout
        result = _parse_json_text(candidate)
        return result, {
            "runner": "opencode",
            "model": effective_model or "OpenCode default",
            "reasoning_effort": variant,
            "response_id": session_id,
            "stderr_tail": (completed.stderr or "")[-2000:],
            "runner_notes": notes,
        }


def _run_openai(root: Path, settings: dict[str, Any], instructions: str, input_text: str, use_web_search: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    config = settings.get("runners", {}).get("openai", {})
    api_key = str(config.get("api_key") or settings.get("api_key") or os.environ.get("OPENAI_API_KEY", "")).strip()
    if not api_key:
        raise StudioError("OpenAI API key is not configured.")
    base_url = str(config.get("base_url") or settings.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    endpoint = base_url if base_url.endswith("/responses") else base_url + "/responses"
    model = str(config.get("model") or settings.get("model") or "gpt-5.6-luna")
    effort = str(config.get("reasoning_effort") or settings.get("reasoning_effort") or "medium")
    payload: dict[str, Any] = {
        "model": model,
        "instructions": instructions,
        "input": input_text,
        "max_output_tokens": 30000,
    }
    if effort:
        payload["reasoning"] = {"effort": effort}
    if use_web_search:
        payload["tools"] = [{"type": "web_search"}]
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=int(config.get("timeout_seconds") or 600)) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body).get("error", {}).get("message", body)
        except json.JSONDecodeError:
            detail = body
        raise StudioError(f"OpenAI API error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise StudioError(f"Could not reach the OpenAI API: {exc.reason}") from exc
    result = _parse_json_text(_extract_openai_text(raw))
    return result, {
        "runner": "openai",
        "model": model,
        "reasoning_effort": effort,
        "response_id": raw.get("id", ""),
    }


def _prioritise_web_research(candidates: list[str], use_web_search: bool, force_runner: str = "") -> list[str]:
    """Prefer runners with explicit web-search support for research-enabled requests."""
    if not use_web_search or force_runner:
        return list(candidates)
    priority = {"codex": 0, "openai": 1, "opencode": 2}
    return sorted(candidates, key=lambda name: priority.get(name, 99))


def execute_runner(
    root: Path,
    settings: dict[str, Any],
    instructions: str,
    input_text: str,
    *,
    stage: str,
    mode: str,
    use_web_search: bool = False,
    force_runner: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidates = _prioritise_web_research(
        runner_candidates(settings, stage, mode, force_runner=force_runner),
        use_web_search,
        force_runner,
    )
    if not candidates:
        raise StudioError("No enabled AI runner is configured.")
    attempts: list[dict[str, str]] = []
    functions = {"codex": _run_codex, "opencode": _run_opencode, "openai": _run_openai}
    for name in candidates:
        try:
            result, metadata = functions[name](root, settings, instructions, input_text, use_web_search)
            metadata["attempts"] = attempts + [{"runner": name, "status": "success", "error": ""}]
            return result, metadata
        except Exception as exc:
            attempts.append({"runner": name, "status": "failed", "error": str(exc)})
            if force_runner:
                break
    detail = " | ".join(f"{RUNNER_LABELS.get(item['runner'], item['runner'])}: {item['error']}" for item in attempts)
    raise StudioError(f"All configured AI runners failed. {detail}")


def quick_runner_statuses(settings: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    runners = settings.get("runners", {}) if isinstance(settings.get("runners"), dict) else {}
    for name in ("codex", "opencode"):
        config = runners.get(name, {}) if isinstance(runners.get(name), dict) else {}
        try:
            parts = _command_parts(str(config.get("command") or name), name)
            result[name] = {"installed": True, "available": bool(config.get("enabled", True)), "command": parts[0]}
        except StudioError as exc:
            result[name] = {"installed": False, "available": False, "command": "", "detail": str(exc)}
    openai = runners.get("openai", {}) if isinstance(runners.get("openai"), dict) else {}
    has_key = bool(openai.get("api_key") or openai.get("has_api_key") or settings.get("api_key") or settings.get("has_api_key") or os.environ.get("OPENAI_API_KEY"))
    result["openai"] = {"installed": True, "available": bool(openai.get("enabled", True) and has_key), "authenticated": has_key}
    return result


def runner_status(root: Path, settings: dict[str, Any], name: str, deep: bool = False) -> dict[str, Any]:
    quick = quick_runner_statuses(settings).get(name, {"installed": False, "available": False})
    status = {"runner": name, "label": RUNNER_LABELS.get(name, name), **quick}
    if not deep or name == "openai" or not status.get("installed"):
        return status
    config = settings.get("runners", {}).get(name, {})
    base = _command_parts(str(config.get("command") or name), name)
    version = _run([*base, "--version"], cwd=root, timeout=15)
    status["version"] = (version.stdout or version.stderr).strip()[:500]
    if name == "codex":
        auth = _run([*base, "login", "status"], cwd=root, timeout=20)
        status["authenticated"] = auth.returncode == 0
        status["auth_detail"] = (auth.stdout or auth.stderr).strip()[:1000]
    else:
        auth = _run([*base, "auth", "list"], cwd=root, timeout=20)
        text = (auth.stdout or auth.stderr).strip()
        status["authenticated"] = auth.returncode == 0 and bool(text) and "no credential" not in text.lower()
        status["auth_detail"] = text[:1000]
    status["available"] = bool(status.get("installed") and config.get("enabled", True) and status.get("authenticated"))
    return status


def install_runner(root: Path, settings: dict[str, Any], name: str) -> dict[str, str]:
    package = {"codex": "@openai/codex", "opencode": "opencode-ai"}.get(name)
    if not package:
        raise StudioError("Only Codex and OpenCode have dashboard installers.")
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        raise StudioError("Node.js/npm is required. Install Node.js LTS, then retry from the dashboard.")
    completed = _run([npm, "install", "-g", package], cwd=root, timeout=1800)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "npm returned no diagnostic output").strip()
        raise StudioError(f"Installation failed: {detail[-5000:]}")
    return {"message": f"{RUNNER_LABELS[name]} installed. Use its setup button next."}


def launch_runner_setup(root: Path, settings: dict[str, Any], name: str) -> dict[str, str]:
    config = settings.get("runners", {}).get(name, {})
    base = _command_parts(str(config.get("command") or name), name)
    if name == "codex":
        completed = _run([*base, "login"], cwd=root, timeout=900)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "Codex login returned no details").strip()
            raise StudioError(f"Codex sign-in failed: {detail[-4000:]}")
        return {"message": "Codex sign-in completed."}
    if name == "opencode":
        log_path = root / "exports" / "opencode-web.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handle = log_path.open("a", encoding="utf-8")
        try:
            subprocess.Popen(
                [*base, "web", "--hostname", "127.0.0.1", "--port", "4096"],
                cwd=root,
                stdout=handle,
                stderr=handle,
                creationflags=_creationflags(),
            )
        finally:
            handle.close()
        threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:4096")).start()
        return {"message": "OpenCode setup launched in the browser. Connect a provider there, then return and test it."}
    raise StudioError("This runner does not have a separate setup flow.")


def test_runner(root: Path, settings: dict[str, Any], name: str) -> dict[str, str]:
    instructions = (
        "Return strict JSON only with keys summary, document, files, questions, warnings. "
        "Do not use tools or modify files."
    )
    files_example = "[]" if name == "codex" else "{}"
    input_text = (
        "This is a connection test. Return summary='Runner connection works', "
        "document='# Runner test\\n\\nConnection successful.', "
        f"files={files_example}, questions=[], warnings=[]."
    )
    result, metadata = execute_runner(
        root,
        settings,
        instructions,
        input_text,
        stage="direction",
        mode="test",
        force_runner=name,
    )
    if not isinstance(result.get("document"), str):
        raise StudioError("Runner answered, but its structured output was invalid.")
    return {"message": f"{RUNNER_LABELS[name]} connection works using {metadata.get('model', 'configured model')}."}
