from fastapi import APIRouter, HTTPException, Request, status

from app._database.dependencies import DBSession
from app.Auth.dependencies import CurrentUser
from app.Auth.schemas.credentials import LoginRequest, RegisterRequest, SetPasswordRequest
from app.Auth.schemas.token import GoogleAuthRequest, TokenResponse
from app.Auth.services.google_auth_service import GoogleUnavailable, verify_google_token
from app.Auth.services.login_throttle import account_key, per_account, per_client
from app.Auth.services.session_service import create_access_token
from app.shared import audit
from app.shared.errors import error_auth, responses
from app.Users.services import user_service

router = APIRouter()


def client_of(request: Request) -> str:
    """Who is calling, for throttling and for the audit log.

    `request.client.host` is the peer address. Behind a reverse proxy every
    caller looks like the proxy, which would make the per-client limiter
    effectively global -- so if this is ever deployed behind one, that proxy has
    to be trusted and its forwarded-for header read here instead. Deliberately
    *not* reading the header today: an unvalidated `X-Forwarded-For` is
    attacker-controlled, and trusting it would hand anyone an unlimited supply of
    fresh throttle keys.
    """
    return request.client.host if request.client else "unknown"


@router.post("/google", response_model=TokenResponse)
def login_with_google(payload: GoogleAuthRequest, request: Request, db: DBSession):
    client = client_of(request)
    try:
        user_data = verify_google_token(payload.id_token)
    except GoogleUnavailable as exc:
        # Not a rejected sign-in: we could not tell either way. Logged as an
        # error rather than an auth outcome, so a Google outage does not read in
        # the audit log as a burst of people failing to sign in.
        audit.auth_event("google", outcome="error", client=client, detail=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except ValueError as exc:
        audit.auth_event("google", outcome="rejected", client=client, detail=str(exc))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    user = user_service.get_or_create_user_by_google_id(db, user_data)
    audit.auth_event("google", outcome="success", user_id=user.id, email=user.email, client=client)
    access_token = create_access_token(user.id, user.session_epoch)
    return TokenResponse(access_token=access_token)


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    responses=responses["auth_409"],
)
def register_with_email(payload: RegisterRequest, request: Request, db: DBSession):
    """Create a local email + password account and sign the user straight in."""
    client = client_of(request)
    try:
        user = user_service.create_local_user(db, payload)
    except ValueError as exc:
        audit.auth_event(
            "register", outcome="rejected", email=payload.email, client=client, detail=str(exc)
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    audit.auth_event("register", outcome="success", user_id=user.id, email=user.email, client=client)
    return TokenResponse(access_token=create_access_token(user.id, user.session_epoch))


@router.post(
    "/login",
    response_model=TokenResponse,
    responses=responses["auth_401"],
)
def login_with_email(payload: LoginRequest, request: Request, db: DBSession):
    client = client_of(request)
    key = account_key(payload.email, client)

    # Checked before the password is verified, so a blocked caller costs no bcrypt
    # work at all -- which is the point: bcrypt is the expensive part.
    retry_after = per_account.retry_after(key) or per_client.retry_after(client)
    if retry_after is not None:
        audit.auth_event("login", outcome="throttled", email=payload.email, client=client)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many sign-in attempts. Try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )

    user = user_service.authenticate_local_user(db, payload.email, payload.password)
    if user is None:
        per_account.record_failure(key)
        per_client.record_failure(client)
        audit.auth_event("login", outcome="invalid_credentials", email=payload.email, client=client)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_auth["invalid_credentials"],
        )

    # A success clears the account's history, so one forgotten password followed
    # by the right one does not leave the account half-locked.
    per_account.reset(key)
    audit.auth_event("login", outcome="success", user_id=user.id, email=user.email, client=client)
    return TokenResponse(access_token=create_access_token(user.id, user.session_epoch))


@router.post("/password", response_model=TokenResponse, responses=responses["auth_password"])
def set_account_password(
    payload: SetPasswordRequest,
    current_user: CurrentUser,
    request: Request,
    db: DBSession,
):
    """Add a first password, or change an existing one, for the signed-in user.

    This is how a Google-only account gains password sign-in: prove who you
    are with Google first, then set a password. Doing it from an
    unauthenticated endpoint would let anyone who knows an address claim the
    account.

    Succeeding here invalidates every session outstanding at that moment, and
    returns a replacement token for *this* one. So a stolen token elsewhere dies
    immediately, while the person who just proved they know the old password is
    not thrown out of the page they are standing on.

    That is why this returns a body where it used to return 204: the caller has to
    store the new token, or its very next request is a 401.
    """
    client = client_of(request)
    try:
        user_service.set_password(db, current_user, payload.new_password, payload.current_password)
    except ValueError as exc:
        audit.auth_event(
            "set_password",
            outcome="rejected",
            user_id=current_user.id,
            client=client,
            detail=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    audit.auth_event(
        "set_password", outcome="success", user_id=current_user.id, client=client,
        detail="other sessions revoked",
    )
    # Minted from the bumped epoch, so it is the only token that now verifies.
    return TokenResponse(access_token=create_access_token(current_user.id, current_user.session_epoch))
