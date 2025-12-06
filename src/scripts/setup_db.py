import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from src.core.database import db
from src._config.logger import get_logger

logger = get_logger(__name__)

async def setup_indexes():
    try:
        db.connect()
        database = db.get_db()
        
        logger.info("Creating indexes for sensor_data collection...")
        
        # Index 1: userId (for querying all data for a user)
        await database.sensor_data.create_index("userId")
        logger.info("Created index: userId")
        
        # Index 2: Compound userId + timestamp (for time-series queries per user)
        await database.sensor_data.create_index([("userId", 1), ("timestamp", 1)])
        logger.info("Created index: userId + timestamp")
        
        # Index 3: Unique Constraint to prevent duplicates
        # userId + deviceId + timestamp + source
        await database.sensor_data.create_index(
            [("userId", 1), ("deviceId", 1), ("timestamp", 1), ("source", 1)],
            unique=True
        )
        logger.info("Created unique index: userId + deviceId + timestamp + source")
        
        logger.info("Index setup complete.")
        
    except Exception as e:
        logger.error(f"Error setting up indexes: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(setup_indexes())
