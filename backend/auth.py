from secrets import token_urlsafe
from typing import Annotated

from database import DatabaseSettings, get_engine
from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from models import User
from pwdlib import PasswordHash
from pydantic import BaseModel, EmailStr, SecretStr
from pydantic_settings import BaseSettings
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE_NAME = "trinity_session"
SESSION_SECONDS = 8 * 60 * 60
password_hash = PasswordHash.recommended()
dummy_hash = password_hash.hash(token_urlsafe(32))


class AuthSettings(BaseSettings):
    session_secret: SecretStr | None = None
    model_config = DatabaseSettings.model_config


settings = AuthSettings()
secret = (
    settings.session_secret.get_secret_value()
    if settings.session_secret
    else token_urlsafe(32)
)
signer = URLSafeTimedSerializer(secret, salt="trinity-session")


class Credentials(BaseModel):
    email: EmailStr
    password: SecretStr


class Account(BaseModel):
    id: int
    email: str


@router.post("/register", status_code=201)
def register(credentials: Credentials) -> Account:
    email = credentials.email.casefold()
    password = credentials.password.get_secret_value()
    if len(email) > 254 or not 8 <= len(password) <= 128:
        raise HTTPException(
            422, "Use a valid email and a password of 8–128 characters."
        )
    with Session(get_engine()) as session:
        user = User(email=email, password_hash=password_hash.hash(password))
        session.add(user)
        try:
            session.flush()
            account = Account(id=user.id, email=user.email)
            session.commit()
        except IntegrityError as error:
            if getattr(error.orig, "sqlstate", None) != "23505":
                raise
            raise HTTPException(409, "An account already uses this email.") from None
    return account


@router.post("/login")
def login(credentials: Credentials, request: Request, response: Response) -> Account:
    password = credentials.password.get_secret_value()
    if not 1 <= len(password) <= 128:
        raise HTTPException(401, "Incorrect email or password.")
    with Session(get_engine()) as session:
        user = session.scalar(
            select(User).where(User.email == credentials.email.casefold())
        )
        valid = password_hash.verify(
            password, user.password_hash if user else dummy_hash
        )
        if not valid or user is None:
            raise HTTPException(401, "Incorrect email or password.")
        account = Account(id=user.id, email=user.email)
    response.set_cookie(
        COOKIE_NAME,
        signer.dumps(account.id),
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
    )
    return account


@router.get("/me")
def me(
    session_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Account:
    if session_token is None:
        raise HTTPException(401, "Sign in to continue.")
    try:
        user_id = signer.loads(session_token, max_age=SESSION_SECONDS)
    except BadSignature:
        raise HTTPException(401, "Sign in to continue.") from None
    with Session(get_engine()) as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(401, "Sign in to continue.")
        return Account(id=user.id, email=user.email)


@router.post("/logout", status_code=204)
def logout(request: Request) -> Response:
    response = Response(status_code=204)
    response.delete_cookie(
        COOKIE_NAME,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
    )
    return response
