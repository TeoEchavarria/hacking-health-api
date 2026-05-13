"""
Health Routes - Main Router.

Combines all health-related routes following Single Responsibility Principle:
- Sensor data and metrics
- Sync requests
- Blood pressure
- Voice/audio parsing
- Biometrics history

The monolithic 845-line routes file has been split into 5 specialized modules
in the route_modules/ directory, each with a clear, focused responsibility.

This file now serves as a composition root, combining all sub-routers.
"""
from fastapi import APIRouter
from src.domains.health.route_modules.sensor_routes import router as sensor_router
from src.domains.health.route_modules.sync_routes import router as sync_router
from src.domains.health.route_modules.bp_routes import router as bp_router
from src.domains.health.route_modules.voice_routes import router as voice_router
from src.domains.health.route_modules.biometrics_routes import router as biometrics_router

# Main router with shared prefix and tags
router = APIRouter(
    prefix="/health",
    tags=["health"]
)

# Include all sub-routers
router.include_router(sensor_router)
router.include_router(sync_router)
router.include_router(bp_router)
router.include_router(voice_router)
router.include_router(biometrics_router)


