"""Email notification utilities using an SSH-forwarded SMTP connection.

This module provides email-sending support for systems that cannot directly
reach an SMTP server. It creates a local SSH tunnel to a network-accessible host
and forwards SMTP traffic through that tunnel, allowing `pytribeam` workflows to
send status updates, completion notices, or error notifications from restricted
microscope environments.

The main public entry point is `send_update_email`. The `SSHTunnelEmailSender`
class handles the lower-level details of opening the SSH tunnel, constructing
MIME email messages, attaching files, sending through SMTP, and cleaning up the
tunnel process.

## Typical usage

```python
from pytribeam.email import send_update_email

success, message = send_update_email(
    ssh_host="ssh-gateway.example.com",
    ssh_port=1025,
    ssh_user="username",
    ssh_key_path="/path/to/id_rsa",
    sender_email="sender@example.com",
    sender_password="app-password",
    recipients=["recipient@example.com"],
    smtp_server="smtp.example.com",
    smtp_port=587,
    subject="pytribeam update",
    body="The experiment has completed.",
)
```

## Email workflow

`send_update_email` performs the following steps:

1. Create an `SSHTunnelEmailSender`.
2. Establish an SSH tunnel from a local port to the configured SMTP server.
3. Construct a multipart email message.
4. Add optional CC, BCC, and file attachments.
5. Start TLS with the SMTP server.
6. Authenticate with the sender credentials.
7. Send the message to all recipients.
8. Clean up the SSH tunnel process when the sender exits.

## Attachments

Attachments are added using MIME types inferred from the file extension. Image
files are attached as `MIMEImage`; other file types are attached as
`MIMEApplication`.

## Security notes

Credentials and SSH keys are supplied by the caller. Avoid hard-coding email
passwords, app passwords, private-key paths, or recipient lists in committed
source code. Prefer secure configuration files, environment variables, or an
approved secret-management mechanism.

> **Warning**
>
> This module opens an SSH subprocess and sends authenticated email. Confirm that
> the SSH host, SMTP server, credentials, and attachments are appropriate before
> enabling automated notifications.
"""

__all__ = [
    "send_update_email",
]

import subprocess
import time
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.application import MIMEApplication
from email.utils import formatdate
import socket
from typing import Tuple, Optional, List, Union
import atexit
from pathlib import Path
import mimetypes
import os


