
"""
Authentication router handling user registration, logins, JWT refresh rotation, and logout sessions.
"""

import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import (
    enforce_api_key_workspace_scope,
    get_api_key,
    get_current_user,
    get_db,
    resolve_active_api_key,
    user_for_access_token,
)
from app.models import APIKey, Membership, User, WorkspaceInvite
from app.schemas import (
    GeneratedUsernameResponse,
    Token,
    UserCreate,
    UsernameAvailabilityResponse,
    UsernameUpdate,
    UserResponse,
)
from app.security import (
    claims_match_user,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    session_claims,
    verify_password,
)
from app.username import (
    find_user_by_username,
    generate_unique_username,
    is_valid_username_format,
    normalize_username,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    email = user_in.email.strip().lower()
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered."
        )

    if user_in.username:
        username = normalize_username(user_in.username)
        if find_user_by_username(db, username):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This username is already taken.",
            )
    else:
        username = generate_unique_username(db, seed=email.split("@")[0])

    hashed_pwd = get_password_hash(user_in.password)
    new_user = User(email=email, username=username, password_hash=hashed_pwd)

    db.add(new_user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That email or username was just taken. Please try again.",
        ) from None
    db.refresh(new_user)

    pending_invites = db.query(WorkspaceInvite).filter(WorkspaceInvite.email == new_user.email).all()
    for invite in pending_invites:
        db.add(
            Membership(
                user_id=new_user.id,
                workspace_id=invite.workspace_id,
                role=invite.role,
                status="pending_acceptance",
            )
        )
        db.delete(invite)
    if pending_invites:
        db.commit()

    return new_user


@router.get("/username-availability", response_model=UsernameAvailabilityResponse)
def check_username_availability(username: str, db: Session = Depends(get_db)):
    """Checks whether a username is valid and not already taken (used while typing)."""
    normalized = normalize_username(username)
    if not is_valid_username_format(normalized):
        return {"available": False}

    return {"available": find_user_by_username(db, normalized) is None}


@router.get("/generate-username", response_model=GeneratedUsernameResponse)
def generate_username_suggestion(seed: str | None = None, db: Session = Depends(get_db)):
    """Returns a fresh, available, randomly generated username suggestion."""
    return {"username": generate_unique_username(db, seed=seed)}


@router.patch("/me/username", response_model=UserResponse)
def update_username(
    payload: UsernameUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Updates the current user's username."""
    username = normalize_username(payload.username)

    if username == current_user.username:
        return current_user

    existing = find_user_by_username(db, username)
    if existing and existing.id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This username is already taken.",
        )

    current_user.username = username
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That username was just taken. Please choose another.",
        ) from None
    db.refresh(current_user)
    return current_user


def _set_session_cookie(response: Response, access_token: str) -> None:
    """Sets a broad-path cookie carrying the access token so the nginx reverse
    proxy can gate console and visdom routes (including the visdom websocket,
    which cannot send Authorization headers) via an auth_request subrequest."""
    response.set_cookie(
        key="session_token",
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )


@router.post("/login", response_model=Token)
def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Validates user credentials (mapping username to email in form data).
    Returns an access token in the JSON body and sets the refresh token in an HTTP-only cookie.
    """
    user = db.query(User).filter(User.email == form_data.username.strip().lower()).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user."
        )

    # generate token payloads
    claims = session_claims(user)
    access_token = create_access_token(data=claims)
    refresh_token = create_refresh_token(data=claims)

    # set refresh token cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,  # HTTPS transfer in production
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/api/v1/auth",  # scope cookie to auth endpoints
    )
    _set_session_cookie(response, access_token)

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/refresh", response_model=Token)
def refresh_session(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Validates the refresh token cookie, rotates it,
    and returns a new Access Token.
    """
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid refresh cookie."
        )

    try:
        payload = decode_token(refresh_token)
        user_id_str: str = payload.get("sub")
        token_type: str = payload.get("type")

        if user_id_str is None or token_type != "refresh":
            raise jwt.PyJWTError()
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token."
        ) from None

    try:
        user_id = uuid.UUID(user_id_str)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token."
        ) from None

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with this token is inactive or does not exist."
        )

    if not claims_match_user(payload, user):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This session has been logged out.",
        )

    # Rotate both access and refresh tokens
    claims = session_claims(user)
    new_access_token = create_access_token(data=claims)
    new_refresh_token = create_refresh_token(data=claims)

    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/api/v1/auth",
    )
    _set_session_cookie(response, new_access_token)

    return {"access_token": new_access_token, "token_type": "bearer"}


