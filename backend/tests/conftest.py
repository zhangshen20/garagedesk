import os

import pytest

os.environ["DATABASE_URL"] = "sqlite://"  # in-memory
os.environ["LLM_MODE"] = "mock"
os.environ["GARAGEDESK_SCHEDULER"] = "0"
os.environ["TTS_MODE"] = "mock"
os.environ["FILES_DIR"] = "/tmp/garagedesk-test-files"


@pytest.fixture()
def client():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import create_engine

    from app import db
    from app.config import get_settings
    from app.llm import reset_llm

    from app.voice import offers

    get_settings.cache_clear()
    reset_llm()
    offers.clear()
    db.reset_engine()
    # one shared in-memory connection for the whole test
    db._engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
    db.reset_engine()
