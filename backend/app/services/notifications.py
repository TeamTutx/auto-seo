"""Tell a user something, in the app and optionally by email.

One function so the two halves cannot drift: whatever the customer reads in the
bell is exactly what was emailed, and there is no path that sends one without
recording the other.

**The alert is the durable record; the email is a copy.** If SMTP is
misconfigured, unreachable or refuses the message, the alert is still written and
`email_status` says what went wrong. Losing a message because a mail server was
down would be the worst possible failure for a feature whose whole job is to tell
someone something.
"""
import logging
from typing import Optional

from sqlmodel import Session

from app.models import Alert, AlertType, User
from app.services import mailer

logger = logging.getLogger("signal.notifications")

MAX_SUBJECT = 150
MAX_BODY = 4000


def notify(
    session: Session,
    user: User,
    subject: str,
    body: str,
    *,
    actor_id: Optional[int] = None,
    send_email: bool = True,
) -> Alert:
    """Write the alert, then try to email it. Does not commit - the caller owns
    the transaction, so a message and whatever prompted it (a credit grant, say)
    land together or not at all."""
    alert = Alert(
        user_id=user.id,
        page_id=None,  # about the account, not a page
        alert_type=AlertType.message,
        subject=subject[:MAX_SUBJECT],
        message=body[:MAX_BODY],
        actor_id=actor_id,
    )

    if not send_email:
        alert.email_status = None
    elif not mailer.enabled():
        alert.email_status = "disabled"
        alert.email_error = mailer.DISABLED_DETAIL
    else:
        ok, detail = mailer.send(user.email, subject, body)
        alert.email_status = "sent" if ok else "failed"
        alert.email_error = None if ok else detail
        if not ok:
            logger.warning("email to %s failed: %s", user.email, detail)

    session.add(alert)
    return alert


def credit_grant_message(delta: int, balance: int, note: Optional[str]) -> tuple:
    """What a customer is told when the owner adjusts their credits.

    The admin's `note` is an internal ledger reason and is deliberately not
    reused as the customer's message - "beta tester gift" reads fine in an audit
    log and oddly in an email. The owner writes the customer's wording, or gets
    this."""
    if delta >= 0:
        subject = f"{delta} credits added to your Signal account"
        body = (
            f"{delta} credit{'s' if delta != 1 else ''} have been added to your Signal account.\n\n"
            f"Your balance is now {balance}."
        )
    else:
        subject = "A change to your Signal credits"
        body = (
            f"{abs(delta)} credit{'s' if abs(delta) != 1 else ''} have been removed from your "
            f"Signal account.\n\nYour balance is now {balance}."
        )
    if note:
        body += f"\n\n{note}"
    return subject, body
