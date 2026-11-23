"""Send one SMTP-over-TLS alert. Credentials arrive only through standard input."""
import json
import smtplib
import ssl
import sys
from email.message import EmailMessage
from html import escape


def send_alert(data):
    message = EmailMessage()
    message["From"] = data["Address"]
    message["To"] = data["Address"]
    message["Subject"] = data["Subject"]
    message.set_content(data["Body"] + "\n\nSTOP alert emails (open on the monitor PC): " + data["StopUrl"])
    message.add_alternative(
        "<html><body><pre>" + escape(data["Body"]) + "</pre><p><a href=\""
        + escape(data["StopUrl"], quote=True)
        + '\" style="display:inline-block;background:#b91c1c;color:white;padding:12px 22px;text-decoration:none">'
        + "STOP alert emails</a></p><p>One click pauses future alerts. Open this link on the Windows PC running the monitor. "
        + "To resume, run Manage-CompanyMonitor.ps1 -Action Start.</p></body></html>",
        subtype="html",
    )
    with smtplib.SMTP_SSL(data["Host"], int(data["Port"]), timeout=30, context=ssl.create_default_context()) as smtp:
        smtp.login(data["Username"], data["Password"])
        smtp.send_message(message)


if __name__ == "__main__":
    try:
        send_alert(json.load(sys.stdin))
    except Exception as exc:
        # Never emit credentials, MIME content, SMTP transcripts or token URLs.
        code = f", status {exc.smtp_code}" if isinstance(exc, smtplib.SMTPResponseException) else ""
        print(f"SMTP delivery failed ({type(exc).__name__}{code}).", file=sys.stderr)
        sys.exit(1)
