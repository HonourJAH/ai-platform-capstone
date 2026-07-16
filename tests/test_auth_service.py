from app.services.auth import _hash_key, generate_api_key


def test_generate_api_key_returns_distinct_raw_and_hash():
    raw_key, hashed_key, prefix = generate_api_key()

    assert raw_key.startswith("sk_live_")
    assert raw_key != hashed_key
    assert prefix == raw_key[:12]


def test_hash_key_is_deterministic():
    raw_key, _, _ = generate_api_key()
    assert _hash_key(raw_key) == _hash_key(raw_key)


def test_different_keys_hash_differently():
    raw_key_1, _, _ = generate_api_key()
    raw_key_2, _, _ = generate_api_key()
    assert _hash_key(raw_key_1) != _hash_key(raw_key_2)
