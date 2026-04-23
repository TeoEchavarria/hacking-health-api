"""
Quick Draw Service
Provides access to Google's Quick Draw dataset for random drawing challenges.
"""
import random
import io
import os
from typing import Tuple
from quickdraw import QuickDrawData
from src._config.logger import get_logger
from src._config.settings import settings

logger = get_logger(__name__)


class QuickDrawService:
    """
    Singleton service for accessing Quick Draw dataset.
    Initializes QuickDrawData once to avoid reloading the index on each request.
    """
    _instance = None
    _qd = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # Ensure cache directory exists
            cache_dir = settings.QUICKDRAW_CACHE_DIR
            os.makedirs(cache_dir, exist_ok=True)
            cls._qd = QuickDrawData(cache_dir=cache_dir)
            logger.info(f"QuickDrawData initialized with cache at {cache_dir}")
        return cls._instance
    
    @property
    def categories(self) -> list:
        """Get list of all available drawing category names."""
        return self._qd.drawing_names
    
    def get_random_drawing(self) -> Tuple[bytes, str]:
        """
        Get a random drawing from a random category.
        
        Returns:
            Tuple of (png_bytes, category_name)
        """
        # Pick random category
        category = random.choice(self._qd.drawing_names)
        logger.info(f"Selected category: {category}")
        
        # Get random drawing from that category
        # Note: First time accessing a category will download its .bin file
        drawing = self._qd.get_drawing(category)
        
        # Convert to PIL Image and then to PNG bytes
        pil_image = drawing.image
        
        # Save to bytes buffer
        img_buffer = io.BytesIO()
        pil_image.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        return img_buffer.getvalue(), category


# Global singleton instance
quick_draw_service = QuickDrawService()
