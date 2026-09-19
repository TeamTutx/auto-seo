"""Email + password sign-in.

This is the fallback path, not the advertised one: the login page offers
"Continue with Google" (app/routers/auth_google.py) and nothing else. These
endpoints stay so that a misconfigured OAuth client can't lock everyone,
including the owner, out of production.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, func, select

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
        credits_balance=user.credits_balance,
        created_at=user.created_at,
        is_admin=is_admin_user(user),
    )


def create_user(session: Session, email: str, hashed_password: str) -> User:
    """New account plus the ledger row for its free credits, in one transaction,
    so the ledger always sums to the balance. Shared with Google sign-up."""
    user = User(email=email, hashed_password=hashed_password)
    session.add(user)
    session.flush()
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
    return user


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, session: Session = Depends(get_session)):
    email = payload.email.strip().lower()
    if session.exec(select(User).where(func.lower(User.email) == email)).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    return to_user_read(create_user(session, email, hash_password(payload.password)))


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    user = session.exec(select(User).where(func.lower(User.email) == form_data.username.strip().lower())).first()
    # An account created through Google has no password hash, so verify_password
    # returns False for every attempt rather than erroring on an empty hash.
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
