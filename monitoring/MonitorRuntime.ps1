. "$PSScriptRoot/HealthChecks.ps1"

function Write-MonitorLog {
    param([string]$StateDir, [string]$Message)
    $path = Join-Path $StateDir 'monitor.log'
    if ((Test-Path -LiteralPath $path) -and (Get-Item -LiteralPath $path).Length -gt 1MB) {
        Move-Item -LiteralPath $path -Destination "$path.1" -Force
    }
    Add-Content -LiteralPath $path -Value "$(Get-Date -Format o) $Message" -Encoding UTF8
}

function Send-MonitorMail {
    param($Config, [string]$StateDir, [string]$Subject, [string]$Body)
    # Check again immediately before submission, including after slow health probes.
    if (Test-Path -LiteralPath (Join-Path $StateDir 'paused')) { return $false }
    $process = New-Object Diagnostics.Process
    $secure = $null
    try {
        $secure = (Get-Content -LiteralPath (Join-Path $StateDir 'smtp-password.dpapi') -Raw).Trim() | ConvertTo-SecureString
        $credential = New-Object Net.NetworkCredential($Config.SmtpUsername, $secure)
        $payload = @{
            Host = $Config.SmtpHost; Port = $Config.SmtpPort; Username = $Config.SmtpUsername
            Password = $credential.Password; Address = $Config.Address; Subject = $Subject; Body = $Body
            StopUrl = "http://127.0.0.1:$($Config.ControlPort)/stop/$($Config.StopToken)"
        } | ConvertTo-Json -Compress
        $process.StartInfo = New-Object Diagnostics.ProcessStartInfo
        $process.StartInfo.FileName = $Config.PythonPath
        $process.StartInfo.Arguments = '-X utf8 "' + (Join-Path $PSScriptRoot 'send_alert.py') + '"'
        $process.StartInfo.UseShellExecute = $false
        $process.StartInfo.CreateNoWindow = $true
        $process.StartInfo.RedirectStandardInput = $true
        $process.StartInfo.RedirectStandardError = $true
        $process.StartInfo.RedirectStandardOutput = $true
        if (!$process.Start()) { throw 'Could not start SMTP sender.' }
        # Windows PowerShell 5.1 lacks ProcessStartInfo.StandardInputEncoding.
        $inputBytes = [Text.Encoding]::UTF8.GetBytes($payload)
        $process.StandardInput.BaseStream.Write($inputBytes, 0, $inputBytes.Length)
        $process.StandardInput.BaseStream.Flush()
        $process.StandardInput.Close()
        if (!$process.WaitForExit(90000)) {
            $process.Kill()
            throw 'SMTP submission timed out.'
        }
        if ($process.ExitCode -ne 0) {
            $reason = $process.StandardError.ReadToEnd().Trim()
            if ($reason -match '^SMTP delivery failed \([A-Za-z]+(, status [0-9]+)?\)\.$') { throw $reason }
            throw 'SMTP delivery failed. Check the server, credentials and network.'
        }
        return $true
    } finally {
        $payload = $null
        if ($inputBytes) { [Array]::Clear($inputBytes, 0, $inputBytes.Length) }
        $credential = $null
        if ($secure) { $secure.Dispose() }
        $process.Dispose()
    }
}

function Invoke-MonitorRun {
    param($Config, [string]$StateDir, [string]$RepositoryRoot)
    if (Test-Path -LiteralPath (Join-Path $StateDir 'paused')) {
        Write-MonitorLog $StateDir 'Alerts paused; skipped daily run.'
        return
    }
    $statePath = Join-Path $StateDir 'state.json'
    $state = @{ IncidentNotified = $false; LastChecked = $null; FailedChecks = @() }
    if (Test-Path -LiteralPath $statePath) {
        $previous = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        $state.IncidentNotified = [bool]$previous.IncidentNotified
    }
    $checks = @(Get-CompanyHealth -RepositoryRoot $RepositoryRoot)
    $failed = @($checks | Where-Object { !$_.Healthy })
    $state.LastChecked = (Get-Date).ToString('o')
    $state.FailedChecks = @($failed.Name)
    $summary = ($checks | ForEach-Object { '{0}: {1} - {2}' -f $_.Name, $(if ($_.Healthy) { 'OK' } else { 'FAILED' }), $_.Detail }) -join "`r`n"
    Write-MonitorLog $StateDir ($summary -replace "`r?`n", '; ')
    $subject = $null
    if ($failed.Count -gt 0) { $subject = '[CompanyBot] AI Agent / MCP availability problem' }
    elseif ($state.IncidentNotified) { $subject = '[CompanyBot] AI Agent / MCP recovered' }
    try {
        if ($subject) {
            $body = "PC: $env:COMPUTERNAME`r`nChecked: $($state.LastChecked)`r`n`r`n$summary`r`n`r`nChecks run once daily. They verify service availability, not every model or database feature."
            if (Send-MonitorMail -Config $Config -StateDir $StateDir -Subject $subject -Body $body) {
                $state.IncidentNotified = ($failed.Count -gt 0)
                Write-MonitorLog $StateDir 'Alert accepted by SMTP server.'
            }
        }
    } finally {
        # Preserve notification state on SMTP failure so recovery can be retried.
        $tempPath = "$statePath.tmp"
        $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $tempPath -Encoding UTF8
        Move-Item -LiteralPath $tempPath -Destination $statePath -Force
    }
}
