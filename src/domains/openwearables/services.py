import httpx
from typing import Optional
from src._config.settings import settings
from src._config.logger import get_logger

logger = get_logger(__name__)


class OpenWearablesService:
    """Service for interacting with OpenWearables API"""
    
    def __init__(self):
        self.host = settings.OPENWEARABLES_HOST
        self.app_id = settings.OPENWEARABLES_APP_ID
        self.app_secret = settings.OPENWEARABLES_APP_SECRET
    
    def _get_headers(self) -> dict:
        """Get headers for API requests"""
        headers = {"Content-Type": "application/json"}
        if self.app_secret:
            headers["X-Open-Wearables-API-Key"] = self.app_secret
        return headers
    
    async def create_user(
        self, 
        external_user_id: str, 
        email: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None
    ) -> dict:
        """
        Create a new user in OpenWearables.
        
        Args:
            external_user_id: Your internal user ID
            email: Optional user email
            first_name: Optional first name
            last_name: Optional last name
            
        Returns:
            OpenWearables user object with 'id' (UUID)
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {"external_user_id": external_user_id}
            if email:
                payload["email"] = email
            if first_name:
                payload["first_name"] = first_name
            if last_name:
                payload["last_name"] = last_name
            
            logger.info(f"Creating OpenWearables user for external_id: {external_user_id}")
            
            response = await client.post(
                f"{self.host}/api/v1/users",
                headers=self._get_headers(),
                json=payload
            )
            
            if response.status_code == 201:
                user = response.json()
                logger.info(f"Created OpenWearables user: {user.get('id')}")
                return user
            elif response.status_code == 409:
                # User already exists, try to find them
                logger.info(f"User already exists, fetching by external_id")
                return await self.get_user_by_external_id(external_user_id)
            else:
                logger.error(f"Failed to create OW user: {response.status_code} - {response.text}")
                response.raise_for_status()
    
    async def get_user_by_external_id(self, external_user_id: str) -> Optional[dict]:
        """
        Find an OpenWearables user by external user ID.
        
        Args:
            external_user_id: Your internal user ID
            
        Returns:
            OpenWearables user object or None
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.host}/api/v1/users",
                headers=self._get_headers(),
                params={"external_user_id": external_user_id}
            )
            
            if response.status_code == 200:
                data = response.json()
                users = data.get("items", [])
                if users:
                    return users[0]
            return None
    
    async def get_user(self, user_id: str) -> Optional[dict]:
        """
        Get an OpenWearables user by ID.
        
        Args:
            user_id: OpenWearables user UUID
            
        Returns:
            OpenWearables user object or None
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.host}/api/v1/users/{user_id}",
                headers=self._get_headers()
            )
            
            if response.status_code == 200:
                return response.json()
            return None
    
    async def create_user_token(self, user_id: str) -> dict:
        """
        Generate SDK tokens for a user.
        
        Args:
            user_id: OpenWearables user UUID
            
        Returns:
            Token response with access_token and refresh_token
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {}
            if self.app_id and self.app_secret:
                payload = {
                    "app_id": self.app_id,
                    "app_secret": self.app_secret
                }
            
            logger.info(f"Generating tokens for OW user: {user_id}")
            
            response = await client.post(
                f"{self.host}/api/v1/users/{user_id}/token",
                headers=self._get_headers(),
                json=payload
            )
            
            if response.status_code == 200:
                tokens = response.json()
                logger.info(f"Generated tokens for user {user_id}")
                return tokens
            else:
                logger.error(f"Failed to generate tokens: {response.status_code} - {response.text}")
                response.raise_for_status()
    
    async def get_user_health_data(
        self, 
        user_id: str, 
        data_type: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> dict:
        """
        Query health data for a user.
        
        Args:
            user_id: OpenWearables user UUID
            data_type: Optional filter by data type (e.g., "heart_rate", "steps")
            from_date: Optional start date (ISO format)
            to_date: Optional end date (ISO format)
            
        Returns:
            Health data records
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            params = {}
            if data_type:
                params["type"] = data_type
            if from_date:
                params["from"] = from_date
            if to_date:
                params["to"] = to_date
            
            response = await client.get(
                f"{self.host}/api/v1/users/{user_id}/health-data",
                headers=self._get_headers(),
                params=params
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get health data: {response.status_code}")
                response.raise_for_status()
