"""
Drawing Challenge Routes
Endpoints for the drawing challenge feature using Google's Quick Draw dataset.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from src.domains.drawing_challenges.services import quick_draw_service
from src._config.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/drawing-challenge",
    tags=["drawing-challenge"]
)


@router.get("/random")
async def get_random_drawing():
    """
    Get a random drawing from the Quick Draw dataset.
    
    Returns a PNG image directly with the category name in the X-Drawing-Category header.
    
    This endpoint is public (no authentication required) as the drawings
    are not sensitive data.
    """
    try:
        # Get random drawing
        png_bytes, category = quick_draw_service.get_random_drawing()
        
        logger.info(f"Serving random drawing from category: {category}")
        
        # Return PNG image with category in header
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={
                "X-Drawing-Category": category,
                "Content-Disposition": f'inline; filename="{category}.png"'
            }
        )
    except Exception as e:
        logger.error(f"Error getting random drawing: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error generating drawing: {str(e)}"
        )


@router.get("/categories")
async def get_categories():
    """
    Get list of all available drawing categories.
    
    Useful for displaying what category the user needs to draw.
    """
    try:
        categories = quick_draw_service.categories
        return {
            "status": "success",
            "count": len(categories),
            "categories": categories
        }
    except Exception as e:
        logger.error(f"Error getting categories: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching categories: {str(e)}"
        )
