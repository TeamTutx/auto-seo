from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from app.database import get_session
from app.deps import get_current_user, is_admin_user
from app.models import CreditReason, CreditTransaction, User
from app.schemas import Token, UserCreate, UserRead
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def to_user_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        email=user.email,
        plan=user.plan,
        credits_balance=user.credits_balance,
        created_at=user.created_at,
        is_admin=is_admin_user(user),
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, session: Session = Depends(get_session)):
    existing = session.exec(select(User).where(User.email == payload.email)).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = User(email=payload.email, hashed_password=hash_password(payload.password))
    session.add(user)
    session.flush()
    # The starting balance goes in the ledger too, so it always sums to the balance.
    session.add(
        CreditTransaction(
            user_id=user.id,
            delta=user.credits_balance,
            balance_after=user.credits_balance,
            reason=CreditReason.signup.value,
            note="Free signup credits",
        )
    )
    session.commit()
    session.refresh(user)
    return to_user_read(user)


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == form_data.username)).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(subject=user.email))


@router.get("/me", response_model=UserRead)
def read_me(current_user: User = Depends(get_current_user)):
    return to_user_read(current_user)
