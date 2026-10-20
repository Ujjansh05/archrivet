param([string]$Python)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
    $candidates = @(
        (Join-Path $projectRoot '.venv\Scripts\python.exe'),
        (Join-Path (Split-Path -Parent $projectRoot) 'architecture-review-plugin\.venv\Scripts\python.exe')
    )
    $Python = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $Python) { $Python = (Get-Command python -ErrorAction Stop).Source }
}
$previousPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $projectRoot 'src'
    & $Python -m arch_review viewer-demo --animate
    if ($LASTEXITCODE -ne 0) { throw 'Preview stopped with an error. See the output above.' }
} finally {
    $env:PYTHONPATH = $previousPath
}
