"""
OpenWearables Service Stub
This is a minimal stub to satisfy auth dependencies.
The actual OpenWearables integration is optional and disabled by default.
"""
from typing import Optional, Dict, Any
from src._config.logger import get_logger
from src._config.settings import settings

logger = get_logger(__name__)


class OpenWearablesService:
    """
    Stub service for OpenWearables integration.
    Returns None/empty when OpenWearables is not configured.
    """
    
    def __init__(self):
        self.configured = bool(
            settings.OPENWEARABLES_APP_ID and 
            settings.OPENWEARABLES_APP_SECRET
        )
        if not self.configured:
            logger.debug("OpenWearables not configured - service disabled")
    
    async def create_user(
        self,
        external_user_id: str,
        email: Optional[str] = None,
        first_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Create user in OpenWearables - returns None if not configured."""
        if not self.configured:
            return None
        # Would call OpenWearables API here if configured
        logger.warning("OpenWearables create_user called but not implemented")
        return None
    
    async def generate_sdk_tokens(
        self,
        ow_user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Generate SDK tokens - returns None if not configured."""
        if not self.configured:
            return None
        logger.warning("OpenWearables generate_sdk_tokens called but not implemented")
        return None
