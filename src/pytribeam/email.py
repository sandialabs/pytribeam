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


class SSHTunnelEmailSender:
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
    recipients: list,
    smtp_server: str,
    smtp_port: int,
    subject: str,
    body: str,
    cc: list = None,
    bcc: list = None,
    attachments: list = None,
):
    sender = SSHTunnelEmailSender(
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


if __name__ == "__main__":
    send_update_email(
        ssh_host="192.168.0.3",
        ssh_user="User",
        ssh_key_path="C:/Users/User/.ssh/id_ed25519",
        sender_email="tribeamexperiments@gmail.com",
        sender_password="xoqs adfo maet dari",
        recipients=["jlamb@ucsb.edu", "mechlin@ucsb.edu"],
        subject="Test Email with Attachments",
        body="This is a test email with multiple recipients and attachments.",
        # cc=["cc1@example.com", "cc2@example.com"],
        # bcc="bcc@example.com",
        # attachments=["D:/James/pre_mill/CoNi67_ETD.tif"],
    )
