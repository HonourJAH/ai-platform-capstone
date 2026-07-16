from app.services.adapters import ADAPTER_REGISTRY


def _create_user_and_key(client):
    resp = client.post(
        "/admin/users",
        json={"email": "async-user@example.com"},
        headers={"x-admin-key": "anything"},
    )
    user_id = resp.json()["user_id"]
    resp = client.post(
        f"/admin/users/{user_id}/keys", headers={"x-admin-key": "anything"}
    )
    return user_id, resp.json()["raw_key"]


def test_image_classification_returns_queued_job(client, monkeypatch):
    _, raw_key = _create_user_and_key(client)

    monkeypatch.setattr(
        ADAPTER_REGISTRY["image_classification"],
        "enqueue",
        lambda payload: "fake-job-id-123",
    )

    resp = client.post(
        "/inference",
        json={
            "task_type": "image_classification",
            "image_url": "https://example.com/cat.jpg",
        },
        headers={"x-api-key": raw_key},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "queued"
    assert body["job_id"] == "fake-job-id-123"


def test_job_status_endpoint_returns_job_for_owner(client, monkeypatch):
    _, raw_key = _create_user_and_key(client)
    monkeypatch.setattr(
        ADAPTER_REGISTRY["image_classification"],
        "enqueue",
        lambda payload: "fake-job-id-456",
    )

    client.post(
        "/inference",
        json={
            "task_type": "image_classification",
            "image_url": "https://example.com/dog.jpg",
        },
        headers={"x-api-key": raw_key},
    )

    resp = client.get("/inference/jobs/fake-job-id-456", headers={"x-api-key": raw_key})
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


def test_job_status_endpoint_rejects_other_users_jobs(client, monkeypatch):
    _, raw_key_a = _create_user_and_key(client)

    resp = client.post(
        "/admin/users",
        json={"email": "other-user@example.com"},
        headers={"x-admin-key": "anything"},
    )
    other_user_id = resp.json()["user_id"]
    resp = client.post(
        f"/admin/users/{other_user_id}/keys", headers={"x-admin-key": "anything"}
    )
    raw_key_b = resp.json()["raw_key"]

    monkeypatch.setattr(
        ADAPTER_REGISTRY["image_classification"],
        "enqueue",
        lambda payload: "fake-job-id-789",
    )
    client.post(
        "/inference",
        json={
            "task_type": "image_classification",
            "image_url": "https://example.com/x.jpg",
        },
        headers={"x-api-key": raw_key_a},
    )

    resp = client.get(
        "/inference/jobs/fake-job-id-789", headers={"x-api-key": raw_key_b}
    )
    assert resp.status_code == 404
