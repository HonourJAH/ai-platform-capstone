from app.config import settings


def _create_user_and_key(client, email="test@example.com", tier="free"):
    resp = client.post(
        "/admin/users",
        json={"email": email, "tier": tier},
        headers={"x-admin-key": "anything-since-verify_admin-is-overridden"},
    )
    assert resp.status_code == 201
    user_id = resp.json()["user_id"]

    resp = client.post(
        f"/admin/users/{user_id}/keys",
        headers={"x-admin-key": "anything-since-verify_admin-is-overridden"},
    )
    assert resp.status_code == 201
    raw_key = resp.json()["raw_key"]

    return user_id, raw_key


def test_inference_rejects_missing_api_key(client):
    resp = client.post(
        "/inference", json={"task_type": "text_classification", "text": "great"}
    )
    assert resp.status_code == 422 or resp.status_code == 401


def test_inference_rejects_invalid_api_key(client):
    resp = client.post(
        "/inference",
        json={"task_type": "text_classification", "text": "great product"},
        headers={"x-api-key": "sk_live_not_a_real_key"},
    )
    assert resp.status_code == 401


def test_text_classification_end_to_end(client):
    _, raw_key = _create_user_and_key(client)

    resp = client.post(
        "/inference",
        json={"task_type": "text_classification", "text": "this is amazing, I love it"},
        headers={"x-api-key": raw_key},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["result"]["label"] in ("positive", "negative")


def test_rate_limit_returns_429_after_capacity_exhausted(client):
    _, raw_key = _create_user_and_key(client, email="limited@example.com")
    capacity = settings.rate_limit_tiers["free"]["capacity"]

    for _ in range(capacity):
        resp = client.post(
            "/inference",
            json={"task_type": "text_classification", "text": "fine"},
            headers={"x-api-key": raw_key},
        )
        assert resp.status_code == 200

    resp = client.post(
        "/inference",
        json={"task_type": "text_classification", "text": "fine"},
        headers={"x-api-key": raw_key},
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_revoked_key_is_rejected(client):
    resp = client.post(
        "/admin/users",
        json={"email": "revoke-me@example.com"},
        headers={"x-admin-key": "anything"},
    )
    user_id = resp.json()["user_id"]

    resp = client.post(
        f"/admin/users/{user_id}/keys", headers={"x-admin-key": "anything"}
    )
    raw_key = resp.json()["raw_key"]

    keys_resp = client.get(
        f"/admin/users/{user_id}/keys", headers={"x-admin-key": "anything"}
    )
    key_id = keys_resp.json()[0]["id"]

    revoke_resp = client.delete(
        f"/admin/keys/{key_id}", headers={"x-admin-key": "anything"}
    )
    assert revoke_resp.status_code == 204

    resp = client.post(
        "/inference",
        json={"task_type": "text_classification", "text": "fine"},
        headers={"x-api-key": raw_key},
    )
    assert resp.status_code == 401
