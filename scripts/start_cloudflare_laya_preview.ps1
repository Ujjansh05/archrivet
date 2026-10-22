param(
    [string]$Python = 'H:\archrivet-gpu-runtime\venv\Scripts\python.exe',
    [string]$Cloudflared = 'C:\Program Files (x86)\cloudflared\cloudflared.exe'
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runtime = Join-Path $repo '.runtime\live'
$workerUrl = 'https://archrivet-mcp.humour-hub-beta.workers.dev'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
if (-not (Test-Path -LiteralPath $Python)) { throw "Python runtime missing: $Python" }
if (-not (Test-Path -LiteralPath $Cloudflared)) { throw "cloudflared missing: $Cloudflared" }
if (-not (Test-Path -LiteralPath (Join-Path $runtime 'settings.json'))) {
    throw 'Laya is not configured. Run arch_review configure with the merged checkpoint first.'
}

$env:PYTHONPATH = Join-Path $repo 'src'
$env:ARCH_REVIEW_HOME = $runtime
& $Python -m arch_review start | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Laya review service did not start' }

$tokenFile = Join-Path $runtime 'http-token.txt'
if (-not (Test-Path -LiteralPath $tokenFile)) {
    $bytes = New-Object byte[] 48
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    [System.IO.File]::WriteAllText($tokenFile, [Convert]::ToBase64String($bytes))
}
$env:ARCH_REVIEW_HTTP_TOKEN = (Get-Content -LiteralPath $tokenFile -Raw).Trim()
if ($env:ARCH_REVIEW_HTTP_TOKEN.Length -lt 32) { throw 'The local HTTP token is too short' }

if (-not (Get-NetTCPConnection -LocalPort 8789 -State Listen -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $Python -ArgumentList @('-m', 'arch_review', 'mcp-http', '--port', '8789') `
        -WorkingDirectory $repo -RedirectStandardOutput (Join-Path $runtime 'mcp-http.out.log') `
        -RedirectStandardError (Join-Path $runtime 'mcp-http.err.log') -WindowStyle Hidden | Out-Null
}
$httpReady = $false
for ($i = 0; $i -lt 150; $i++) {
    if (Get-NetTCPConnection -LocalPort 8789 -State Listen -ErrorAction SilentlyContinue) {
        $httpReady = $true
        break
    }
    Start-Sleep -Seconds 2
}
if (-not $httpReady) { throw 'Laya HTTP MCP warmup failed; inspect .runtime\live\mcp-http.err.log' }

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$tunnelLog = Join-Path $runtime "cloudflared-$stamp.err.log"
$tunnel = Start-Process -FilePath $Cloudflared `
    -ArgumentList @('tunnel', '--url', 'http://127.0.0.1:8789', '--http-host-header', '127.0.0.1:8789', '--no-autoupdate') `
    -WorkingDirectory $runtime -RedirectStandardOutput (Join-Path $runtime "cloudflared-$stamp.out.log") `
    -RedirectStandardError $tunnelLog -WindowStyle Hidden -PassThru
$origin = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    $log = Get-Content -LiteralPath $tunnelLog -Raw -ErrorAction SilentlyContinue
    if ($log -match '(https://[a-z0-9-]+\.trycloudflare\.com)') {
        $origin = $Matches[1] + '/'
        break
    }
    if ($tunnel.HasExited) { throw "Cloudflare tunnel exited; inspect $tunnelLog" }
}
if (-not $origin) { throw "Cloudflare tunnel did not provide a URL; inspect $tunnelLog" }

Push-Location (Join-Path $repo 'cloudflare')
try {
    $origin | npx.cmd wrangler secret put LAYA_ORIGIN_URL | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not update LAYA_ORIGIN_URL in Cloudflare' }
    $env:ARCH_REVIEW_HTTP_TOKEN | npx.cmd wrangler secret put LAYA_ORIGIN_TOKEN | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not update LAYA_ORIGIN_TOKEN in Cloudflare' }
} finally {
    Pop-Location
}

$headers = @{'Accept' = 'application/json, text/event-stream'; 'Content-Type' = 'application/json';
             'MCP-Protocol-Version' = '2025-06-18'}
$initialize = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"archrivet-restart-check","version":"1.0"}}}'
$reply = Invoke-RestMethod -Uri ($workerUrl + '/mcp') -Method Post -Headers $headers -Body $initialize -TimeoutSec 30
if ($reply.result.serverInfo.name -ne 'architecture-review') { throw 'Public MCP handshake failed' }

[System.IO.File]::WriteAllText((Join-Path $runtime 'current-tunnel-pid.txt'), [string]$tunnel.Id)
Write-Output "ArchRivet Laya MCP is connected: $workerUrl/mcp"
Write-Output 'The model runs on this PC. Keep it awake and online; this quick tunnel changes after restart.'
