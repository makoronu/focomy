"""Mail service for sending emails."""

import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..config import settings


@dataclass
class EmailMessage:
    """Email message data."""

    to: str
    subject: str
    body: str
    html: str | None = None
    reply_to: str | None = None


class MailService:
    """
    Mail sending service.

    Supports SMTP.
    Configure via environment variables:
    - MAIL_HOST
    - MAIL_PORT
    - MAIL_USERNAME
    - MAIL_PASSWORD
    - MAIL_FROM
    - MAIL_FROM_NAME
    """

    def __init__(self):
        self.host = getattr(settings, "mail_host", None)
        self.port = getattr(settings, "mail_port", 587)
        self.username = getattr(settings, "mail_username", None)
        self.password = getattr(settings, "mail_password", None)
        self.from_email = getattr(settings, "mail_from", None)
        self.from_name = getattr(settings, "mail_from_name", "Focomy")
        self.use_tls = getattr(settings, "mail_use_tls", True)

    def is_configured(self) -> bool:
        """Check if mail is configured."""
        return bool(self.host and self.from_email)

    def send(self, message: EmailMessage) -> bool:
        """Send an email."""
        if not self.is_configured():
            print("Mail not configured, skipping send")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = message.subject
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = message.to

            if message.reply_to:
                msg["Reply-To"] = message.reply_to

            # Add body
            msg.attach(MIMEText(message.body, "plain", "utf-8"))

            if message.html:
                msg.attach(MIMEText(message.html, "html", "utf-8"))

            # Send
            with smtplib.SMTP(self.host, self.port) as server:
                if self.use_tls:
                    server.starttls()
                if self.username and self.password:
                    server.login(self.username, self.password)
                server.sendmail(self.from_email, message.to, msg.as_string())

            return True

        except Exception as e:
            print(f"Failed to send email: {e}")
            return False

    def send_form_notification(
        self,
        to: str,
        form_title: str,
        submission_data: dict,
        reply_to: str | None = None,
    ) -> bool:
        """Send form submission notification."""
        # Build plain text body
        lines = [f"フォーム「{form_title}」から新しい送信がありました。", "", "--- 送信内容 ---"]
        for key, value in submission_data.items():
            lines.append(f"{key}: {value}")

        body = "\n".join(lines)

        # Build HTML body
        html_lines = [
            f"<h2>フォーム「{form_title}」から新しい送信がありました</h2>",
            "<table style='border-collapse: collapse; width: 100%;'>",
        ]
        for key, value in submission_data.items():
            html_lines.append(
                f"<tr><td style='border: 1px solid #ddd; padding: 8px; background: #f9f9f9;'><strong>{key}</strong></td>"
                f"<td style='border: 1px solid #ddd; padding: 8px;'>{value}</td></tr>"
            )
        html_lines.append("</table>")

        html = "\n".join(html_lines)

        return self.send(
            EmailMessage(
                to=to,
                subject=f"[Focomy] {form_title} - 新しい送信",
                body=body,
                html=html,
                reply_to=reply_to,
            )
        )


# Singleton
mail_service = MailService()
