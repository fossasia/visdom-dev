# Copyright 2017-present, The Visdom Authors
from app.config import settings


def test_register_user(client):
    """Assert user registration succeeds and enforces validation rules."""
    # Test valid registration
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "securepassword"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "id" in data
    assert data["tier"] == "free"
    assert data["is_active"] is True

    # Test duplicate registration error
    dup_response = client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "securepassword"}
    )
    assert dup_response.status_code == 400
    assert dup_response.json()["detail"] == "Email already registered."

    # Test password too short
    short_response = client.post(
        "/api/v1/auth/register",
        json={"email": "short@example.com", "password": "123"}
    )
    assert short_response.status_code == 422


def test_login_user(client):
    """Assert login exchanges credentials for access token & secure cookies."""
    # Register first
    client.post(
        "/api/v1/auth/register",
        json={"email": "user@example.com", "password": "mypassword"}
    )

    # Login
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "user@example.com", "password": "mypassword"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Assert HTTP-only refresh cookie is set
    assert "refresh_token" in response.cookies
    cookie = next((c for c in response.cookies.jar if c.name == "refresh_token"), None)
    assert cookie is not None
    assert cookie.secure is settings.COOKIE_SECURE


def test_login_user_invalid(client):
    """Assert login returns 401 for incorrect credentials."""
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "fake@example.com", "password": "wrongpassword"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password."


def test_refresh_token(client):
    """Assert cookie-based token refresh rotations generate fresh access tokens."""
    # Register and Login
    client.post(
        "/api/v1/auth/register",
        json={"email": "refresh@example.com", "password": "securepassword"}
    )
    login_response = client.post(
        "/api/v1/auth/login",
        data={"username": "refresh@example.com", "password": "securepassword"}
    )
    assert login_response.status_code == 200

    # Call refresh (TestClient automatically forwards the cookie set in previous response)
    refresh_response = client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 200
    data = refresh_response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_logout_user(client):
    """Assert logout endpoint clears cookies."""
    # Login
    client.post(
        "/api/v1/auth/register",
        json={"email": "logout@example.com", "password": "securepassword"}
    )
    login_response = client.post(
        "/api/v1/auth/login",
        data={"username": "logout@example.com", "password": "securepassword"}
    )
    assert "refresh_token" in login_response.cookies

    # Logout
    logout_response = client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 200

    # Verify cookie has expired
    cookie = next((c for c in logout_response.cookies.jar if c.name == "refresh_token"), None)
    # A deleted cookie has max_age=0 or expires set in the past
    assert cookie is None or cookie.expires is not None


def test_api_key_lifecycle(client):
    """Assert creating, listing, and revoking API keys behaves correctly."""
    # Register and Login
    client.post(
        "/api/v1/auth/register",
        json={"email": "keys@example.com", "password": "securepassword"}
    )
    login_response = client.post(
        "/api/v1/auth/login",
        data={"username": "keys@example.com", "password": "securepassword"}
    )
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create Key
    create_response = client.post(
        "/api/v1/keys",
        json={"name": "test-key-1"},
        headers=headers
    )
    assert create_response.status_code == 201
    data = create_response.json()
    assert data["name"] == "test-key-1"
    assert "raw_key" in data
    assert "prefix" in data

    key_id = data["id"]
    raw_key = data["raw_key"]

    # 2. List Keys
    list_response = client.get("/api/v1/keys", headers=headers)
    assert list_response.status_code == 200
    keys_list = list_response.json()
    assert len(keys_list) == 1
    assert keys_list[0]["id"] == key_id

    # 3. Key check validation endpoint
    check_response = client.get(
        "/api/v1/auth/key-check",
        headers={"X-API-KEY": raw_key}
    )
    assert check_response.status_code == 200
    check_data = check_response.json()
    assert check_data["status"] == "authenticated"
    assert check_data["email"] == "keys@example.com"
    assert check_data["key_name"] == "test-key-1"

    # 4. Revoke Key
    revoke_response = client.delete(
        f"/api/v1/keys/{key_id}",
        headers=headers
    )
    assert revoke_response.status_code == 204

    # 5. Verify it's revoked in list
    post_list_response = client.get("/api/v1/keys", headers=headers)
    assert len(post_list_response.json()) == 0

    # 6. Verify key check fails now
    check_revoked_response = client.get(
        "/api/v1/auth/key-check",
        headers={"X-API-KEY": raw_key}
    )
    assert check_revoked_response.status_code == 401


VERIFY = "/api/v1/auth/verify"


def test_verify_accepts_a_live_session(client, make_user):
    """The nginx auth gate lets a logged-in browser through."""
    make_user(email="gate-live@example.com")

    response = client.get(VERIFY)

    assert response.status_code == 200
    assert response.json()["auth"] == "session"


def test_verify_rejects_a_session_cookie_after_logout(client, make_user):
    """Logging out revokes the cookie for the gate, not just for the browser.

    The token is replayed by hand because logout also clears it client-side;
    without that the request would carry no cookie at all and would be refused
    for the wrong reason. This is the stolen-cookie case.
    """
    make_user(email="gate-logout@example.com")
    stolen = client.cookies.get("session_token")
    assert stolen

    assert client.get(VERIFY).status_code == 200

    assert client.post("/api/v1/auth/logout").status_code == 200

    replayed = client.get(VERIFY, headers={"Cookie": f"session_token={stolen}"})
    assert replayed.status_code == 401


def test_verify_rejects_a_deactivated_user(client, make_user, db_session):
    """Deactivating an account closes the gate for sessions it already had."""
    from app.models import User

    user = make_user(email="gate-inactive@example.com")
    assert client.get(VERIFY).status_code == 200

    record = db_session.query(User).filter(User.email == user["email"]).first()
    record.is_active = False
    db_session.commit()

    assert client.get(VERIFY).status_code == 401


def test_verify_still_accepts_an_api_key(client, make_user):
    """The programmatic path is unchanged by the session-revocation check."""
    user = make_user(email="gate-key@example.com")
    created = client.post(
        "/api/v1/keys", json={"name": "gate-key"}, headers=user["headers"]
    )
    assert created.status_code == 201, created.text
    raw_key = created.json()["raw_key"]

    client.cookies.clear()
    response = client.get(VERIFY, headers={"X-API-KEY": raw_key})

    assert response.status_code == 200
    assert response.json()["auth"] == "api_key"


def test_logout_revokes_when_only_the_session_cookie_is_present(client, make_user):
    """The refresh cookie is not the only way to say who is logging out.

    A client can hold a session token without a refresh token: the refresh
    cookie is scoped to /api/v1/auth and has a shorter life of its own. Logout
    used to revoke nothing in that case and still answer "Successfully logged
    out", leaving the session token working for the rest of its lifetime. That
    is the token an attacker would have.
    """
    make_user(email="session-only-logout@example.com")
    stolen = client.cookies.get("session_token")
    assert stolen

    client.cookies.delete("refresh_token", path="/api/v1/auth")
    assert client.cookies.get("refresh_token") is None

    assert client.post("/api/v1/auth/logout").status_code == 200

    replayed = client.get(VERIFY, headers={"Cookie": f"session_token={stolen}"})
    assert replayed.status_code == 401
