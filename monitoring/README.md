# Independent daily AI Agent and MCP monitoring

`CompanyBot-HealthMonitor` is a Windows Task Scheduler job, separate from AI Agent,
MCP, Docker and VS Code. It checks daily at **09:00 Windows local time** (currently
Berlin / W. Europe Standard Time). It sends mail from and to
`karim.khavazov@sedatech.net` using `smtp.strato.de:465` with certificate-verified
TLS. A failed check produces an email each daily run until resolved; one recovery
email follows a successfully notified incident. Healthy runs are silent.

Checks cover:

- AI Agent's Streamlit health endpoint on port 8503.
- Tunnel readiness on port 8091.
- MCP initialization and an authenticated `inventory_get_current_time` call on
  port 8001, including validation of the tool result.

This is an availability monitor. It does not exercise LLM generation, SQL, GA4,
Qdrant, or the entire ChatGPT-to-tunnel path. A failure report names the affected
check; it does not include service response bodies or customer data.

## Setup

In Windows PowerShell, from the repository root:

```powershell
.\monitoring\Setup-Monitor.ps1
```

Enter the mailbox password in the hidden prompt. The installer stores it using
Windows DPAPI in ignored `.company-monitor/smtp-password.dpapi`, accessible to the
installing Windows user and SYSTEM. This ties decryption to that user on this PC;
it does not protect against programs already running as that user. The password
is passed to the SMTP helper through an anonymous input pipe, never command-line
arguments, environment variables, email content or logs.

Installation starts the STOP listener, submits a setup test email, then registers
the daily check. Failed setup removes the tasks it created. SMTP acceptance is
not a guarantee of inbox delivery; check the setup test email.

Both tasks run under the signed-in user, hidden, at limited privilege. Closing
VS Code or locking Windows is fine. Signing out, sleeping, losing Internet or
powering off prevents monitoring; `StartWhenAvailable` allows a missed daily run
after the machine is available again. An off-PC monitor is needed to detect this
PC being unavailable. SMTP outages are logged locally because the same SMTP
connection cannot deliver an alert about itself.

## One-click STOP

Every email includes a **STOP alert emails** link. Open it **on this PC**. It calls
a tiny loopback-only control service on `127.0.0.1:18761`, which immediately writes
the pause flag. No login, reply or confirmation is required. A response confirms
that alerts are stopped. An email already submitted to SMTP cannot be recalled.

`CompanyBot-MonitorControl` keeps this independent control running while signed
in. It starts at sign-in, restarts after failure and has a one-minute fallback
trigger. It does not use AI Agent or MCP. Links contain a random capability token;
the listener accepts only the matching token and loopback Host header, and never
logs URLs. As requested, opening the link itself pauses alerts, so a link scanner
running on this PC could also pause them. Mobile devices and other computers
cannot use this local button. Some email clients block localhost links; open the
link in a browser on this PC or use the Stop command below.

```powershell
.\Manage-CompanyMonitor.ps1 -Action Status
.\Manage-CompanyMonitor.ps1 -Action Check     # Live probes; no email or state changes
.\Manage-CompanyMonitor.ps1 -Action Stop      # Pause immediately
.\Manage-CompanyMonitor.ps1 -Action Start     # Resume at the next daily check
.\Manage-CompanyMonitor.ps1 -Action TestEmail # Explicit test, unless paused
.\Manage-CompanyMonitor.ps1 -Action Remove    # Unregister both tasks; retain local data
```

Logs and last-check state are in `.company-monitor/monitor.log` and `state.json`.
Logs rotate at 1 MB with one backup. Re-running `Configure` updates the password
without invalidating existing STOP links. To reinstall after removal, deliberately
remove `.company-monitor/paused` first if you want to enable emails again.

## Tests

```powershell
Invoke-Pester -Script .\monitoring\HealthChecks.Tests.ps1,.\monitoring\MonitorRuntime.Tests.ps1 -EnableExit
.\.uv-python\cpython-3.12.14-windows-x86_64-none\python.exe -m unittest discover -s monitoring -p 'test_*.py'
```

Tests cover successful and failed service responses, notification and recovery
state, SMTP failure, pause behavior, real local STOP requests, invalid tokens and
Host headers, and SMTP/TLS message construction. They do not send real emails.
