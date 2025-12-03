from motor.motor_asyncio import AsyncIOMotorClient
from src._config.settings import settings
from src._config.logger import get_logger

logger = get_logger(__name__)

class Database:
    client: AsyncIOMotorClient = None
    
    def connect(self):
        """Create database connection."""
        try:
            self.client = AsyncIOMotorClient(settings.MONGO_URI)
            logger.info("Connected to MongoDB.")
        except Exception as e:
            logger.error(f"Could not connect to MongoDB: {e}")
            raise e

    def close(self):
        """Close database connection."""
        if self.client:
            self.client.close()
            logger.info("Closed MongoDB connection.")

    def get_db(self):
        """Get database instance."""
        return self.client[settings.MONGO_DB]

db = Database()

def get_database():
    """Dependency to get database instance"""
    if db.client is None:
        db.connect()
    return db.get_db()

async def check_db_connection():
    """Check if database is responding"""
    try:
        if db.client is None:
            db.connect()
        # The ismaster command is cheap and does not require auth.
        await db.client.admin.command('ismaster')
        return True
    except Exception as e:
        logger.error(f"Database check failed: {e}")
        return False
