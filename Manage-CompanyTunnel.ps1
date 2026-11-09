param(
    [ValidateSet('Install', 'Run', 'Start', 'Status', 'Stop', 'Remove')]
    [string]$Action = 'Status'
)

$ErrorActionPreference = 'Stop'
$taskName = 'CompanyBot-Tunnel'
$stateDir = Join-Path $PSScriptRoot '.tunnel-client'
$keyPath = Join-Path $stateDir 'runtime-key.dpapi'
$binary = Join-Path $stateDir 'tunnel-client.exe'
$config = Join-Path $stateDir 'profiles\company-bot.yaml'
$mcpSecretPath = Join-Path $stateDir 'mcp-key'
$logDir = Join-Path $stateDir 'logs'

function Write-TunnelLog([string]$Line) {
    # Redact literal credentials before persisting any process output.
    foreach ($value in @($env:CONTROL_PLANE_API_KEY, $script:mcpSecret)) {
        if (![string]::IsNullOrEmpty($value)) { $Line = $Line.Replace($value, '[REDACTED]') }
    }
    $Line = $Line -replace 'sk-[A-Za-z0-9_-]+', '[REDACTED]'
    $logPath = Join-Path $logDir 'tunnel.log'
    if ((Test-Path -LiteralPath $logPath) -and (Get-Item -LiteralPath $logPath).Length -ge 10MB) {
        for ($i = 4; $i -ge 1; $i--) {
            $source = "$logPath.$i"
            if (Test-Path -LiteralPath $source) { Move-Item -LiteralPath $source -Destination "$logPath.$($i + 1)" -Force }
        }
        Move-Item -LiteralPath $logPath -Destination "$logPath.1" -Force
    }
    Add-Content -LiteralPath $logPath -Value "$(Get-Date -Format o) $Line" -Encoding UTF8
}

switch ($Action) {
    'Install' {
        foreach ($path in @($binary, $config, $mcpSecretPath)) {
            if (!(Test-Path -LiteralPath $path)) { throw "Required file is missing: $path" }
        }
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
            throw 'Task already exists. Use Status/Start, or Remove before reinstalling.'
        }
        $secret = Read-Host 'OpenAI runtime API key (hidden; Tunnels Read + Use)' -AsSecureString
        try {
            if ($secret.Length -eq 0) { throw 'API key cannot be empty.' }
            # Windows DPAPI ties this encrypted value to this user on this PC.
            $encrypted = ConvertFrom-SecureString $secret
            [IO.File]::WriteAllText($keyPath, $encrypted)
        } finally { $secret.Dispose() }
        $acl = New-Object Security.AccessControl.FileSecurity
        $acl.SetAccessRuleProtection($true, $false)
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($identity.User, 'FullControl', 'Allow')))
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule('SYSTEM', 'FullControl', 'Allow')))
        Set-Acl -LiteralPath $keyPath -AclObject $acl

        $powershellExe = Join-Path $PSHOME 'powershell.exe'
        $taskAction = New-ScheduledTaskAction -Execute $powershellExe -WorkingDirectory $PSScriptRoot -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Action Run"
        $trigger = @(
            New-ScheduledTaskTrigger -AtLogOn -User $identity.Name
            New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
        )
        $principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $trigger -Principal $principal -Settings $settings -Description 'Company MCP tunnel; starts at user sign-in, restarts on failure, logs with credential redaction.' | Out-Null
        Write-Host 'Installed. Close the old foreground tunnel with Ctrl+C, then run:'
        Write-Host '.\Manage-CompanyTunnel.ps1 -Action Start'
    }
    'Run' {
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        $secret = $null
        try {
            $secret = Get-Content -LiteralPath $keyPath -Raw | ConvertTo-SecureString
            $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
            try { $env:CONTROL_PLANE_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
            finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
            $script:mcpSecret = [IO.File]::ReadAllText($mcpSecretPath).Trim()
            Write-TunnelLog 'Starting tunnel-client under Task Scheduler.'
            # Native stderr is diagnostic output, not a terminating PowerShell error.
            $ErrorActionPreference = 'Continue'
            & $binary run --config $config --mcp.extra-headers "X-Company-Tunnel-Key: file:$mcpSecretPath" --mcp.discovery-extra-headers "X-Company-Tunnel-Key: file:$mcpSecretPath" 2>&1 | ForEach-Object { Write-TunnelLog ([string]$_) }
            $exitCode = $LASTEXITCODE
            $ErrorActionPreference = 'Stop'
            Write-TunnelLog "Tunnel process exited with code $exitCode. Scheduler will retry."
        } catch {
            Write-TunnelLog "Tunnel supervisor failed: $($_.Exception.Message)"
        } finally {
            Remove-Item Env:CONTROL_PLANE_API_KEY -ErrorAction SilentlyContinue
            if ($null -ne $secret) { $secret.Dispose() }
            $script:mcpSecret = $null
        }
        # Even an unexpected clean exit should restart this long-lived service.
        exit 1
    }
    'Start' {
        $task = Get-ScheduledTask -TaskName $taskName
        Enable-ScheduledTask -TaskName $taskName | Out-Null
        if ($task.State -eq 'Running') { Write-Host 'Scheduled tunnel is already running.'; break }
        $listener = New-Object Net.Sockets.TcpClient
        try {
            $listener.Connect('127.0.0.1', 8091)
            throw 'Port 8091 is already in use. Stop the old foreground tunnel before starting the task.'
        } catch [Net.Sockets.SocketException] {
            Start-ScheduledTask -TaskName $taskName
            Write-Host 'Task started. Run -Action Status to verify readiness.'
        } finally { $listener.Dispose() }
    }
    'Status' {
        $task = Get-ScheduledTask -TaskName $taskName
        $info = Get-ScheduledTaskInfo -TaskName $taskName
        [pscustomobject]@{
            TaskName = $task.TaskName
            State = $task.State
            LastRunTime = $info.LastRunTime
            LastTaskResult = ('0x{0:X8}' -f $info.LastTaskResult)
            NextRunTime = $info.NextRunTime
        } | Format-List | Out-Host
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8091/readyz' -TimeoutSec 5
            Write-Host "Tunnel readiness: HTTP $($response.StatusCode)"
        } catch { Write-Host 'Tunnel readiness is not confirmed. Check .tunnel-client\logs\tunnel.log.' }
    }
    'Stop' {
        Disable-ScheduledTask -TaskName $taskName | Out-Null
        Stop-ScheduledTask -TaskName $taskName
    }
    'Remove' {
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host 'Task removed. Encrypted credentials and logs remain in .tunnel-client.'
    }
}
