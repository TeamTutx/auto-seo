"""Send an email over SMTP.

Deliberately `smtplib` from the standard library rather than a vendor SDK: the
only thing Signal sends is the occasional account message from the owner, and a
dependency plus an API key is a poor trade for that. It also means any SMTP
server works - the owner's existing mailbox, their host, or a transactional
provider later - without changing code.

**Nothing here raises.** `send` returns whether it worked and a sentence saying
why not, because the caller has already written the in-app alert and must not
lose it when a mail server is unreachable. An email that did not send is a
delivery problem to show the admin, not an error that discards the message.

Sent synchronously, on purpose. This runs from admin endpoints acting on one
user, where waiting a second to be told "sent" beats being told "queued" and
having to go and look. `SMTP_TIMEOUT` bounds the wait so a hanging server cannot
hold a worker open.
"""
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from typing import Tuple

from app.config import settings

logger = logging.getLogger("signal.mailer")

DISABLED_DETAIL = "No SMTP server is configured, so no email was sent."


def enabled() -> bool:
    """Whether there is anywhere to send. Host and sender are the minimum; a
    username and password are not, since a local relay often needs neither."""
    return bool(settings.smtp_host and settings.smtp_from)


def _from_header() -> str:
    name, address = parseaddr(settings.smtp_from)
    display = settings.smtp_from_name or name
    return formataddr((display, address)) if display else address


def build(to: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = _from_header()
    message["To"] = to
    message["Subject"] = subject
    # Plain text only. An HTML template is a second thing to keep in step with
    # the in-app copy, and account notices do not need one.
    message.set_content(body)
    if settings.smtp_reply_to:
        message["Reply-To"] = settings.smtp_reply_to
    return message


def send(to: str, subject: str, body: str) -> Tuple[bool, str]:
    """(ok, detail). Never raises - see the module docstring."""
    if not enabled():
        return False, DISABLED_DETAIL

    message = build(to, subject, body)
    try:
        with _connect() as server:
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
    except smtplib.SMTPAuthenticationError:
        # By far the most common failure, and the one with a specific fix:
        # Gmail and friends refuse an account password and want an app password.
        return False, (
            "The mail server rejected the username or password. Most providers require an "
            "app-specific password here rather than the account password."
        )
    except smtplib.SMTPRecipientsRefused:
        return False, f"The mail server refused {to} as a recipient."
    except smtplib.SMTPException as exc:
        return False, f"The mail server refused the message: {exc}"
    except (OSError, ssl.SSLError) as exc:
        return False, f"Could not reach {settings.smtp_host}:{settings.smtp_port} - {exc}"

    logger.info("sent %r to %s", subject, to)
    return True, f"Emailed {to}."


def _connect() -> smtplib.SMTP:
    """Implicit TLS on 465, STARTTLS everywhere else - the split every provider
    follows, so it is inferred from the port rather than asked for twice."""
    if settings.smtp_port == 465:
        return smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout,
            context=ssl.create_default_context(),
        )
    server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout)
    if settings.smtp_starttls:
        server.starttls(context=ssl.create_default_context())
    return server
