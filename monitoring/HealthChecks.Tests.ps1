. "$PSScriptRoot/HealthChecks.ps1"

Describe 'Independent service health checks' {
    BeforeEach {
        $script:root = Join-Path $TestDrive 'repo'
        New-Item -ItemType Directory -Path (Join-Path $script:root '.tunnel-client') -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $script:root '.tunnel-client/mcp-key') -Value ('x' * 32)
        Mock Invoke-WebRequest {
            param($Uri, $Body)
            if ($Uri -like '*/_stcore/health') { return @{ StatusCode = 200; Content = 'ok' } }
            if ($Uri -like '*/readyz') { return @{ StatusCode = 200; Content = 'ready' } }
            $request = $Body | ConvertFrom-Json
            if ($request.method -eq 'initialize') {
                return @{ Content = '{"jsonrpc":"2.0","id":1,"result":{"serverInfo":{"name":"company-customer-bot"},"protocolVersion":"2024-11-05"}}' }
            }
            return @{ Content = '{"jsonrpc":"2.0","id":2,"result":{"isError":false,"structuredContent":{"success":true,"data":{"current_time":"09:00:00"}}}}' }
        }
    }

    It 'checks the UI, tunnel and a real authenticated MCP tool response' {
        $checks = @(Get-CompanyHealth $script:root)
        $checks.Count | Should Be 3
        @($checks | Where-Object { !$_.Healthy }).Count | Should Be 0
        Assert-MockCalled Invoke-WebRequest -Times 1 -Exactly -ParameterFilter {
            $null -ne $Headers -and $Headers['X-Company-Tunnel-Key'] -eq ('x' * 32) -and $Body -like '*tools/call*'
        }
    }

    It 'still checks MCP if the agent web service is down' {
        Mock Invoke-WebRequest { throw 'Connection refused' } -ParameterFilter { $Uri -like '*/_stcore/health' }
        $checks = @(Get-CompanyHealth $script:root)
        $checks[0].Healthy | Should Be $false
        $checks[2].Healthy | Should Be $true
    }

    It 'does not accept a generic HTTP 200 page as Streamlit health' {
        Mock Invoke-WebRequest { return @{ StatusCode = 200; Content = '<html>login</html>' } } -ParameterFilter { $Uri -like '*/_stcore/health' }
        (Get-CompanyHealth $script:root)[0].Healthy | Should Be $false
    }

    It 'detects an MCP tool error even when HTTP succeeds' {
        Mock Invoke-WebRequest { return @{ Content = '{"jsonrpc":"2.0","id":2,"result":{"isError":true}}' } } -ParameterFilter { $Body -like '*tools/call*' }
        (Get-CompanyHealth $script:root)[2].Healthy | Should Be $false
    }

    It 'rejects a mismatched JSON RPC response ID' {
        Mock Invoke-WebRequest { return @{ Content = '{"jsonrpc":"2.0","id":99,"result":{"serverInfo":{"name":"wrong"}}}' } } -ParameterFilter { $Body -like '*initialize*' }
        (Get-CompanyHealth $script:root)[2].Healthy | Should Be $false
    }

    It 'does not expose secrets or server response bodies in a failure' {
        Mock Invoke-WebRequest { throw 'private response and secret' } -ParameterFilter { $Uri -like '*/mcp' }
        $checks = @(Get-CompanyHealth $script:root)
        $checks[2].Healthy | Should Be $false
        ($checks | ConvertTo-Json) | Should Not Match 'private response|secret|xxxxxxxx'
    }
}
