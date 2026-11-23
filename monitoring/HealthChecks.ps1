# Independent probes: no imports from the agent and no Docker dependency.
function Invoke-CompanyMcpRequest {
    param([string]$Url, [hashtable]$Headers, [string]$Method, [hashtable]$Parameters, [int]$Id)
    $body = @{ jsonrpc = '2.0'; id = $Id; method = $Method; params = $Parameters } | ConvertTo-Json -Depth 12 -Compress
    $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -Method Post -Headers $Headers -ContentType 'application/json' -Body $body -TimeoutSec 15 -MaximumRedirection 0
    $message = $response.Content | ConvertFrom-Json
    if ($message.jsonrpc -ne '2.0' -or $message.id -ne $Id -or $message.error -or $null -eq $message.result) {
        throw 'Invalid or failed MCP response.'
    }
    return $message.result
}

function Get-CompanyHealth {
    param([string]$RepositoryRoot)
    $checks = @(
        @{ Name = 'AI Agent web service'; Url = 'http://127.0.0.1:8503/_stcore/health'; Expected = 'ok' },
        @{ Name = 'MCP tunnel readiness'; Url = 'http://127.0.0.1:8091/readyz'; Expected = $null }
    )
    foreach ($check in $checks) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $check.Url -TimeoutSec 15 -MaximumRedirection 0
            if ($response.StatusCode -ne 200 -or ($check.Expected -and $response.Content.Trim() -ne $check.Expected)) {
                throw 'Unexpected health response.'
            }
            [pscustomobject]@{ Name = $check.Name; Healthy = $true; Detail = 'Responding' }
        } catch {
            # Do not include response bodies, headers, credentials or customer data in alerts.
            [pscustomobject]@{ Name = $check.Name; Healthy = $false; Detail = 'Health endpoint unavailable or returned an unexpected response' }
        }
    }
    try {
        $secret = [IO.File]::ReadAllText((Join-Path $RepositoryRoot '.tunnel-client/mcp-key')).Trim()
        if (!$secret) { throw 'Missing MCP credential.' }
        $headers = @{ 'X-Company-Tunnel-Key' = $secret; Accept = 'application/json, text/event-stream' }
        $url = 'http://127.0.0.1:8001/mcp'
        $initialized = Invoke-CompanyMcpRequest -Url $url -Headers $headers -Method 'initialize' -Id 1 -Parameters @{
            protocolVersion = '2024-11-05'; capabilities = @{}; clientInfo = @{ name = 'company-health-monitor'; version = '1' }
        }
        if (!$initialized.serverInfo.name -or !$initialized.protocolVersion) { throw 'MCP initialization failed.' }
        # This repository uses stateless JSON MCP, so no session needs to be retained.
        $headers['MCP-Protocol-Version'] = $initialized.protocolVersion
        $result = Invoke-CompanyMcpRequest -Url $url -Headers $headers -Method 'tools/call' -Id 2 -Parameters @{
            name = 'inventory_get_current_time'; arguments = @{}
        }
        if ($result.isError) { throw 'MCP tool failed.' }
        $payload = $result.structuredContent
        if (!$payload) { $payload = ($result.content | Where-Object { $_.type -eq 'text' } | Select-Object -First 1).text | ConvertFrom-Json }
        if ($payload.error -or $payload.success -eq $false) { throw 'Inventory handler failed.' }
        if ($payload.data) { $payload = $payload.data }
        if (!$payload.current_time) { throw 'MCP tool returned no time.' }
        [pscustomobject]@{ Name = 'MCP authenticated tool call'; Healthy = $true; Detail = 'Initialization and current-time tool succeeded' }
    } catch {
        [pscustomobject]@{ Name = 'MCP authenticated tool call'; Healthy = $false; Detail = 'Authentication, initialization or tool execution failed; inspect MCP logs' }
    } finally {
        $secret = $null
        $headers = $null
    }
}
