. "$PSScriptRoot/MonitorRuntime.ps1"

Describe 'Daily notification lifecycle' {
    BeforeEach {
        $script:stateDir = Join-Path $TestDrive ([Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $script:stateDir | Out-Null
        Mock Get-CompanyHealth { [pscustomobject]@{ Name = 'MCP'; Healthy = $true; Detail = 'Responding' } }
        Mock Send-MonitorMail { return $true }
    }

    It 'does not email when healthy with no previous incident' {
        Invoke-MonitorRun @{} $script:stateDir 'repo'
        Assert-MockCalled Send-MonitorMail -Times 0 -Exactly -Scope It
    }

    It 'emails on failure and sends one recovery notification' {
        Mock Get-CompanyHealth { [pscustomobject]@{ Name = 'MCP'; Healthy = $false; Detail = 'Unavailable' } }
        Invoke-MonitorRun @{} $script:stateDir 'repo'
        (Get-Content (Join-Path $script:stateDir 'state.json') -Raw | ConvertFrom-Json).IncidentNotified | Should Be $true
        Mock Get-CompanyHealth { [pscustomobject]@{ Name = 'MCP'; Healthy = $true; Detail = 'Responding' } }
        Invoke-MonitorRun @{} $script:stateDir 'repo'
        Invoke-MonitorRun @{} $script:stateDir 'repo'
        Assert-MockCalled Send-MonitorMail -Times 2 -Exactly -Scope It
        (Get-Content (Join-Path $script:stateDir 'state.json') -Raw | ConvertFrom-Json).IncidentNotified | Should Be $false
    }

    It 'sends nothing and performs no probes after STOP' {
        Set-Content (Join-Path $script:stateDir 'paused') ''
        Invoke-MonitorRun @{} $script:stateDir 'repo'
        Assert-MockCalled Send-MonitorMail -Times 0 -Exactly -Scope It
        Assert-MockCalled Get-CompanyHealth -Times 0 -Exactly -Scope It
    }

    It 'does not mark a failed email as delivered' {
        Mock Get-CompanyHealth { [pscustomobject]@{ Name = 'MCP'; Healthy = $false; Detail = 'Unavailable' } }
        Mock Send-MonitorMail { throw 'SMTP unavailable' }
        { Invoke-MonitorRun @{} $script:stateDir 'repo' } | Should Throw
        (Get-Content (Join-Path $script:stateDir 'state.json') -Raw | ConvertFrom-Json).IncidentNotified | Should Be $false
    }

    It 'retains an undelivered recovery for the next run' {
        Set-Content (Join-Path $script:stateDir 'state.json') '{"IncidentNotified":true}'
        Mock Send-MonitorMail { throw 'SMTP unavailable' }
        { Invoke-MonitorRun @{} $script:stateDir 'repo' } | Should Throw
        (Get-Content (Join-Path $script:stateDir 'state.json') -Raw | ConvertFrom-Json).IncidentNotified | Should Be $true
    }
}

Describe 'STOP immediately before SMTP submission' {
    It 'does not access credentials or start SMTP if already paused' {
        $stateDir = Join-Path $TestDrive 'paused-send'
        New-Item -ItemType Directory -Path $stateDir | Out-Null
        Set-Content (Join-Path $stateDir 'paused') ''
        Send-MonitorMail @{} $stateDir 'test' 'test' | Should Be $false
    }
}

Describe 'Windows PowerShell SMTP subprocess integration' {
    It 'passes encrypted credentials through the input pipe and reports a refused SMTP connection safely' {
        $stateDir = Join-Path $TestDrive 'smtp-pipe'
        New-Item -ItemType Directory -Path $stateDir | Out-Null
        $secret = ConvertTo-SecureString 'test-password-not-real' -AsPlainText -Force
        try { ConvertFrom-SecureString $secret | Set-Content (Join-Path $stateDir 'smtp-password.dpapi') }
        finally { $secret.Dispose() }
        $config = @{
            Address = 'test@example.test'; SmtpUsername = 'test@example.test'; SmtpHost = '127.0.0.1'; SmtpPort = 1
            ControlPort = 18761; StopToken = 'test-token'
            PythonPath = Join-Path (Split-Path $PSScriptRoot -Parent) '.uv-python/cpython-3.12.14-windows-x86_64-none/python.exe'
        }
        $failure = $null
        try { Send-MonitorMail $config $stateDir 'test' 'test' } catch { $failure = $_.Exception.Message }
        $failure | Should Be 'SMTP delivery failed (ConnectionRefusedError).'
    }
}
