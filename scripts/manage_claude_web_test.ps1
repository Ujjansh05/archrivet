param(
    [ValidateSet('Start', 'Status', 'Stop', 'ReloadServer')]
    [string]$Action = 'Start',
    [string]$BundleDirectory = '',
    [ValidateSet('Rules', 'Laya')]
    [string]$Profile = 'Rules',
    [string]$Checkpoint = ''
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$runtimeDir = Join-Path $projectRoot $(if ($Profile -eq 'Laya') { '.runtime\claude-web-test-laya' } else { '.runtime\claude-web-test' })
$defaultBundleDir = Join-Path $projectRoot '.runtime\claude-code-extracted\archrivet'
$bundlePathFile = Join-Path $runtimeDir 'bundle-path.txt'
$bundleDir = if ($BundleDirectory) { $BundleDirectory } elseif (Test-Path -LiteralPath $bundlePathFile) {
    (Get-Content -LiteralPath $bundlePathFile -Raw).Trim()
} else { $defaultBundleDir }
$pythonExe = if ($Profile -eq 'Laya') {
    [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($projectRoot, '..', 'architecture-review-plugin', '.venv', 'Scripts', 'python.exe'))
} else { [System.IO.Path]::Combine($bundleDir, 'runtime', 'python.exe') }
$checkpointDir = if ($Checkpoint) { $Checkpoint } else { Join-Path $projectRoot '.runtime\laya-web-test-checkpoint' }
$backendArgs = if ($Profile -eq 'Laya') { @('--backend', 'laya', '--checkpoint', $checkpointDir) } else { @() }
$hostScript = Join-Path $PSScriptRoot 'claude_web_test_host.py'
$statePath = Join-Path $runtimeDir 'processes.json'
$urlPath = Join-Path $runtimeDir 'connector-url.txt'
$secretPath = Join-Path $runtimeDir 'secret.txt'
$listenPort = if ($Profile -eq 'Laya') { 8767 } else { 8765 }
$tunnelExe = (Get-Command cloudflared.exe -ErrorAction SilentlyContinue).Source

function Get-TrackedProcess([int]$processId, [string]$expectedExe, [string]$expectedStartTime) {
    if ($processId -le 0) { return $null }
    $observed = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($null -eq $observed) { return $null }
    if ($observed.Path -ne $expectedExe) { return $null }
    if ($expectedStartTime) {
        $difference = ($observed.StartTime.ToUniversalTime() -
            ([datetime]::Parse($expectedStartTime)).ToUniversalTime()).TotalSeconds
        if ([Math]::Abs($difference) -gt 3) { return $null }
    }
    return $observed
}

function Read-SharedText([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) { return '' }
    $stream = [System.IO.File]::Open($path, 'Open', 'Read', 'ReadWrite')
    try {
        $reader = [System.IO.StreamReader]::new($stream)
        try { return $reader.ReadToEnd() } finally { $reader.Dispose() }
    } finally { $stream.Dispose() }
}

function Get-State {
    if (-not (Test-Path -LiteralPath $statePath)) { return $null }
    return Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
}

function Stop-Tracked($state) {
    if ($null -eq $state) { return }
    $tunnel = Get-TrackedProcess ([int]$state.tunnel_pid) ([string]$state.tunnel_exe) ([string]$state.tunnel_started)
    if ($null -ne $tunnel) { Stop-Process -Id $tunnel.Id -Force }
    $server = Get-TrackedProcess ([int]$state.server_pid) ([string]$state.python_exe) ([string]$state.server_started)
    if ($null -ne $server) { Stop-Process -Id $server.Id -Force }
}

function Start-TestServer([string]$candidateBundle, [string]$candidatePython, [string]$stamp) {
    $serverLog = Join-Path $runtimeDir "server-$stamp.log"
    $serverErrorLog = Join-Path $runtimeDir "server-$stamp.err.log"
    $process = Start-Process -FilePath $candidatePython -ArgumentList (@('-I', '-B', $hostScript,
        'serve', '--bundle', $candidateBundle, '--directory', $runtimeDir, '--port', "$listenPort") + $backendArgs) `
        -WindowStyle Hidden -PassThru -RedirectStandardOutput $serverLog -RedirectStandardError $serverErrorLog
    $secret = (Get-Content -LiteralPath $secretPath -Raw).Trim()
    for ($attempt = 0; $attempt -lt 80; $attempt++) {
        Start-Sleep -Milliseconds 250
        if ($process.HasExited) { break }
        try {
            $request = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"archrivet-reload","version":"1"}}}'
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$listenPort/$secret/mcp" -Method Post `
                -ContentType 'application/json' -Headers @{Accept='application/json, text/event-stream'} `
                -Body $request -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { return $process }
        } catch { }
    }
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    throw "Local MCP server did not become ready; inspect $serverErrorLog"
}

function Save-ServerState($state, $process, [string]$candidateBundle, [string]$candidatePython) {
    $state.server_pid = $process.Id
    $state.server_started = $process.StartTime.ToString('o')
    $state.python_exe = $candidatePython
    if ($state.PSObject.Properties['bundle_dir']) {
        $state.bundle_dir = $candidateBundle
    } else {
        $state | Add-Member -NotePropertyName bundle_dir -NotePropertyValue $candidateBundle
    }
    $state | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
}

if ($Action -eq 'Status') {
    $state = Get-State
    if ($null -eq $state) { 'ArchRivet Claude web test: stopped'; exit 0 }
    $server = Get-TrackedProcess ([int]$state.server_pid) ([string]$state.python_exe) ([string]$state.server_started)
    $tunnel = Get-TrackedProcess ([int]$state.tunnel_pid) ([string]$state.tunnel_exe) ([string]$state.tunnel_started)
    if ($null -ne $server -and $null -ne $tunnel) {
        'ArchRivet Claude web test: running'
        "Connector URL file: $urlPath"
        'Keep the PC awake and connected to the internet.'
    } else {
        'ArchRivet Claude web test: stopped or incomplete; run Start again.'
    }
    exit 0
}

if ($Action -eq 'ReloadServer') {
    $state = Get-State
    if ($null -eq $state) { throw 'Start the Claude web test before reloading its server.' }
    $oldServer = Get-TrackedProcess ([int]$state.server_pid) ([string]$state.python_exe) ([string]$state.server_started)
    $tunnel = Get-TrackedProcess ([int]$state.tunnel_pid) ([string]$state.tunnel_exe) ([string]$state.tunnel_started)
    if ($null -eq $oldServer -or $null -eq $tunnel) { throw 'The server and tunnel must both be running before a reload.' }
    if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) { throw "Missing candidate runtime: $pythonExe" }
    $bundleDir = (Resolve-Path -LiteralPath $bundleDir).Path
    $oldBundle = if ($state.PSObject.Properties['bundle_dir']) { [string]$state.bundle_dir } else { $defaultBundleDir }
    $oldPython = [string]$state.python_exe
    & $pythonExe -I -B $hostScript init --bundle $bundleDir --directory $runtimeDir | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Candidate server failed initialization; the current server remains running.' }
    Stop-Process -Id $oldServer.Id -Force
    try {
        $replacement = Start-TestServer $bundleDir $pythonExe (Get-Date -Format 'yyyyMMdd-HHmmss')
        Save-ServerState $state $replacement $bundleDir $pythonExe
        [System.IO.File]::WriteAllText($bundlePathFile, "$bundleDir`n")
        'ArchRivet Claude web test: server reloaded; existing connector URL preserved.'
    } catch {
        $failure = $_.Exception.Message
        try {
            $restored = Start-TestServer $oldBundle $oldPython (Get-Date -Format 'yyyyMMdd-HHmmss')
            Save-ServerState $state $restored $oldBundle $oldPython
        } catch {
            throw "Server reload failed and rollback failed: $failure; $($_.Exception.Message)"
        }
        throw "Server reload failed; previous server restored: $failure"
    }
    exit 0
}

