import pytest
from unittest.mock import AsyncMock, patch
from src.core.database import check_db_connection, db

@pytest.mark.asyncio
async def test_database_connection():
    """
    Test that the database connection check returns True.
    """
    # Mock the client command to return successfully
    db.client = AsyncMock()
    db.client.admin.command = AsyncMock(return_value={"ok": 1})
    
    result = await check_db_connection()
    assert result is True