class _SSHTunnelEmailSender:
    def __init__(
        self,
        ssh_host: str,
        ssh_user: str,
        ssh_key_path: Optional[str] = None,
        local_port: int = 1025,
        smtp_server: str = "smtp.gmail.com",
        smtp_port: int = 587,
    ):
        """Initialize SSH tunnel and email sender."""
        self.ssh_host = ssh_host
        self.ssh_user = ssh_user
        self.ssh_key_path = ssh_key_path or str(Path.home() / ".ssh" / "id_rsa")
        self.local_port = local_port
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.tunnel_process = None
        atexit.register(self.cleanup)

    def establish_tunnel(self) -> Tuple[bool, str]:
        """Establish SSH tunnel with direct TCP forwarding."""
        try:
            ssh_cmd = [
                "ssh",
                "-L",
                f"{self.local_port}:{self.smtp_server}:{self.smtp_port}",
                "-N",
                "-F",
                "none",
                "-o",
                "ExitOnForwardFailure=yes",
                "-o",
                "ServerAliveInterval=60",
                "-o",
                "StrictHostKeyChecking=no",
                "-i",
                self.ssh_key_path,
                f"{self.ssh_user}@{self.ssh_host}",
            ]

            self.tunnel_process = subprocess.Popen(
                ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )

            time.sleep(2)

            if self.tunnel_process.poll() is None:
                try:
                    with socket.create_connection(
                        ("127.0.0.1", self.local_port), timeout=5
                    ):
                        return True, "SSH tunnel established successfully"
                except socket.error as e:
                    self.cleanup()
                    return False, f"Tunnel establishment failed: {str(e)}"
            else:
                _, stderr = self.tunnel_process.communicate()
                return False, f"Failed to establish SSH tunnel: {stderr.decode()}"

        except Exception as e:
            return False, str(e)

    def cleanup(self):
        """Clean up SSH tunnel process on exit."""
        if self.tunnel_process:
            try:
                self.tunnel_process.terminate()
                self.tunnel_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.tunnel_process.kill()
                self.tunnel_process.wait()

    def add_attachment(self, msg: MIMEMultipart, filepath: str) -> None:
        """
        Add an attachment to the email message.

        Args:
            msg: The email message to attach to
            filepath: Path to the file to attach
        """
        with open(filepath, "rb") as f:
            file_data = f.read()

        # Guess the content type
        content_type, _ = mimetypes.guess_type(filepath)
        if content_type is None:
            content_type = "application/octet-stream"

        maintype, subtype = content_type.split("/", 1)

        if maintype == "image":
            # Handle image attachments
            attachment = MIMEImage(file_data, _subtype=subtype)
        else:
            # Handle all other file types
            attachment = MIMEApplication(file_data, _subtype=subtype)

        # Add header with filename
        attachment.add_header(
            "Content-Disposition", "attachment", filename=os.path.basename(filepath)
        )

        msg.attach(attachment)

    def create_message(
        self,
        sender: str,
        recipients: Union[str, List[str]],
        subject: str,
        body: str,
        cc: Optional[Union[str, List[str]]] = None,
        bcc: Optional[Union[str, List[str]]] = None,
        attachments: Optional[List[str]] = None,
    ) -> MIMEMultipart:
        """
        Create an email message with proper headers and structure.

        Args:
            sender: Email address of the sender
            recipients: Single recipient or list of recipients
            subject: Email subject
            body: Email body text
            cc: Optional CC recipient(s)
            bcc: Optional BCC recipient(s)
            attachments: Optional list of file paths to attach
        """
        msg = MIMEMultipart()
        msg["From"] = sender
        msg["Date"] = formatdate(localtime=True)
        msg["Subject"] = subject

        # Handle multiple recipients
        if isinstance(recipients, list):
            msg["To"] = ", ".join(recipients)
        else:
            msg["To"] = recipients

        # Handle CC recipients
        if cc:
            if isinstance(cc, list):
                msg["Cc"] = ", ".join(cc)
            else:
                msg["Cc"] = cc

        # Handle BCC recipients
        if bcc:
            if isinstance(bcc, list):
                msg["Bcc"] = ", ".join(bcc)
            else:
                msg["Bcc"] = bcc

        # Attach body
        msg.attach(MIMEText(body, "plain"))

        # Add any attachments
        if attachments:
            for filepath in attachments:
                self.add_attachment(msg, filepath)

        return msg

    def send_email(
        self,
        sender_email: str,
        sender_password: str,
        recipients: Union[str, List[str]],
        subject: str,
        body: str,
        cc: Optional[Union[str, List[str]]] = None,
        bcc: Optional[Union[str, List[str]]] = None,
        attachments: Optional[List[str]] = None,
    ) -> Tuple[bool, str]:
        """
        Send an email through the SSH tunnel.

        Args:
            sender_email: Email address of the sender
            sender_password: Password or app-specific password for sender's account
            recipients: Single recipient or list of recipients
            subject: Email subject
            body: Email body text
            cc: Optional CC recipient(s)
            bcc: Optional BCC recipient(s)
            attachments: Optional list of file paths to attach

        Returns:
            Tuple of (success: bool, message: str)
        """
        if not self.tunnel_process or self.tunnel_process.poll() is not None:
            success, message = self.establish_tunnel()
            if not success:
                return success, message

        try:
            msg = self.create_message(
                sender_email, recipients, subject, body, cc, bcc, attachments
            )

            # Prepare recipient list
            all_recipients = []

            # Add main recipients
            if isinstance(recipients, list):
                all_recipients.extend(recipients)
            else:
                all_recipients.append(recipients)

            # Add CC recipients
            if cc:
                if isinstance(cc, list):
                    all_recipients.extend(cc)
                else:
                    all_recipients.append(cc)

            # Add BCC recipients
            if bcc:
                if isinstance(bcc, list):
                    all_recipients.extend(bcc)
                else:
                    all_recipients.append(bcc)

            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

            with smtplib.SMTP("127.0.0.1", self.local_port) as server:
                server.starttls(context=context)
                server.login(sender_email, sender_password)
                server.send_message(msg, sender_email, all_recipients)

            return True, "Email sent successfully"

        except smtplib.SMTPAuthenticationError:
            return (
                False,
                "Authentication failed. Check credentials and ensure using App Password if needed.",
            )
        except Exception as e:
            return False, str(e)


def send_update_email(
    ssh_host: str,
    ssh_port: int,
    ssh_user: str,
    ssh_key_path: str,
    sender_email: str,
    sender_password: str,
    recipients: List[str],
    smtp_server: str,
    smtp_port: int,
    subject: str,
    body: str,
    cc: List[str] = None,
    bcc: List[str] = None,
    attachments: List[str] = None,
) -> Tuple[bool, str]:
    """
    Send an update email.
    
    ## Parameters
    
    - `ssh_host` (`str`) : The hostname of the machine with internet access that the email will be sent through.
    - `ssh_port` (`int`) : The port of the machine with internet access.
    - `ssh_user` (`str`) : The username of the machine with internet access.
    - `ssh_key_path` (`str`) : The path to the ssh key that will be used for authentication with the internet machine.
    - `sender_email` (`str`) : The email of the sender.
    - `sender_password` (`str`) : The app password for accessing the sender email account.
    - `recipients` (`List[str]`) : The recipients of the email.
    - `smtp_server` (`str`) : The SMTP server to use for sending the email.
    - `smtp_port` (`int`) : The SMTP port to use for sending the email.
    - `subject` (`str`) : The email subject text.
    - `body` (`str`) : The email body text.
    - `cc` (`List[str]`) : A list of email addresses to CC on the email.
    - `bcc` (`List[str]`) : A list of email addresses to BCC on the email.
    - `attachments` (`List[str]`) : A list of filepath strings of attachments to include in the email.
    """
    sender = _SSHTunnelEmailSender(
        ssh_host=ssh_host,
        ssh_user=ssh_user,
        ssh_key_path=ssh_key_path,
        local_port=ssh_port,
        smtp_server=smtp_server,
        smtp_port=smtp_port,
    )

    success, message = sender.send_email(
        sender_email=sender_email,
        sender_password=sender_password,
        recipients=recipients,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
        attachments=attachments,
    )

    return success, message
