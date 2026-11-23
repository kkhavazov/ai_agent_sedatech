param(
    [ValidateSet('Configure', 'Install', 'Run', 'Check', 'TestEmail', 'Start', 'Stop', 'Status', 'Remove')]
    [string]$Action = 'Status',
    [ValidatePattern('^([01][0-9]|2[0-3]):[0-5][0-9]$')]
    [string]$DailyAt = '09:00'
)

$ErrorActionPreference = 'Stop'
$taskName = 'CompanyBot-HealthMonitor'
$controlTaskName = 'CompanyBot-MonitorControl'
$stateDir = Join-Path $PSScriptRoot '.company-monitor'
$configPath = Join-Path $stateDir 'config.json'
$pausePath = Join-Path $stateDir 'paused'
. "$PSScriptRoot/monitoring/MonitorRuntime.ps1"

function Read-MonitorConfig {
    if (!(Test-Path -LiteralPath $configPath)) { throw 'Run -Action Configure first to save the SMTP password securely.' }
    return Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
}

function Test-ControlReady {
    param($Config)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$($Config.ControlPort)/health" -TimeoutSec 2 -MaximumRedirection 0
        return $response.StatusCode -eq 200 -and $response.Content.Trim() -eq 'company-monitor-control'
    } catch { return $false }
}