def _users_logging_out(db: Session, request: Request) -> list[User]:
    """Everyone the request can still prove it is, from either cookie.

    Usually both cookies name the same account. A client can also hold only
    the session token, or two cookies that name different accounts, and each
    of those is a token that must stop working.
    """
    found = {}
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        try:
            user_id = uuid.UUID(decode_token(refresh_token).get("sub"))
        except (jwt.PyJWTError, TypeError, ValueError):
            user_id = None
        if user_id is not None:
            user = db.query(User).filter(User.id == user_id).first()
            if user is not None:
                found[user.id] = user

    user = user_for_access_token(db, request.cookies.get("session_token"))
    if user is not None:
        found[user.id] = user
    return list(found.values())


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(key="refresh_token", path="/api/v1/auth")
    response.delete_cookie(key="session_token", path="/")


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """Clears the session cookies and revokes the tokens already issued.

    Bumping `token_version` is what actually ends the session, since every path
    that resolves a token checks it. Clearing the cookies only ends it for a
    client that cooperates, which a stolen token does not. So if the bump cannot
    be saved, the answer is an error and not a logout that did not happen. The
    cookies are cleared either way, so this browser is not left signed in.
    """
    users = _users_logging_out(db, request)
    for user in users:
        user.token_version = (user.token_version or 0) + 1
    if users:
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            response = JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"detail": "Could not log out. Please try again."},
            )
            _clear_session_cookies(response)
            return response

    _clear_session_cookies(response)
    return {"detail": "Successfully logged out"}


@router.get("/verify")
def verify_session(request: Request, db: Session = Depends(get_db)):
    """auth_request target for the nginx reverse proxy. Returns 200 when the
    caller presents either a valid `session_token` cookie (browser read path) or
    a valid `X-API-KEY` (programmatic write path), and 401 otherwise. This is a
    coarse "is this a legitimate caller?" gate; the precise workspace + role check
    is done separately by the visdom resolve endpoints.

    Both paths resolve against the database so that logging out, or revoking a
    key, actually closes the gate. Note that nginx caches this response per
    credential, so a revoked session keeps passing until that entry expires."""
    user = user_for_access_token(db, request.cookies.get("session_token"))
    if user is not None and user.is_active:
        return {"status": "ok", "auth": "session"}

    if resolve_active_api_key(db, request.headers.get("X-API-KEY")) is not None:
        return {"status": "ok", "auth": "api_key"}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No valid session or API key.",
    )


@router.get("/me", response_model=UserResponse)
def get_user_profile(current_user: User = Depends(get_current_user)):
    """Returns the current authenticated user's profile info."""
    return current_user

@router.get("/key-check")
def check_api_key(
    workspace_id: uuid.UUID | None = None,
    key_record: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """
    Verifies an API key and returns the owner details. If a workspace_id is
    supplied, additionally enforces the key's workspace-scope binding for that
    workspace: a workspace-scoped key is rejected (403) for any workspace it is
    not bound to, and any key is rejected if its owner has lost access there.
    """
    response = {
        "status": "authenticated",
        "email": key_record.owner.email,
        "key_name": key_record.name,
        "scope": key_record.scope,
    }

    if workspace_id is not None:
        enforce_api_key_workspace_scope(db, key_record, workspace_id)
        response["workspace_id"] = str(workspace_id)
        response["workspace_access"] = "granted"

    return response
