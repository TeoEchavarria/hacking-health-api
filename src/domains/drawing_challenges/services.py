"""
Drawing Challenge Service
Serves random drawing images for the drawing challenge feature.
"""
import random
import os
from pathlib import Path
from typing import Tuple
from src._config.logger import get_logger

logger = get_logger(__name__)

# Path to images folder
IMAGES_DIR = Path(__file__).parent.parent.parent / "images"

# Image names with descriptive titles
IMAGE_NAMES = {
    "image.png": "Estrella Chef",
    "image copy.png": "Cafetera Pájaro",
    "image copy 2.png": "Tortuga Reloj",
    "image copy 3.png": "Mariposa Lápiz",
    "image copy 4.png": "Teléfono Abeja",
    "image copy 5.png": "Dinosaurio Paraguas",
    "image copy 6.png": "Pez Radio",
    "image copy 7.png": "Botella Ratón",
    "image copy 8.png": "Sándwich Reloj",
    "image copy 9.png": "Silla Helado",
    "image copy 10.png": "Tetera Gato",
    "image copy 11.png": "Robot Zanahoria",
    "image copy 12.png": "Lavadora Chef",
    "image copy 13.png": "Bicicleta Reloj",
    "image copy 14.png": "Lámpara Perro",
    "image copy 15.png": "Cuchara Flor",
    "image copy 16.png": "Árbol Tenedor",
    "image copy 17.png": "Tetera Manzana",
}


class DrawingChallengeService:
    """
    Service for serving random drawing challenge images.
    Uses local images instead of external API.
    """
    _instance = None
    _images: list = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._images = list(IMAGE_NAMES.keys())
            logger.info(f"DrawingChallengeService initialized with {len(cls._images)} images from {IMAGES_DIR}")
        return cls._instance
    
    @property
    def categories(self) -> list:
        """Get list of all available drawing names."""
        return list(IMAGE_NAMES.values())
    
    def get_random_drawing(self) -> Tuple[bytes, str]:
        """
        Get a random drawing from the local images folder.
        
        Returns:
            Tuple of (png_bytes, drawing_name)
        """
        # Pick random image
        image_file = random.choice(self._images)
        drawing_name = IMAGE_NAMES.get(image_file, "Dibujo")
        
        image_path = IMAGES_DIR / image_file
        logger.info(f"Selected drawing: {drawing_name} ({image_file})")
        
        # Read image bytes
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        
        return image_bytes, drawing_name


# Global singleton instance
quick_draw_service = DrawingChallengeService()
