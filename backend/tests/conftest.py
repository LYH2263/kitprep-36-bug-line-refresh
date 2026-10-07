import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="kitprep-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["SEED_ON_EMPTY"] = "false"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import models
from app.services.seed import seed_if_empty


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for t in (models.PrepRun, models.OrderLine, models.KitchenOrder,
                  models.BomLine, models.Ingredient, models.Dish):
            db.query(t).delete()
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def seeded(client):
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()
    return client
