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
        
        # Convert ObjectId to string and datetime to timestamps
        for pairing in pairings:
            pairing["_id"] = str(pairing["_id"])
            # Convert datetime fields to milliseconds timestamps (Long)
            if "createdAt" in pairing and pairing["createdAt"]:
                pairing["createdAt"] = int(pairing["createdAt"].timestamp() * 1000)
            if "activatedAt" in pairing and pairing["activatedAt"]:
                pairing["activatedAt"] = int(pairing["activatedAt"].timestamp() * 1000)
            if "expiresAt" in pairing and pairing["expiresAt"]:
                pairing["expiresAt"] = int(pairing["expiresAt"].timestamp() * 1000)
        
        return pairings
    
    async def get_my_pairings(self, user_id: str) -> list:
        """
        Get all active pairings where user is either caregiver OR patient.
        
        This is the main method for session initialization - returns all
        relationships regardless of role, with populated user info.
        
        Args:
            user_id: ID of the authenticated user
            
        Returns:
            List of pairing info dicts with role and other user details
        """
        # Find all active pairings where user is either patient or caregiver
        cursor = self.collection.find({
            "$or": [
                {"patientId": user_id},
                {"caregiverId": user_id}
            ],
            "status": "active"
        })
        pairings = await cursor.to_list(length=100)
        
        result = []
        for pairing in pairings:
            # Determine user's role in this pairing
            is_caregiver = pairing.get("caregiverId") == user_id
            role = "caregiver" if is_caregiver else "patient"
            
            # Get the other user's info
            if is_caregiver:
                other_user_id = pairing.get("patientId")
                other_user_name = pairing.get("patientName", "Usuario")
            else:
                other_user_id = pairing.get("caregiverId")
                other_user_name = pairing.get("caregiverName", "Cuidador")
            
            # Fetch other user's profile picture from users collection
            other_user_profile_picture = None
            if other_user_id:
                try:
                    other_user = await self.db.users.find_one({"_id": ObjectId(other_user_id)})
                    if other_user:
                        other_user_profile_picture = other_user.get("profile_picture")
                except Exception as e:
                    logger.warning(f"Could not fetch profile picture for user {other_user_id}: {e}")
            
            # Convert timestamps
            created_at = pairing.get("createdAt")
            activated_at = pairing.get("activatedAt")
            
            result.append({
                "pairing_id": str(pairing["_id"]),
                "role": role,
                "other_user_id": other_user_id,
                "other_user_name": other_user_name,
                "other_user_profile_picture": other_user_profile_picture,
                "status": pairing["status"],
                "activated_at": int(activated_at.timestamp() * 1000) if activated_at else None,
                "created_at": int(created_at.timestamp() * 1000) if created_at else 0
            })
        
        logger.info(f"Retrieved {len(result)} active pairings for user {user_id}")
        return result
    
    async def revoke_pairing(
        self,
        pairing_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Revoke an active pairing.
        
        The user must be either the patient or caregiver in the pairing.
        Sets status to "revoked" instead of deleting for audit trail.
        
        Args:
            pairing_id: ID of the pairing to revoke
            user_id: ID of the user requesting revocation
            
        Returns:
            Dict with success status
        """
        try:
            pairing = await self.collection.find_one({"_id": ObjectId(pairing_id)})
        except Exception:
            logger.error(f"Invalid pairing_id format: {pairing_id}")
            return {
                "success": False,
                "error": "ID de vinculación inválido"
            }
        
        if not pairing:
            return {
                "success": False,
                "error": "Vinculación no encontrada"
            }
        
        # Verify user has permission to revoke
        if pairing.get("patientId") != user_id and pairing.get("caregiverId") != user_id:
            logger.warning(f"User {user_id} attempted to revoke pairing {pairing_id} without permission")
            return {
                "success": False,
                "error": "No tienes permiso para revocar esta vinculación"
            }
        
        # Check if already revoked
        if pairing.get("status") == "revoked":
            return {
                "success": True,
                "message": "La vinculación ya estaba revocada"
            }
        
        # Revoke the pairing
        revoked_at = datetime.now(timezone.utc)
        await self.collection.update_one(
            {"_id": ObjectId(pairing_id)},
            {
                "$set": {
                    "status": "revoked",
                    "revokedAt": revoked_at,
                    "revokedBy": user_id
                }
            }
        )
        
        logger.info(f"Pairing {pairing_id} revoked by user {user_id}")
        
        return {
            "success": True,
            "message": "Vinculación revocada correctamente"
        }
    
    async def get_patient_caregivers(self, patient_id: str) -> list:
        """
        Get all active caregivers for a patient.
        
        Used for sending notifications to caregivers when a patient has a health event.
        
        Args:
            patient_id: ID of the patient
            
        Returns:
            List of caregiver user IDs
        """
        cursor = self.collection.find({
            "patientId": patient_id,
            "status": "active"
        })
        pairings = await cursor.to_list(length=100)
        
        caregiver_ids = [
            p.get("caregiverId") 
            for p in pairings 
            if p.get("caregiverId")
        ]
        
        logger.debug(f"Found {len(caregiver_ids)} caregivers for patient {patient_id}")
        return caregiver_ids
    
    async def get_caregiver_patients(self, caregiver_id: str) -> list:
        """
        Get all active patients for a caregiver.
        
        Args:
            caregiver_id: ID of the caregiver
            
        Returns:
            List of patient user IDs
        """
        cursor = self.collection.find({
            "caregiverId": caregiver_id,
            "status": "active"
        })
        pairings = await cursor.to_list(length=100)
        
        patient_ids = [
            p.get("patientId") 
            for p in pairings 
            if p.get("patientId")
        ]
        
        logger.debug(f"Found {len(patient_ids)} patients for caregiver {caregiver_id}")
        return patient_ids
