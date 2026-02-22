from motor.motor_asyncio import AsyncIOMotorDatabase
from openai import AsyncOpenAI
from src._config.settings import settings
from .schemas import InventoryItem, RecipeRequest, RecipeResponse
from typing import List
import logging

logger = logging.getLogger(__name__)

class InventoryService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db.inventory

    async def add_item(self, item: InventoryItem):
        item_dict = item.model_dump()
        result = await self.collection.insert_one(item_dict)
        return str(result.inserted_id)

    async def get_items(self, user_id: str) -> List[InventoryItem]:
        cursor = self.collection.find({"user_id": user_id})
        items = []
        async for doc in cursor:
            # removing _id from mongo doc before creating pydantic model
            doc.pop("_id", None)
            items.append(InventoryItem(**doc))
        return items

class RecipeGenerationService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.inventory_service = InventoryService(db)

    async def suggest_recipe(self, request: RecipeRequest, user_id: str) -> RecipeResponse:
        inventory_items = await self.inventory_service.get_items(user_id)
        
        inventory_list = [f"{item.quantity} {item.unit} of {item.name}" for item in inventory_items]
        inventory_str = ", ".join(inventory_list)
        
        system_prompt = (
            "You are a helpful nutrition assistant. Create a healthy recipe using the available ingredients. "
            "You can assume basic pantry staples (oil, salt, pepper, etc.) are available. "
        )
        
        user_message = f"Here is my inventory: {inventory_str}. "
        if request.prompt:
            user_message += f"My request: {request.prompt}. "
        if request.preferences:
            user_message += f"My preferences: {request.preferences}. "

        try:
            completion = await self.client.beta.chat.completions.parse(
                model="gpt-4o-2024-08-06",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                response_format=RecipeResponse,
            )
            return completion.choices[0].message.parsed
        except Exception as e:
            logger.error(f"Error generating recipe: {e}")
            raise e
