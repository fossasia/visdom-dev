# Copyright 2017-present, The Visdom Authors
import itertools
import os

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["USAGE_SAMPLE_SECONDS"] = "0"
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-0123456789abcdef")

from app import security
from app.database import Base
from app.dependencies import get_db
from app.main import app

security.gensalt = lambda: bcrypt.gensalt(rounds=4)

# Setup a clean in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_counter = itertools.count(1)

@pytest.fixture(scope="function", autouse=True)
def setup_database():
    """Auto-creates tables before each test and drops them after.

    The plans are seeded as the migration seeds them, since the schema here
    comes from the models and not from the migrations.
    """
    from app.billing import seed_default_plans

    Base.metadata.create_all(bind=engine)
    seeder = TestingSessionLocal()
    try:
        seed_default_plans(seeder)
    finally:
        seeder.close()
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def db_session():
    """Provides a fresh database session for assertions inside test functions."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="function")
def client(db_session):
    """Provides a TestClient with overridden database dependencies."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture
def make_user(client, db_session):
    def _make(email=None, password="securepassword", username=None, tier=None):
        if email is None:
            email = f"user{next(_counter)}@example.com"
        payload = {"email": email, "password": password}
        if username:
            payload["username"] = username
        registered = client.post("/api/v1/auth/register", json=payload)
        assert registered.status_code == 201, registered.text
        if tier is not None:
            from app.models import User

            record = db_session.query(User).filter(User.email == email).first()
            record.tier = tier
            db_session.commit()

        logged_in = client.post(
            "/api/v1/auth/login", data={"username": email, "password": password}
        )
        assert logged_in.status_code == 200, logged_in.text
        return {
            "id": registered.json()["id"],
            "email": registered.json()["email"],
            "username": registered.json()["username"],
            "password": password,
            "headers": {"Authorization": f"Bearer {logged_in.json()['access_token']}"},
        }
    return _make

@pytest.fixture
def make_workspace(client, db_session):
    """Create a workspace, lifting the owner's plan limit out of the way.

    Scaffolding for tests that are not about billing should not be refused by
    it. The tests that do exercise the limits create their users fresh on the
    default free tier and post to the endpoint directly.
    """
    def _make(user, name=None, slug=None):
        from app.models import User

        owner = db_session.query(User).filter(User.email == user["email"]).first()
        if owner is not None and owner.tier != "enterprise":
            owner.tier = "enterprise"
            db_session.commit()
        n = next(_counter)
        response = client.post(
            "/api/v1/workspaces",
            json={"name": name or f"Workspace {n}", "slug": slug or f"workspace-{n}"},
            headers=user["headers"],
        )
        assert response.status_code == 201, response.text
        return response.json()
    return _make

@pytest.fixture
def add_member(client):
    def _add(admin, workspace, invitee, role="member"):
        invited = client.post(
            f"/api/v1/workspaces/{workspace['id']}/members",
            json={"email": invitee["email"], "role": role},
            headers=admin["headers"],
        )
        assert invited.status_code == 201, invited.text
        accepted = client.post(
            f"/api/v1/workspaces/{workspace['id']}/members/me/accept",
            headers=invitee["headers"],
        )
        assert accepted.status_code == 200, accepted.text
        return accepted.json()
    return _add
