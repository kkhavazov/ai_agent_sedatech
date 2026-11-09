param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
$tunnelBinary = Join-Path $PSScriptRoot '.tunnel-client\tunnel-client.exe'
$tunnelConfig = Join-Path $PSScriptRoot '.tunnel-client\profiles\company-bot.yaml'
$mcpKeyFile = Join-Path $PSScriptRoot '.tunnel-client\mcp-key'
if (!(Test-Path -LiteralPath $mcpKeyFile)) {
    throw 'Missing .tunnel-client/mcp-key. Generate the shared local MCP secret before starting.'
}
$mcpAuthOptions = @('--mcp.extra-headers', "X-Company-Tunnel-Key: file:$mcpKeyFile",
                    '--mcp.discovery-extra-headers', "X-Company-Tunnel-Key: file:$mcpKeyFile")
if (!(Test-Path -LiteralPath $tunnelBinary) -or !(Test-Path -LiteralPath $tunnelConfig)) {
    throw 'The workspace-local tunnel-client binary or company-bot profile is missing.'
}

# Keep the runtime key only in this process environment; never write it to disk
# or pass its literal value on the command line. Restore any prior environment.
$previousTunnelKey = $env:CONTROL_PLANE_API_KEY
$secretInput = $null
try {
    if ([string]::IsNullOrWhiteSpace($env:CONTROL_PLANE_API_KEY)) {
        Write-Host 'Enter a runtime API key with Tunnels Read + Use (not an admin key).'
        $secretInput = Read-Host 'Runtime API key (hidden input)' -AsSecureString
        $secretPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secretInput)
        try {
            $env:CONTROL_PLANE_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPointer)
        } finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPointer)
        }
    }
    if ([string]::IsNullOrWhiteSpace($env:CONTROL_PLANE_API_KEY)) {
        throw 'No runtime API key was entered.'
    }
    & $tunnelBinary doctor --config $tunnelConfig @mcpAuthOptions --explain
    if ($LASTEXITCODE -ne 0) {
        throw 'Tunnel diagnostics failed. Resolve the reported checks and rerun this script.'
    }
    if (!$CheckOnly) {
        Write-Host 'Starting the tunnel. Keep this terminal open; Ctrl+C stops it.'
        Write-Host 'Local status UI: http://127.0.0.1:8091/ui'
        & $tunnelBinary run --config $tunnelConfig @mcpAuthOptions
        if ($LASTEXITCODE -ne 0) { throw 'Tunnel client exited with an error.' }
    }
} finally {
    $env:CONTROL_PLANE_API_KEY = $previousTunnelKey
    if ($null -ne $secretInput) { $secretInput.Dispose() }
}
