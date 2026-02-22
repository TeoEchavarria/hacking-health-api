from fastapi import APIRouter, Depends, HTTPException, status
from src.core.database import get_database
from motor.motor_asyncio import AsyncIOMotorDatabase
from .schemas import InventoryItem, RecipeRequest, RecipeResponse
from .services import InventoryService, RecipeGenerationService
from typing import List

router = APIRouter()

def get_inventory_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> InventoryService:
    return InventoryService(db)

def get_recipe_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> RecipeGenerationService:
    return RecipeGenerationService(db)

@router.get("/inventory", response_model=List[InventoryItem])
async def get_inventory(
    user_id: str,
    service: InventoryService = Depends(get_inventory_service)
):
    """Retrieve the user's current inventory."""
    return await service.get_items(user_id)

@router.post("/inventory", response_model=dict, status_code=status.HTTP_201_CREATED)
async def add_inventory_item(
    item: InventoryItem,
    service: InventoryService = Depends(get_inventory_service)
):
    """Add a new food item to the kitchen."""
    item_id = await service.add_item(item)
    return {"id": item_id, "message": "Item added successfully"}

@router.post("/recipes/suggest", response_model=RecipeResponse)
async def suggest_recipe(
    request: RecipeRequest,
    user_id: str,
    service: RecipeGenerationService = Depends(get_recipe_service)
):
    """Triggers the OpenAI generation service."""
    return await service.suggest_recipe(request, user_id)
