import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.database import get_session
from app.main import app
from app.services.auth import verify_admin


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="fake_redis")
def fake_redis_fixture():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture(name="client")
def client_fixture(session, fake_redis, monkeypatch):
    def get_session_override():
        return session

    def get_redis_override():
        return fake_redis

    from app.routes.inference import get_rate_limiter
    from app.services.rate_limit import RateLimiter, get_redis_client

    monkeypatch.setattr("app.main.create_db_and_tables", lambda: None)

    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_redis_client] = get_redis_override
    app.dependency_overrides[get_rate_limiter] = lambda: RateLimiter(fake_redis)
    app.dependency_overrides[verify_admin] = lambda: None

    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
