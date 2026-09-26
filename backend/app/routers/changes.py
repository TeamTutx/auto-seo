"""Connect a site to where its content lives, and apply changes there.

The safety rules are in this file rather than in the targets, because they must
hold no matter which target is connected:

1. **A verified site only.** Attaching a write target to a domain the account has
   not proven it owns is the one mistake here that cannot be walked back.
2. **A credential is tested before it is stored.** Saving one that does not work
   just moves the failure to the moment the user is trying to fix their site.
3. **A stale change is refused.** If the live page no longer holds the value the
   change was built against, someone edited it in between, and applying would
   overwrite their work with a suggestion written for the old page.
4. **Nothing is charged for a write.** The credit paid for the model call that
   compiled the change; applying and reverting are free, because a button people
   hesitate over is a button that does not get pressed - and charging for undo is
   indefensible.
"""
import json
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.database import get_session
from app.deps import get_current_user
from app.models import (
    AppliedFix,
    Audit,
    ChangeStatus,
    Check,
    CheckStatus,
    OpportunityType,
    Page,
    ProposedChange,
    Site,
    SiteWriteTarget,
    User,
    WriteTargetKind,
)
from app.routers.pages import get_owned_page
from app.routers.sites import _get_owned_site
from app.schemas import (
    ApplyChangesResult,
    ChangeIdsRequest,
    CompileChangeRequest,
    ProposedChangeRead,
    WriteTargetConnect,
    WriteTargetRead,
)
from app.services import applied_fixes, changes as change_service, token_crypto, write_targets
from app.services.credits import deduct_credit, require_credits
from app.services.fetcher import fetch_html
from app.services.write_targets import FieldWrite, WriteTargetError

logger = logging.getLogger("signal.changes")

router = APIRouter(tags=["changes"])


# --- reading and writing the connection ---


def _label(kind: str, config: dict) -> str:
    if kind == WriteTargetKind.wordpress.value:
        return (config.get("base_url") or "").replace("https://", "").replace("http://", "")
    return config.get("repo") or ""


def _read_target(row: SiteWriteTarget) -> WriteTargetRead:
    config = json.loads(row.config or "{}")
    return WriteTargetRead(
        kind=row.kind,
        label=_label(row.kind, config),
        status=row.status,
        status_detail=row.status_detail,
        capabilities=config.get("capabilities") or [],
        writes_immediately=row.kind != WriteTargetKind.github.value,
        last_checked_at=row.last_checked_at,
        created_at=row.created_at,
    )


@router.get("/sites/{site_id}/write-target", response_model=Optional[WriteTargetRead])
def get_write_target(
    site_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    """Null means the site is manual - changes are shown to copy. That is the
    default for every site, not an error state."""
    site = _get_owned_site(session, site_id, current_user)
    row = write_targets.row_for_site(session, site.id)
    return _read_target(row) if row else None


@router.put("/sites/{site_id}/write-target", response_model=WriteTargetRead)
def connect_write_target(
    site_id: int,
    payload: WriteTargetConnect,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    site = _get_owned_site(session, site_id, current_user)
    if not site.verified:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Verify you own this site before connecting somewhere Signal can write to it. "
                "Site settings has the verification options."
            ),
        )

    if payload.kind.value == WriteTargetKind.wordpress.value:
        target = write_targets.WordPressTarget(
            base_url=payload.base_url, username=payload.username, app_password=payload.secret
        )
        config = {"base_url": payload.base_url, "username": payload.username}
    else:
        target = write_targets.GitHubTarget(repo=payload.repo, token=payload.secret, branch=payload.branch or "")
        config = {"repo": payload.repo, "branch": payload.branch or ""}

    # Tested before it is stored: a credential that does not work is not a
    # connection, and finding out later means finding out mid-fix.
    result = target.test()
    if not result.ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.detail)
    config["capabilities"] = result.capabilities or list(target.supports)

    row = write_targets.row_for_site(session, site.id)
    if row is None:
        row = SiteWriteTarget(site_id=site.id, kind=payload.kind.value, secret_encrypted="")
    row.kind = payload.kind.value
    row.config = json.dumps(config)
    row.secret_encrypted = token_crypto.encrypt_token(payload.secret)
    row.status = "ok"
    row.status_detail = result.detail
    row.last_checked_at = datetime.utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return _read_target(row)


