"""
Health Routes Package.

Modularized health endpoints following Single Responsibility Principle:
- sensor_routes: Sensor data, metrics, patient queries
- sync_routes: Sync requests, HR history
- bp_routes: Blood pressure endpoints
- voice_routes: Voice/audio parsing
- biometrics_routes: Biometrics history
"""
from .sensor_routes import router as sensor_router
from .sync_routes import router as sync_router
from .bp_routes import router as bp_router
from .voice_routes import router as voice_router
from .biometrics_routes import router as biometrics_router

__all__ = [
    "sensor_router",
    "sync_router",
    "bp_router",
    "voice_router",
    "biometrics_router"
]
