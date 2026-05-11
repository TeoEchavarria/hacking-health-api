from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.domains.txagent.routes import router as txagent_router
from src.domains.health.routes import router as health_router
from src.domains.auth.routes import router as auth_router
from src.domains.updates.routes import router as updates_router
from src.domains.user.routes import user_router, users_router
from src.domains.pairing.routes import router as pairing_router
from src.domains.medications.routes import router as medications_router
from src.domains.notifications.routes import router as notifications_router
from src.domains.location.routes import router as location_router
from src.domains.drawing_challenges.routes import router as drawing_challenges_router
from src.domains.events.routes import router as events_router
from src._config.logger import setup_logging, get_logger
from src.middleware.logging import LoggingMiddleware
from src.core.database import db

# Setup logging
setup_logging()


app = FastAPI(
    title="Hacking Health API",
    description="Backend API for Hacking Health App",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_db_client():
    db.connect()
    database = db.get_db()
    logger = get_logger(__name__)
    
    # Create indexes for pairings collection
    try:
        await database.pairings.create_index("code")
        await database.pairings.create_index([("code", 1), ("status", 1)])
        await database.pairings.create_index("patientId")
        await database.pairings.create_index("caregiverId")
        await database.pairings.create_index([("status", 1), ("expiresAt", 1)])
        # Unique index: only one active pairing per patient+caregiver pair
        await database.pairings.create_index(
            [("patientId", 1), ("caregiverId", 1)],
            unique=True,
            partialFilterExpression={"status": "active", "caregiverId": {"$ne": None}}
        )
    except Exception as e:
        logger.warning(f"Could not create indexes for pairings: {e}")
    
    # Create indexes for health_metrics collection
    try:
        await database.health_metrics.create_index("userId")
        await database.health_metrics.create_index([("userId", 1), ("type", 1)])
        await database.health_metrics.create_index([("userId", 1), ("timestamp", -1)])
        await database.health_metrics.create_index("timestamp")
    except Exception as e:
        logger.warning(f"Could not create indexes for health_metrics: {e}")
    
    # Create indexes for medications collection
    try:
        await database.medications.create_index("userId")
        await database.medications.create_index([("userId", 1), ("isActive", 1)])
        await database.medications.create_index([("userId", 1), ("time", 1)])
    except Exception as e:
        logger.warning(f"Could not create indexes for medications: {e}")
    
    # Create indexes for medication_takes collection
    try:
        await database.medication_takes.create_index("userId")
        await database.medication_takes.create_index("medicationId")
        await database.medication_takes.create_index([("userId", 1), ("date", 1)])
        await database.medication_takes.create_index([("medicationId", 1), ("date", 1)])
        await database.medication_takes.create_index("date")
    except Exception as e:
        logger.warning(f"Could not create indexes for medication_takes: {e}")
    
    # Create indexes for notifications collection
    try:
        await database.notifications.create_index("userId")
        await database.notifications.create_index([("userId", 1), ("type", 1)])
        await database.notifications.create_index([("userId", 1), ("isRead", 1)])
        await database.notifications.create_index([("userId", 1), ("timestamp", -1)])
        await database.notifications.create_index("timestamp")
    except Exception as e:
        logger.warning(f"Could not create indexes for notifications: {e}")
    
    # Create indexes for health_tips collection
    try:
        await database.health_tips.create_index("userId")
        await database.health_tips.create_index([("userId", 1), ("category", 1)])
        await database.health_tips.create_index([("userId", 1), ("isActive", 1)])
    except Exception as e:
        logger.warning(f"Could not create indexes for health_tips: {e}")
    
    # Create indexes for locations collection (history)
    try:
        await database.locations.create_index("userId")
        await database.locations.create_index([("userId", 1), ("createdAt", -1)])
        await database.locations.create_index("createdAt")
        # TTL index: auto-delete locations older than 7 days
        await database.locations.create_index(
            "createdAt",
            expireAfterSeconds=7 * 24 * 60 * 60  # 7 days
        )
    except Exception as e:
        logger.warning(f"Could not create indexes for locations: {e}")
    
    # Create geospatial index for users.lastLocation (GeoJSON Point)
    try:
        await database.users.create_index([("lastLocation", "2dsphere")])
        logger.info("Created 2dsphere index on users.lastLocation")
    except Exception as e:
        logger.warning(f"Could not create 2dsphere index for users.lastLocation: {e}")
    
    # Create indexes for blood_pressure_readings collection
    try:
        await database.blood_pressure_readings.create_index("userId")
        await database.blood_pressure_readings.create_index([("userId", 1), ("timestamp", -1)])
        await database.blood_pressure_readings.create_index([("userId", 1), ("date", 1)])
        await database.blood_pressure_readings.create_index("timestamp")
        await database.blood_pressure_readings.create_index([("userId", 1), ("stage", 1)])
    except Exception as e:
        logger.warning(f"Could not create indexes for blood_pressure_readings: {e}")
    
    # Create indexes for bp_cusum_state collection (CUSUM drift detection state)
    try:
        await database.bp_cusum_state.create_index("userId", unique=True)
    except Exception as e:
        logger.warning(f"Could not create indexes for bp_cusum_state: {e}")
    
    # Create indexes for alerts collection
    try:
        await database.alerts.create_index("patient_id")
        await database.alerts.create_index([("patient_id", 1), ("type", 1)])
        await database.alerts.create_index([("patient_id", 1), ("status", 1)])
        await database.alerts.create_index([("patient_id", 1), ("created_at_iso", -1)])
        await database.alerts.create_index("severity")
    except Exception as e:
        logger.warning(f"Could not create indexes for alerts: {e}")
    
    # Create indexes for biometric_events collection
    try:
        await database.biometric_events.create_index([("patientId", 1), ("recordedAt", -1)])
        await database.biometric_events.create_index([("caregiverId", 1), ("recordedAt", -1)])
        await database.biometric_events.create_index([("patientId", 1), ("readByPatient", 1)])
        await database.biometric_events.create_index([("caregiverId", 1), ("readByCaregiver", 1)])
        # TTL index: auto-delete events older than 30 days
        await database.biometric_events.create_index(
            "createdAt",
            expireAfterSeconds=30 * 24 * 60 * 60  # 30 days
        )
    except Exception as e:
        logger.warning(f"Could not create indexes for biometric_events: {e}")
    
    # NOTE: Pairing cleanup code removed - was deleting active connections on every deployment
    # If you need to clean up test data, do it manually via MongoDB console

@app.on_event("shutdown")
async def shutdown_db_client():
    db.close()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Logging Middleware
app.add_middleware(LoggingMiddleware)

# Include routers
app.include_router(txagent_router)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(updates_router)
app.include_router(user_router)
app.include_router(users_router)
app.include_router(pairing_router)
app.include_router(medications_router)
app.include_router(notifications_router)
app.include_router(location_router)
app.include_router(drawing_challenges_router)
app.include_router(events_router)

@app.get("/")
async def root():
    return {"message": "Hacking Health API is running"}
