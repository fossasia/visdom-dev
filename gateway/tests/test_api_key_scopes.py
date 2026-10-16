# Copyright 2017-present, The Visdom Authors
import uuid

KEYS = "/api/v1/keys"
KEY_CHECK = "/api/v1/auth/key-check"
WORKSPACES = "/api/v1/workspaces"


def test_scope_payload_validation(client, make_user, make_workspace):
    user = make_user()
    workspace = make_workspace(user)

    no_ids = client.post(
        KEYS, json={"name": "bad", "scope": "workspace", "workspace_ids": []}, headers=user["headers"]
    )
    assert no_ids.status_code == 422

    org_with_ids = client.post(
        KEYS,
        json={"name": "bad", "scope": "org", "workspace_ids": [workspace["id"]]},
        headers=user["headers"],
    )
    assert org_with_ids.status_code == 422


def test_workspace_scoped_key_enforcement(client, make_user, make_workspace):
    user = make_user()
    bound_ws = make_workspace(user)
    other_ws = make_workspace(user)

    created = client.post(
        KEYS,
        json={"name": "scoped", "scope": "workspace", "workspace_ids": [bound_ws["id"]]},
        headers=user["headers"],
    )
    assert created.status_code == 201
    data = created.json()
    assert data["scope"] == "workspace"
    assert [ws["id"] for ws in data["workspaces"]] == [bound_ws["id"]]
    raw_key = data["raw_key"]

    plain = client.get(KEY_CHECK, headers={"X-API-KEY": raw_key})
    assert plain.status_code == 200
    assert plain.json()["scope"] == "workspace"

    granted = client.get(
        KEY_CHECK, params={"workspace_id": bound_ws["id"]}, headers={"X-API-KEY": raw_key}
    )
    assert granted.status_code == 200
    assert granted.json()["workspace_access"] == "granted"
    assert granted.json()["workspace_id"] == bound_ws["id"]

    unbound = client.get(
        KEY_CHECK, params={"workspace_id": other_ws["id"]}, headers={"X-API-KEY": raw_key}
    )
    assert unbound.status_code == 403
    assert unbound.json()["detail"] == "This API key is not scoped to this workspace."

    unknown = client.get(
        KEY_CHECK, params={"workspace_id": str(uuid.uuid4())}, headers={"X-API-KEY": raw_key}
    )
    assert unknown.status_code == 403
    assert unknown.json()["detail"] == "This API key's owner is not a member of this workspace."


def test_workspace_key_requires_active_membership(client, make_user, make_workspace):
    owner = make_user()
    stranger = make_user()
    workspace = make_workspace(owner)

    as_stranger = client.post(
        KEYS,
        json={"name": "sneaky", "scope": "workspace", "workspace_ids": [workspace["id"]]},
        headers=stranger["headers"],
    )
    assert as_stranger.status_code == 403

    client.post(
        f"{WORKSPACES}/{workspace['id']}/members",
        json={"email": stranger["email"], "role": "member"},
        headers=owner["headers"],
    )
    while_pending = client.post(
        KEYS,
        json={"name": "still-sneaky", "scope": "workspace", "workspace_ids": [workspace["id"]]},
        headers=stranger["headers"],
    )
    assert while_pending.status_code == 403


def test_org_key_follows_membership(client, make_user, make_workspace, add_member):
    owner = make_user()
    member = make_user()
    workspace = make_workspace(owner)
    add_member(owner, workspace, member)

    created = client.post(KEYS, json={"name": "org-key"}, headers=member["headers"])
    assert created.status_code == 201
    assert created.json()["scope"] == "org"
    raw_key = created.json()["raw_key"]

    granted = client.get(
        KEY_CHECK, params={"workspace_id": workspace["id"]}, headers={"X-API-KEY": raw_key}
    )
    assert granted.status_code == 200
    assert granted.json()["workspace_access"] == "granted"

    removed = client.delete(
        f"{WORKSPACES}/{workspace['id']}/members/{member['id']}", headers=owner["headers"]
    )
    assert removed.status_code == 204

    rejected = client.get(
        KEY_CHECK, params={"workspace_id": workspace["id"]}, headers={"X-API-KEY": raw_key}
    )
    assert rejected.status_code == 403

    still_valid = client.get(KEY_CHECK, headers={"X-API-KEY": raw_key})
    assert still_valid.status_code == 200


def test_expired_key_rejected(client, make_user):
    user = make_user(tier="enterprise")

    expired = client.post(
        KEYS, json={"name": "expired", "expires_at": "2020-01-01T00:00:00Z"}, headers=user["headers"]
    ).json()
    naive_expired = client.post(
        KEYS, json={"name": "naive-expired", "expires_at": "2020-01-01T00:00:00"}, headers=user["headers"]
    ).json()
    fresh = client.post(
        KEYS, json={"name": "fresh", "expires_at": "2099-01-01T00:00:00Z"}, headers=user["headers"]
    ).json()

    for key in (expired, naive_expired):
        response = client.get(KEY_CHECK, headers={"X-API-KEY": key["raw_key"]})
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid, expired, or inactive API key."

    ok = client.get(KEY_CHECK, headers={"X-API-KEY": fresh["raw_key"]})
    assert ok.status_code == 200


def test_key_use_is_recorded_then_throttled(client, make_user):
    user = make_user()
    created = client.post(KEYS, json={"name": "stamped"}, headers=user["headers"]).json()

    def last_used():
        listed = client.get(KEYS, headers=user["headers"]).json()
        return next(key["last_used_at"] for key in listed if key["id"] == created["id"])

    assert last_used() is None

    assert client.get(KEY_CHECK, headers={"X-API-KEY": created["raw_key"]}).status_code == 200
    first = last_used()
    assert first is not None

    # A second use inside the throttle window must not write again, otherwise every
    # request on the read path costs a commit.
    assert client.get(KEY_CHECK, headers={"X-API-KEY": created["raw_key"]}).status_code == 200
    assert last_used() == first


def test_a_rejected_key_is_not_stamped(client, make_user):
    user = make_user()
    expired = client.post(
        KEYS, json={"name": "expired", "expires_at": "2020-01-01T00:00:00Z"}, headers=user["headers"]
    ).json()

    assert client.get(KEY_CHECK, headers={"X-API-KEY": expired["raw_key"]}).status_code == 401

    listed = client.get(KEYS, headers=user["headers"]).json()
    assert next(key["last_used_at"] for key in listed if key["id"] == expired["id"]) is None
