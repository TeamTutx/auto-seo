"""The countries Signal can measure a search in.

A table rather than a constant because the list used to be a hardcoded array in
the frontend bundle, so adding a market meant a code change and a deploy. The
read endpoint is open to any signed-in user - it is a dropdown's contents, not
a secret - while editing is owner-only like the credit packs it mirrors.

A location is retired by clearing `active`, never deleted: historical rank and
visibility rows store the code, and a reading whose country cannot be named is
worse than one from a market no longer offered.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.database import get_session
from app.deps import get_current_user, require_admin
from app.models import SearchLocation, User
from app.schemas import SearchLocationCreate, SearchLocationRead, SearchLocationUpdate

#: The countries the frontend used to hardcode, in the same order. Seeded on
#: startup when the table is empty, exactly as the credit packs are: migration
#: 0017 inserts them for a migrated database, but dev and the test suite build
#: their schema with create_all, which runs no migration - and an empty country
#: list means a keyword form with nothing to pick.
DEFAULT_LOCATIONS = [
    dict(code=2356, label="India", sort_order=10),
    dict(code=2840, label="United States", sort_order=20),
    dict(code=2826, label="United Kingdom", sort_order=30),
    dict(code=2124, label="Canada", sort_order=40),
    dict(code=2036, label="Australia", sort_order=50),
]


def seed_default_locations(session: Session) -> int:
    """Insert the default country list if there are none at all. Returns rows added."""
    if session.exec(select(SearchLocation)).first() is not None:
        return 0
    session.add_all(SearchLocation(**row) for row in DEFAULT_LOCATIONS)
    session.commit()
    return len(DEFAULT_LOCATIONS)


router = APIRouter(tags=["locations"])


def _read(row: SearchLocation) -> SearchLocationRead:
    return SearchLocationRead(
        id=row.id, code=row.code, label=row.label, active=row.active, sort_order=row.sort_order
    )


def _ordered(session: Session, include_retired: bool) -> List[SearchLocation]:
    statement = select(SearchLocation)
    if not include_retired:
        statement = statement.where(SearchLocation.active.is_(True))
    return session.exec(statement.order_by(SearchLocation.sort_order, SearchLocation.label)).all()


@router.get("/locations", response_model=List[SearchLocationRead])
def list_locations(
    current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    """What the keyword form offers. Active only - a retired market should not
    be selectable for a new search, though old readings still name it."""
    return [_read(row) for row in _ordered(session, include_retired=False)]


@router.get("/admin/locations", response_model=List[SearchLocationRead])
def admin_list_locations(admin: User = Depends(require_admin), session: Session = Depends(get_session)):
    return [_read(row) for row in _ordered(session, include_retired=True)]


@router.post("/admin/locations", response_model=SearchLocationRead, status_code=status.HTTP_201_CREATED)
def create_location(
    payload: SearchLocationCreate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    existing = session.exec(select(SearchLocation).where(SearchLocation.code == payload.code)).first()
    if existing is not None:
        # Re-adding a retired market is the common case, and recreating it would
        # orphan every reading already pointing at the old row.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Location {payload.code} already exists as “{existing.label}”"
            + ("." if existing.active else " — it is retired; switch it back on instead."),
        )

    row = SearchLocation(code=payload.code, label=payload.label.strip(), sort_order=payload.sort_order)
    session.add(row)
    session.commit()
    session.refresh(row)
    return _read(row)


@router.put("/admin/locations/{location_id}", response_model=SearchLocationRead)
def update_location(
    location_id: int,
    payload: SearchLocationUpdate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    row = session.get(SearchLocation, location_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such location.")

    # The code is deliberately not editable: readings point at it, so changing it
    # would silently relabel history as having been measured somewhere else.
    if payload.label is not None:
        row.label = payload.label.strip()
    if payload.active is not None:
        row.active = payload.active
    if payload.sort_order is not None:
        row.sort_order = payload.sort_order

    session.add(row)
    session.commit()
    session.refresh(row)
    return _read(row)