@router.post("/sites/{site_id}/write-target/test", response_model=WriteTargetRead)
def test_write_target(
    site_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    site = _get_owned_site(session, site_id, current_user)
    row = _require_target_row(session, site)

    try:
        result = write_targets.build(row).test()
    except WriteTargetError as exc:
        result = write_targets.TargetStatus(ok=False, detail=str(exc))

    config = json.loads(row.config or "{}")
    if result.capabilities is not None:
        config["capabilities"] = result.capabilities
        row.config = json.dumps(config)
    row.status = "ok" if result.ok else "failed"
    row.status_detail = result.detail
    row.last_checked_at = datetime.utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return _read_target(row)


@router.delete("/sites/{site_id}/write-target", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_write_target(
    site_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    """Applied changes are kept. They are the record of edits made to a real
    site, and deleting them because the connection went away would lose the only
    note of what Signal changed and what it was before."""
    site = _get_owned_site(session, site_id, current_user)
    row = _require_target_row(session, site)
    session.delete(row)
    session.commit()


def _require_target_row(session: Session, site: Site) -> SiteWriteTarget:
    row = write_targets.row_for_site(session, site.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This site has no connection yet.")
    return row


# --- changes ---


def _read_change(change: ProposedChange, *, stale: bool = False) -> ProposedChangeRead:
    receipt = change_service.receipt_of(change) or {}
    return ProposedChangeRead(
        id=change.id,
        page_id=change.page_id,
        field=change.field,
        subject=change.subject,
        before=change.before,
        after=change.after,
        status=change.status,
        target_kind=change.target_kind,
        receipt_url=receipt.get("url"),
        receipt_detail=receipt.get("detail"),
        error=change.error,
        created_at=change.created_at,
        applied_at=change.applied_at,
        reverted_at=change.reverted_at,
        stale=stale,
        warning=change_service.value_warning(change.field, change.after),
    )


@router.get("/pages/{page_id}/changes", response_model=List[ProposedChangeRead])
def list_page_changes(
    page_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    """Does not fetch the page, so `stale` is always false here - checking would
    cost an HTTP request on every dashboard load. Compile and apply check it."""
    page = get_owned_page(session, page_id, current_user)
    rows = session.exec(
        select(ProposedChange)
        .where(ProposedChange.page_id == page.id)
        .order_by(ProposedChange.field, ProposedChange.subject)
    ).all()
    return [_read_change(row) for row in rows]


@router.get("/sites/{site_id}/changes", response_model=List[ProposedChangeRead])
def list_site_changes(
    site_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    site = _get_owned_site(session, site_id, current_user)
    rows = session.exec(
        select(ProposedChange)
        .where(ProposedChange.site_id == site.id)
        .order_by(ProposedChange.created_at.desc())
    ).all()
    return [_read_change(row) for row in rows]


@router.post("/pages/{page_id}/changes/compile", response_model=List[ProposedChangeRead])
def compile_change(
    page_id: int,
    payload: CompileChangeRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Build the exact change for one field. Costs one credit where a model runs,
    nothing where the answer is deterministic."""
    page = get_owned_page(session, page_id, current_user)
    html = _fetch(page.url)

    # Checked before the work, so a user with no credits is told so rather than
    # having a model call made and then refused.
    if payload.field not in change_service.DETERMINISTIC_FIELDS:
        require_credits(current_user)

    try:
        compiled = change_service.compile_field(session, page, payload.field, html)
    except change_service.Unsupported as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except change_service.NothingToChange as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    if compiled.credits:
        # deduct_credit commits, which also persists the changes above - the
        # result and the charge for it land together or not at all.
        deduct_credit(session, current_user, f"apply_compile_{payload.field}")
    else:
        session.commit()

    for change in compiled.changes:
        session.refresh(change)
    return [_read_change(c) for c in compiled.changes]


@router.delete("/pages/{page_id}/changes/{change_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard_change(
    page_id: int,
    change_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    page = get_owned_page(session, page_id, current_user)
    change = session.get(ProposedChange, change_id)
    if change is None or change.page_id != page.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such change for this page.")
    if change.status == ChangeStatus.applied.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This change is live on your site. Revert it instead of discarding it.",
        )
    session.delete(change)
    session.commit()


def _fetch(url: str) -> str:
    try:
        return fetch_html(url)
    except Exception as exc:  # httpx raises several distinct types here
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not read {url}: {exc}"
        )


def _load(session: Session, page: Page, ids: List[int], expected: str) -> List[ProposedChange]:
    rows = session.exec(select(ProposedChange).where(ProposedChange.id.in_(ids))).all()
    found = {row.id for row in rows}
    missing = [i for i in ids if i not in found]
    if missing or any(row.page_id != page.id for row in rows):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such change for this page.")
    wrong = [row for row in rows if row.status != expected]
    if wrong:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{len(wrong)} of those changes are not {expected} any more - reload the page.",
        )
    return rows


@router.post("/pages/{page_id}/changes/apply", response_model=ApplyChangesResult)
def apply_changes(
    page_id: int,
    payload: ChangeIdsRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    page = get_owned_page(session, page_id, current_user)
    site = session.get(Site, page.site_id)
    rows = _load(session, page, payload.ids, ChangeStatus.proposed.value)

    target = _target_for(session, site)
    unsupported = [r for r in rows if not target.can_write(r.field)]
    if unsupported:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"This connection cannot set {', '.join(sorted({r.field.replace('_', ' ') for r in unsupported}))}. "
                "Copy the value in instead - Signal has already written it for you."
            ),
        )

    html = _fetch(page.url)
    stale = [r for r in rows if change_service.is_stale(r, html)]
    if stale:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{page.url} no longer has the value {'these changes were' if len(stale) > 1 else 'this change was'} "
                "written against, so someone has edited it since. Generate it again so you can see the current text "
                "before it is replaced."
            ),
        )

    writes = [FieldWrite(field=r.field, value=r.after, subject=r.subject, before=r.before) for r in rows]
    try:
        receipt = target.write(page.url, writes)
    except WriteTargetError as exc:
        for row in rows:
            row.status = ChangeStatus.failed.value
            row.error = str(exc)
            session.add(row)
        session.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    now = datetime.utcnow()
    for row in rows:
        row.status = ChangeStatus.applied.value
        row.target_kind = target.kind
        row.receipt = json.dumps(receipt.as_dict())
        row.applied_at = now
        row.error = None
        session.add(row)
    session.commit()

    # Hook into the loop that already exists (Phase D): the next audit checks
    # whether the underlying check now passes and raises fix_verified. Done for a
    # pull request too - it stays "verifying" until someone merges it, which is
    # exactly what is true.
    for row in rows:
        _track_for_verification(session, page, row.field)

    for row in rows:
        session.refresh(row)
    return ApplyChangesResult(
        ok=True,
        message=receipt.detail,
        target_kind=target.kind,
        receipt_url=receipt.url,
        changes=[_read_change(r) for r in rows],
    )


@router.post("/pages/{page_id}/changes/revert", response_model=ApplyChangesResult)
def revert_changes(
    page_id: int,
    payload: ChangeIdsRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Free, and never refused for being stale: putting back what was there is
    the right answer whatever happened to the page since."""
    page = get_owned_page(session, page_id, current_user)
    site = session.get(Site, page.site_id)
    rows = _load(session, page, payload.ids, ChangeStatus.applied.value)
    target = _target_for(session, site)

    # `before` is the value to write now. A field that had nothing becomes an
    # empty string, which every target treats as "no value" for the fields it can
    # write - GitHub never applied one of those in the first place, since it can
    # only replace text it found.
    writes = [FieldWrite(field=r.field, value=r.before or "", subject=r.subject, before=r.after) for r in rows]
    try:
        receipt = target.revert(page.url, writes, change_service.receipt_of(rows[0]))
    except WriteTargetError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    now = datetime.utcnow()
    for row in rows:
        row.status = ChangeStatus.reverted.value
        row.reverted_at = now
        row.receipt = json.dumps(receipt.as_dict())
        session.add(row)
        _stop_tracking(session, page, row.field)
    session.commit()

    for row in rows:
        session.refresh(row)
    return ApplyChangesResult(
        ok=True,
        message=receipt.detail,
        target_kind=target.kind,
        receipt_url=receipt.url,
        changes=[_read_change(r) for r in rows],
    )


def _target_for(session: Session, site: Site):
    row = write_targets.row_for_site(session, site.id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This site is not connected to anywhere Signal can write. Connect WordPress or a "
                "GitHub repository in site settings, or copy the change in yourself."
            ),
        )
    try:
        return write_targets.build(row)
    except WriteTargetError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _opportunity_type(session: Session, page: Page, check_type: str) -> OpportunityType:
    latest = session.exec(
        select(Audit).where(Audit.page_id == page.id).order_by(Audit.created_at.desc())
    ).first()
    if latest is not None:
        check = session.exec(
            select(Check).where(Check.audit_id == latest.id, Check.check_type == check_type)
        ).first()
        if check is not None and check.status == CheckStatus.warning:
            return OpportunityType.audit_warning
    return OpportunityType.audit_fail


def _track_for_verification(session: Session, page: Page, check_type: str) -> None:
    already = session.exec(
        select(AppliedFix).where(
            AppliedFix.page_id == page.id,
            AppliedFix.check_type == check_type,
            AppliedFix.resolved.is_(False),
        )
    ).first()
    if already is None:
        applied_fixes.mark_applied(session, page, _opportunity_type(session, page, check_type), check_type, None)


def _stop_tracking(session: Session, page: Page, check_type: str) -> None:
    """A reverted change must not leave a pending fix behind, or the next audit
    would announce it as verified when nothing was applied."""
    for fix in session.exec(
        select(AppliedFix).where(
            AppliedFix.page_id == page.id,
            AppliedFix.check_type == check_type,
            AppliedFix.resolved.is_(False),
        )
    ).all():
        session.delete(fix)