if ($Action -eq 'Stop') {
    Stop-Tracked (Get-State)
    foreach ($path in @($statePath, $urlPath)) {
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
    }
    'ArchRivet Claude web test: stopped. The URL secret remains for the next local test.'
    exit 0
}

if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
    throw "The Python runtime is missing: $pythonExe"
}
if ($Profile -eq 'Laya' -and -not (Test-Path -LiteralPath (Join-Path $checkpointDir 'rl_agent_config.json') -PathType Leaf)) {
    throw "The trained Laya checkpoint is missing: $checkpointDir"
}
if (-not $tunnelExe) { throw 'cloudflared.exe is required for the temporary HTTPS tunnel.' }
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
$state = Get-State
if ($null -ne $state) {
    $server = Get-TrackedProcess ([int]$state.server_pid) ([string]$state.python_exe) ([string]$state.server_started)
    $tunnel = Get-TrackedProcess ([int]$state.tunnel_pid) ([string]$state.tunnel_exe) ([string]$state.tunnel_started)
    if ($null -ne $server -and $null -ne $tunnel) {
        'ArchRivet Claude web test is already running.'
        "Connector URL file: $urlPath"
        exit 0
    }
    Stop-Tracked $state
}

$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $listenPort)
try { $listener.Start() } catch { throw "Port $listenPort is already in use. Stop the other server first." }
finally { $listener.Stop() }

