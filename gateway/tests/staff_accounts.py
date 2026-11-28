# Copyright 2017-present, The Visdom Authors
from app.models import AdminUser, User
from app.security import create_access_token, get_password_hash, session_claims


def create_staff(db, email, role):
    user = User(
        email=email,
        username=email.split("@")[0],
        password_hash=get_password_hash("dashboard-password"),
        tier="enterprise",
    )
    db.add(user)
    db.flush()
    member = AdminUser(email=email, role=role, user_id=user.id)
    db.add(member)
    db.commit()
    return member


def use_session(client, db, email):
    user = db.query(User).filter_by(email=email).one()
    client.cookies.set("session_token", create_access_token(session_claims(user)))
