$ErrorActionPreference = 'Stop'
$manager = Join-Path (Split-Path $PSScriptRoot -Parent) 'Manage-CompanyMonitor.ps1'
try {
    Write-Host 'Set up daily AI Agent/MCP monitoring at 09:00 on this PC.'
    Write-Host 'Your mailbox password stays on this PC, encrypted for your Windows account.'
    & $manager -Action Configure
    & $manager -Action Install -DailyAt '09:00'
    & $manager -Action Check
    & $manager -Action Status
    Write-Host 'Setup finished. Check your inbox for the setup test email.'
} catch {
    Write-Host "Setup did not finish: $($_.Exception.Message)" -ForegroundColor Red
}
Read-Host 'Press Enter to close this window' | Out-Null
