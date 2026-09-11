param(
    [string]$CepRoot = (Join-Path $env:APPDATA "Adobe\CEP\extensions\MCPBridgeCEP")
)

$ErrorActionPreference = "Stop"

if (-not $env:APPDATA) {
    throw "APPDATA is not set; cannot locate the per-user Adobe CEP extensions directory."
}

$CssPath = Join-Path $CepRoot "styles.css"
if (-not (Test-Path -LiteralPath $CssPath)) {
    throw "Premiere MCP CEP stylesheet was not found at '$CssPath'. Run setup.ps1 first or pass -CepRoot explicitly."
}

$BeginMarker = "/* BEGIN CUTS STUDIO DOCKED PANEL SCROLL FIX */"
$EndMarker = "/* END CUTS STUDIO DOCKED PANEL SCROLL FIX */"
$Patch = @'
/* BEGIN CUTS STUDIO DOCKED PANEL SCROLL FIX */
/*
 * premiere-pro-mcp v1.15.0 keeps body overflow hidden and constrains
 * .panel-shell to the CEP viewport. In a docked Premiere workspace the
 * panel can be shorter than its content, so the lower controls are clipped.
 * Make the shell itself the scroll container; this preserves the upstream
 * layout and the independent Activity log scrollbar.
 */
.panel-shell {
  overflow-x: hidden !important;
  overflow-y: auto !important;
  overscroll-behavior: contain;
}

.panel-shell::-webkit-scrollbar {
  width: 6px;
}

.panel-shell::-webkit-scrollbar-track {
  background: transparent;
}

.panel-shell::-webkit-scrollbar-thumb {
  border-radius: 3px;
  background: var(--border-strong);
}
/* END CUTS STUDIO DOCKED PANEL SCROLL FIX */
'@

$Content = [System.IO.File]::ReadAllText($CssPath)
$Pattern = [regex]::Escape($BeginMarker) + ".*?" + [regex]::Escape($EndMarker)
$RegexOptions = [System.Text.RegularExpressions.RegexOptions]::Singleline

if ([regex]::IsMatch($Content, $Pattern, $RegexOptions)) {
    $Updated = [regex]::Replace($Content, $Pattern, $Patch.TrimEnd(), $RegexOptions)
    $Action = "Refreshed"
} else {
    $Updated = $Content.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + $Patch.TrimEnd() + [Environment]::NewLine
    $Action = "Applied"
}

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($CssPath, $Updated, $Utf8NoBom)

Write-Host "$Action docked-panel scroll fix: $CssPath"
Write-Host "Fully restart Premiere Pro so the CEP panel reloads the stylesheet."