switch ($Action) {
    'Configure' {
        New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $acl = New-Object Security.AccessControl.DirectorySecurity
        $acl.SetAccessRuleProtection($true, $false)
        foreach ($who in @($identity.User, 'SYSTEM')) {
            $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($who, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')))
        }
        Set-Acl -LiteralPath $stateDir -AclObject $acl
        $python = Join-Path $PSScriptRoot '.uv-python/cpython-3.12.14-windows-x86_64-none/python.exe'
        if (!(Test-Path -LiteralPath $python)) { throw 'The standalone Python runtime is missing. Update its path before configuring.' }
        $config = @{
            Address = 'karim.khavazov@sedatech.net'; SmtpUsername = 'karim.khavazov@sedatech.net'
            SmtpHost = 'smtp.strato.de'; SmtpPort = 465; ControlPort = 18761
            PythonPath = $python; StopToken = ([Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N'))
        }
        if (Test-Path -LiteralPath $configPath) {
            # Preserve existing email links when only updating the SMTP password.
            $config.StopToken = (Read-MonitorConfig).StopToken
        }
        $password = Read-Host 'STRATO mailbox password for karim.khavazov@sedatech.net (hidden)' -AsSecureString
        try {
            if ($password.Length -eq 0) { throw 'Password cannot be empty.' }
            ConvertFrom-SecureString $password | Set-Content -LiteralPath (Join-Path $stateDir 'smtp-password.dpapi') -Encoding ASCII
        } finally { $password.Dispose() }
        $config | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8
        Write-Host 'SMTP password saved using Windows DPAPI for this account. Next: -Action Install'
    }
    'Install' {
        $config = Read-MonitorConfig
        if (!(Test-Path -LiteralPath (Join-Path $stateDir 'smtp-password.dpapi'))) { throw 'SMTP password is missing; run -Action Configure.' }
        foreach ($name in @($taskName, $controlTaskName)) {
            if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) { throw "Task $name already exists. Use Status/Start or Remove before reinstalling." }
        }
        if (Test-ControlReady $config) { throw 'A STOP control listener is already running; inspect it before installing.' }
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Limited
        $psExe = Join-Path $PSHOME 'powershell.exe'
        $runAction = New-ScheduledTaskAction -Execute $psExe -WorkingDirectory $PSScriptRoot -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Action Run"
        $dailyTrigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
        $runSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        $pythonw = Join-Path (Split-Path $config.PythonPath -Parent) 'pythonw.exe'
        if (!(Test-Path -LiteralPath $pythonw)) { throw 'The windowless Python runtime is missing.' }
        # Schedule the listener directly so stopping the task stops the listener,
        # without leaving a child process behind after setup rollback or removal.
        $controlAction = New-ScheduledTaskAction -Execute $pythonw -WorkingDirectory $PSScriptRoot -Argument "-X utf8 `"$PSScriptRoot/monitoring/stop_control.py`" --state-dir `"$stateDir`" --port $($config.ControlPort)"
        $controlTriggers = @(
            New-ScheduledTaskTrigger -AtLogOn -User $identity.Name
            New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
        )
        $controlSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        $createdTasks = @()
        try {
            Register-ScheduledTask -TaskName $controlTaskName -Action $controlAction -Trigger $controlTriggers -Principal $principal -Settings $controlSettings -Description 'Loopback-only one-click STOP button for CompanyBot alert emails.' | Out-Null
            $createdTasks += $controlTaskName
            Start-ScheduledTask -TaskName $controlTaskName
            for ($attempt = 0; $attempt -lt 10 -and !(Test-ControlReady $config); $attempt++) { Start-Sleep -Milliseconds 500 }
            if (!(Test-ControlReady $config)) { throw 'STOP control did not become ready.' }
            if (Test-Path -LiteralPath $pausePath) { throw 'Alerts are paused. Use Start after installation or remove the pause marker intentionally before reinstalling.' }
            if (!(Send-MonitorMail -Config $config -StateDir $stateDir -Subject '[CompanyBot] Daily monitor setup test' -Body "This confirms SMTP submission for your daily AI Agent and MCP monitor.`r`nSchedule: $DailyAt ($((Get-TimeZone).Id)).`r`nAlerts go from your address to itself. The STOP button pauses future emails immediately on this PC.")) { throw 'Test email was not submitted.' }
            Register-ScheduledTask -TaskName $taskName -Action $runAction -Trigger $dailyTrigger -Principal $principal -Settings $runSettings -Description "Independent AI Agent/MCP checks daily at $DailyAt; SMTP alerts with a local STOP button." | Out-Null
            $createdTasks += $taskName
            Write-MonitorLog $stateDir "Installed daily at $DailyAt ($((Get-TimeZone).Id)); test email accepted by SMTP."
            Write-Host "Installed. Daily check: $DailyAt ($((Get-TimeZone).Id)). Test email accepted by SMTP."
        } catch {
            foreach ($name in $createdTasks) {
                Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
                Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
            }
            throw
        }
    }
    'Run' {
        $mutex = New-Object Threading.Mutex($false, 'Local\CompanyBotHealthMonitor')
        $locked = $false
        try {
            try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
            if (!$locked) { exit 0 }
            $config = Read-MonitorConfig
            Invoke-MonitorRun -Config $config -StateDir $stateDir -RepositoryRoot $PSScriptRoot
        } catch {
            if (Test-Path -LiteralPath $stateDir) { Write-MonitorLog $stateDir 'Monitor run failed; check SMTP configuration, network and local state. No credentials or response bodies are logged.' }
            exit 1
        } finally {
            if ($locked) { $mutex.ReleaseMutex() }
            $mutex.Dispose()
        }
    }
    'Check' { Get-CompanyHealth -RepositoryRoot $PSScriptRoot | Format-Table -AutoSize }
    'TestEmail' {
        $config = Read-MonitorConfig
        if (!(Test-ControlReady $config)) { throw 'STOP control is unavailable. Start CompanyBot-MonitorControl first.' }
        if (!(Send-MonitorMail -Config $config -StateDir $stateDir -Subject '[CompanyBot] Monitor test' -Body 'Test of the independent daily monitor email and STOP button.')) { throw 'Alerts are paused; test email was not sent.' }
        Write-Host 'Test email accepted by SMTP.'
    }
    'Stop' {
        New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
        [IO.File]::WriteAllText($pausePath, '')
        Write-Host 'Future alert emails are paused. An email already submitted cannot be recalled.'
    }
    'Start' {
        $config = Read-MonitorConfig
        foreach ($name in @($taskName, $controlTaskName)) { Get-ScheduledTask -TaskName $name | Out-Null }
        Enable-ScheduledTask -TaskName $controlTaskName | Out-Null
        if ((Get-ScheduledTask -TaskName $controlTaskName).State -ne 'Running') { Start-ScheduledTask -TaskName $controlTaskName }
        for ($attempt = 0; $attempt -lt 10 -and !(Test-ControlReady $config); $attempt++) { Start-Sleep -Milliseconds 500 }
        if (!(Test-ControlReady $config)) { throw 'STOP control unavailable; alerts remain paused.' }
        Enable-ScheduledTask -TaskName $taskName | Out-Null
        if (Test-Path -LiteralPath $pausePath) { Remove-Item -LiteralPath $pausePath }
        Write-Host 'Alerts resumed for the next daily check.'
    }
    'Status' {
        Write-Host "Alerts paused: $(Test-Path -LiteralPath $pausePath)"
        foreach ($name in @($taskName, $controlTaskName)) {
            $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
            if ($task) {
                $info = Get-ScheduledTaskInfo -TaskName $name
                [pscustomobject]@{ Task = $name; State = $task.State; LastRun = $info.LastRunTime; LastResult = $info.LastTaskResult; NextRun = $info.NextRunTime } | Format-List
            } else { Write-Host "$name is not installed." }
        }
        if (Test-Path -LiteralPath $configPath) { Write-Host "STOP control ready: $(Test-ControlReady (Read-MonitorConfig))" }
    }
    'Remove' {
        New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
        [IO.File]::WriteAllText($pausePath, '')
        foreach ($name in @($taskName, $controlTaskName)) {
            if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
                Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
                Unregister-ScheduledTask -TaskName $name -Confirm:$false
            }
        }
        Write-Host 'Monitor tasks removed. Encrypted credentials, logs and paused state retained.'
    }
}
