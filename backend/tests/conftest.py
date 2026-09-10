from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)


# Existing fixtures represent the migrated Techspire dataset. Add the college
# row when a test builds an empty database through metadata.create_all().
from sqlalchemy import event
from app.modules.platform.models import College

@event.listens_for(College.__table__, "after_create")
def seed_test_college(table, connection, **kwargs):
    connection.execute(table.insert().values(id=1, name="Techspire College", slug="techspire", is_active=True))
