"""
Business logic for pairing domain.
"""
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from bson import ObjectId
import random
import string
from src._config.logger import get_logger

logger = get_logger(__name__)

# Constants
CODE_LENGTH = 6
CODE_EXPIRY_MINUTES = 10
COLLECTION_NAME = "pairings"


class PairingService:
    """Service for managing family pairing operations."""
    
    def __init__(self, db):
        self.db = db
        self.collection = db[COLLECTION_NAME]
    
    @staticmethod
    def generate_code() -> str:
        """
        Generate a random 6-digit numeric code.
        
        Returns:
            str: 6-digit code
        """
        return ''.join(random.choices(string.digits, k=CODE_LENGTH))
    
    async def create_pairing_code(self, user_id: str) -> Dict[str, Any]:
        """
        Create a new pairing code for a patient.
        
        Args:
            user_id: ID of the patient user
            
        Returns:
            Dict with pairing_id, code, created_at, expires_at
        """
        # Get user info
        user = await self.db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise ValueError("User not found")
        
        # CLEANUP: Delete any existing pending codes for this patient
        # This prevents accumulation of unused pairing codes
        cleanup_result = await self.collection.delete_many({
            "patientId": user_id,
            "status": "pending"
        })
        if cleanup_result.deleted_count > 0:
            logger.info(f"Cleaned up {cleanup_result.deleted_count} old pending codes for user {user_id}")
        
        # Generate unique code (retry if collision)
        max_retries = 10
        code = None
        for _ in range(max_retries):
            candidate_code = self.generate_code()
            # Check if code is already active
            existing = await self.collection.find_one({
                "code": candidate_code,
                "status": "pending",
                "expiresAt": {"$gt": datetime.now(timezone.utc)}
            })
            if not existing:
                code = candidate_code
                break
        
        if not code:
            raise RuntimeError("Could not generate unique code")
        
        # Calculate expiry
        created_at = datetime.now(timezone.utc)
        expires_at = created_at + timedelta(minutes=CODE_EXPIRY_MINUTES)
        
        # Create pairing document
        pairing_doc = {
            "patientId": user_id,
            "patientName": user.get("name", "Usuario"),
            "code": code,
            "status": "pending",
            "createdAt": created_at,
            "expiresAt": expires_at,
            "activatedAt": None,
            "caregiverId": None,
            "caregiverName": None
        }
        
        result = await self.collection.insert_one(pairing_doc)
        pairing_id = str(result.inserted_id)
        
        logger.info(f"Created pairing code {code} for user {user_id}, expires in {CODE_EXPIRY_MINUTES} minutes")
        
        return {
            "pairing_id": pairing_id,
            "code": code,
            "created_at": int(created_at.timestamp() * 1000),
            "expires_at": int(expires_at.timestamp() * 1000)
        }
    
    async def validate_pairing_code(
        self, 
        code: str, 
        caregiver_id: str
    ) -> Dict[str, Any]:
        """
        Validate a pairing code and activate the pairing.
        
        Args:
            code: 6-digit pairing code
            caregiver_id: ID of the caregiver user
            
        Returns:
            Dict with success, pairing_id, patient_id, patient_name, or error
        """
        # Get caregiver info
        caregiver = await self.db.users.find_one({"_id": ObjectId(caregiver_id)})
        if not caregiver:
            return {
                "success": False,
                "error": "Caregiver user not found"
            }
        
        # Find active pairing code
        pairing = await self.collection.find_one({
            "code": code,
            "status": "pending"
        })
        
        if not pairing:
            logger.warning(f"Invalid or inactive pairing code: {code}")
            return {
                "success": False,
                "error": "Código inválido o ya fue usado"
            }
        
        # Check expiry
        expires_at = pairing["expiresAt"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        
        if expires_at < datetime.now(timezone.utc):
            # Mark as expired
            await self.collection.update_one(
                {"_id": pairing["_id"]},
                {"$set": {"status": "expired"}}
            )
            logger.warning(f"Pairing code {code} has expired")
            return {
                "success": False,
                "error": "El código ha expirado"
            }
        
        # Prevent self-pairing
        if pairing["patientId"] == caregiver_id:
            logger.warning(f"User {caregiver_id} attempted to pair with themselves")
            return {
                "success": False,
                "error": "No puedes vincularte contigo mismo"
            }
        
        # Check for existing active pairing between this patient and caregiver
        existing_pairing = await self.collection.find_one({
            "patientId": pairing["patientId"],
            "caregiverId": caregiver_id,
            "status": "active"
        })
        if existing_pairing:
            logger.warning(f"Duplicate pairing attempt: caregiver {caregiver_id} already paired with patient {pairing['patientId']}")
            return {
                "success": False,
                "error": "Ya tienes una vinculación activa con esta persona"
            }
        
        # Activate pairing
        activated_at = datetime.now(timezone.utc)
        await self.collection.update_one(
            {"_id": pairing["_id"]},
            {
                "$set": {
                    "status": "active",
                    "caregiverId": caregiver_id,
                    "caregiverName": caregiver.get("name", "Cuidador"),
                    "activatedAt": activated_at
                },
                "$unset": {
                    "code": "",  # Remove code for security
                    "expiresAt": ""
                }
            }
        )
        
        logger.info(
            f"Pairing activated: {caregiver.get('name')} (caregiver) <-> "
            f"{pairing['patientName']} (patient)"
        )
        
        return {
            "success": True,
            "pairing_id": str(pairing["_id"]),
            "patient_id": pairing["patientId"],
            "patient_name": pairing["patientName"]
        }
    
    async def get_pairing_status(self, pairing_id: str) -> Dict[str, Any]:
        """
        Get the current status of a pairing.
        
        Args:
            pairing_id: ID of the pairing
            
        Returns:
            Dict with pairing status information
        """
        try:
            pairing = await self.collection.find_one({"_id": ObjectId(pairing_id)})
        except Exception:
            logger.error(f"Invalid pairing_id format: {pairing_id}")
            raise ValueError("Invalid pairing ID")
        
        if not pairing:
            raise ValueError("Pairing not found")
        
        # Check if expired but not marked
        if (pairing["status"] == "pending" and 
            pairing.get("expiresAt")):
            # Make sure both datetimes are timezone-aware for comparison
            expires_at = pairing["expiresAt"]
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            
            if expires_at < datetime.now(timezone.utc):
                # Mark as expired
                await self.collection.update_one(
                    {"_id": pairing["_id"]},
                    {"$set": {"status": "expired"}}
                )
                pairing["status"] = "expired"
        
        return {
            "pairing_id": str(pairing["_id"]),
            "status": pairing["status"],
            "linked": pairing["status"] == "active",
            "caregiver_id": pairing.get("caregiverId"),
            "caregiver_name": pairing.get("caregiverName"),
            "patient_id": pairing.get("patientId"),
            "patient_name": pairing.get("patientName"),
            "created_at": int(pairing["createdAt"].timestamp() * 1000),
            "expires_at": (
                int(pairing["expiresAt"].timestamp() * 1000) 
                if pairing.get("expiresAt") else None
            ),
            "activated_at": (
                int(pairing["activatedAt"].timestamp() * 1000)
                if pairing.get("activatedAt") else None
            )
        }
    
    async def get_user_pairings(
        self, 
        user_id: str, 
        role: str = "patient"
    ) -> list:
        """
        Get all pairings for a user.
        
        Args:
            user_id: ID of the user
            role: "patient" or "caregiver"
            
        Returns:
            List of pairing documents
        """
        field = "patientId" if role == "patient" else "caregiverId"
        cursor = self.collection.find({
            field: user_id,
            "status": "active"
        })
        pairings = await cursor.to_list(length=100)
        
        # Convert ObjectId to string
        for pairing in pairings:
            pairing["_id"] = str(pairing["_id"])
        
        return pairings
