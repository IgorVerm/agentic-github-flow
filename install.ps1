# agentic-github-flow installer for Windows (PowerShell 5.1 or 7). The one command (README):
#   git clone https://github.com/IgorVerm/agentic-github-flow.git "$env:USERPROFILE\.agentic-github-flow"; & "$env:USERPROFILE\.agentic-github-flow\install.ps1"
# It makes sure the clone exists in %USERPROFILE%\.agentic-github-flow, finds Python 3.8+ and hands
# over to tools\installer.py in that clone, which owns every step. Options (all passed on):
#   --with security,web-deploy   --guards   --overlay <git-url-or-path>   --update   --uninstall
#   --no-claude   --no-codex   --claude-bin <path>   --codex-bin <path>   --help
$ErrorActionPreference = 'Continue'  # native commands report through exit codes, checked below

$RepoUrl = if ($env:AGENTIC_GITHUB_FLOW_REPO) { $env:AGENTIC_GITHUB_FLOW_REPO } else { 'https://github.com/IgorVerm/agentic-github-flow.git' }
$Target = Join-Path $env:USERPROFILE '.agentic-github-flow'

function Find-Python {
    foreach ($candidate in @(@('py', '-3'), @('python'), @('python3'))) {
        $exe = $candidate[0]
        $rest = @($candidate | Select-Object -Skip 1)
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        & $exe @rest -c 'import sys; sys.exit(sys.version_info < (3, 8))' 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { return ,$candidate }
    }
    return $null
}

$python = Find-Python
if (-not $python) {
    Write-Host 'STOP  agentic-github-flow needs Python 3.8 or newer (for example: winget install Python.Python.3.12). Install it, then run this again.'
    exit 3
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host 'STOP  agentic-github-flow needs Git for Windows (winget install Git.Git). Install it, then run this again.'
    exit 3
}

$installer = Join-Path $Target 'tools\installer.py'
if (-not (Test-Path $installer)) {
    if (Test-Path $Target) {
        Write-Host "STOP  $Target exists but is not an agentic-github-flow clone; move it away first."
        exit 3
    }
    if ($args -contains '--uninstall') {
        Write-Host "STOP  nothing to uninstall: $Target does not exist."
        exit 3
    }
    git clone --quiet $RepoUrl $Target
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "ok    cloned $RepoUrl into $Target"
}

$exe = $python[0]
$rest = @($python | Select-Object -Skip 1)
& $exe @rest $installer @args
exit $LASTEXITCODE
