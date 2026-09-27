from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.database import get_session
from app.deps import get_current_user
from app.models import Alert, Page, User
from app.schemas import AlertRead

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _to_read(alert: Alert, site_id: Optional[int]) -> AlertRead:
    return AlertRead(
        id=alert.id,
        page_id=alert.page_id,
        site_id=site_id,
        alert_type=alert.alert_type,
        subject=alert.subject,
        message=alert.message,
        read=alert.read,
        created_at=alert.created_at,
    )


@router.get("", response_model=List[AlertRead])
def list_alerts(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    # Outer join, not inner: an alert about the account has no page, and an
    # inner join would drop every one of them silently rather than failing.
    rows = session.exec(
        select(Alert, Page.site_id)
        .join(Page, Page.id == Alert.page_id, isouter=True)
        .where(Alert.user_id == current_user.id)
        .order_by(Alert.created_at.desc())
    ).all()
    return [_to_read(alert, site_id) for alert, site_id in rows]


@router.post("/{alert_id}/read", response_model=AlertRead)
def mark_alert_read(
    alert_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    alert = session.get(Alert, alert_id)
    if alert is None or alert.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    page = session.get(Page, alert.page_id) if alert.page_id else None
    alert.read = True
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return _to_read(alert, page.site_id if page else None)