& $pythonExe -I -B $hostScript init --bundle $bundleDir --directory $runtimeDir | Out-Null
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $secretPath)) {
    throw 'Could not initialize the private URL secret.'
}
$secret = (Get-Content -LiteralPath $secretPath -Raw).Trim()
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$serverLog = Join-Path $runtimeDir "server-$stamp.log"
$serverErrorLog = Join-Path $runtimeDir "server-$stamp.err.log"
$tunnelLog = Join-Path $runtimeDir "tunnel-$stamp.log"
$tunnelErrorLog = Join-Path $runtimeDir "tunnel-$stamp.err.log"
$serverProcess = $null
$tunnelProcess = $null
try {
    $serverProcess = Start-Process -FilePath $pythonExe -ArgumentList (@('-I', '-B', $hostScript,
        'serve', '--bundle', $bundleDir, '--directory', $runtimeDir, '--port', "$listenPort") + $backendArgs) `
        -WindowStyle Hidden -PassThru -RedirectStandardOutput $serverLog -RedirectStandardError $serverErrorLog
    $initialized = $false
    for ($attempt = 0; $attempt -lt 80; $attempt++) {
        Start-Sleep -Milliseconds 250
        if ($serverProcess.HasExited) { throw "Local MCP server exited; inspect $serverErrorLog" }
        try {
            $request = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"archrivet-start","version":"1"}}}'
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$listenPort/$secret/mcp" -Method Post `
                -ContentType 'application/json' -Headers @{Accept='application/json, text/event-stream'} `
                -Body $request -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { $initialized = $true; break }
        } catch { }
    }
    if (-not $initialized) { throw "Local MCP server did not become ready; inspect $serverErrorLog" }

    $tunnelProcess = Start-Process -FilePath $tunnelExe -ArgumentList @('tunnel', '--url',
        "http://127.0.0.1:$listenPort", '--protocol', 'http2', '--no-autoupdate') -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $tunnelLog -RedirectStandardError $tunnelErrorLog
    $baseUrl = $null
    for ($attempt = 0; $attempt -lt 180; $attempt++) {
        Start-Sleep -Milliseconds 500
        if ($tunnelProcess.HasExited) { throw "HTTPS tunnel exited; inspect $tunnelErrorLog" }
        $match = [regex]::Match((Read-SharedText $tunnelErrorLog), 'https://[a-z0-9-]+\.trycloudflare\.com')
        if ($match.Success) { $baseUrl = $match.Value; break }
    }
    if (-not $baseUrl) { throw "Tunnel URL was not reported; inspect $tunnelErrorLog" }

    $publicReady = $false
    for ($attempt = 0; $attempt -lt 80; $attempt++) {
        Start-Sleep -Milliseconds 500
        if ($tunnelProcess.HasExited) { throw "HTTPS tunnel exited before becoming ready; inspect $tunnelErrorLog" }
        try {
            $response = Invoke-WebRequest -Uri "$baseUrl/$secret/mcp" -Method Post `
                -ContentType 'application/json' -Headers @{Accept='application/json, text/event-stream'} `
                -Body $request -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -eq 200) { $publicReady = $true; break }
        } catch { }
    }
    if (-not $publicReady) { throw "Public MCP endpoint did not become ready; inspect $tunnelErrorLog" }

    [System.IO.File]::WriteAllText($urlPath, "$baseUrl/$secret/mcp`n")
    @{
        server_pid = $serverProcess.Id
        tunnel_pid = $tunnelProcess.Id
        server_started = $serverProcess.StartTime.ToString('o')
        tunnel_started = $tunnelProcess.StartTime.ToString('o')
        python_exe = $pythonExe
        bundle_dir = $bundleDir
        tunnel_exe = $tunnelExe
        base_url = $baseUrl
        started_at = (Get-Date).ToString('o')
    } | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
    [System.IO.File]::WriteAllText($bundlePathFile, "$bundleDir`n")
    'ArchRivet Claude web test: running in the background.'
    "Connector URL file: $urlPath"
    'Show the private URL locally with: Get-Content -LiteralPath "' + $urlPath + '"'
    'Keep this PC awake and online; the temporary tunnel address changes after restart.'
} catch {
    if ($null -ne $tunnelProcess -and -not $tunnelProcess.HasExited) { Stop-Process -Id $tunnelProcess.Id -Force }
    if ($null -ne $serverProcess -and -not $serverProcess.HasExited) { Stop-Process -Id $serverProcess.Id -Force }
    throw
}
