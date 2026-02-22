from pydantic import BaseModel, Field
from typing import List, Optional

class InventoryItem(BaseModel):
    name: str
    category: str  # vegetable, meat, etc.
    quantity: float
    unit: str  # e.g., grams, units, ml
    user_id: str

class RecipeRequest(BaseModel):
    prompt: Optional[str] = None
    preferences: Optional[str] = None

class RecipeIngredient(BaseModel):
    name: str
    amount: str

class RecipeResponse(BaseModel):
    dish_name: str
    meal_type: str  # Breakfast, Lunch, or Dinner
    ingredients_to_use: List[RecipeIngredient]
    preparation_steps: List[str]
