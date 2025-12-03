import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock
from src.main import app
from src.core.database import get_database, db

@pytest.fixture(scope="module")
def client():
    # Mock the database dependency
    mock_db = AsyncMock()
    mock_db.sensor_data = AsyncMock()
    
    # Mock insert_many result
    mock_result = MagicMock()
    mock_result.inserted_ids = ["id1"]
    mock_db.sensor_data.insert_many = AsyncMock(return_value=mock_result)
    
    # Mock users collection
    mock_db.users = AsyncMock()
    mock_db.users.find_one = AsyncMock(return_value=None) # Default to user not found
    mock_db.users.insert_one = AsyncMock()
    
    def override_get_database():
        return mock_db
    
    app.dependency_overrides[get_database] = override_get_database
    
    # Prevent actual DB connection attempts during tests
    db.connect = MagicMock()
    db.close = MagicMock()
    db.client = AsyncMock() # Mock client so check_db_connection doesn't fail immediately if called directly
    
    with TestClient(app) as c:
        yield c
    
    app.dependency_overrides.clear()
