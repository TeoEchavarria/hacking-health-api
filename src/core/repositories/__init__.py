"""
Repository interfaces for data access abstraction.

This package defines abstract repository interfaces following the Repository Pattern
and Dependency Inversion Principle (DIP). Concrete implementations are in 
src/infrastructure/repositories.
"""

from .base import BaseRepository
from .user_repository import IUserRepository
from .pairing_repository import IPairingRepository
from .health_repository import IHealthRepository
from .medication_repository import IMedicationRepository

__all__ = [
    "BaseRepository",
    "IUserRepository",
    "IPairingRepository",
    "IHealthRepository",
    "IMedicationRepository",
]
