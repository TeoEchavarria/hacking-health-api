from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.domains.txagent.routes import router as txagent_router
from src.domains.health.routes import router as health_router
from src.domains.auth.routes import router as auth_router
from src.domains.appointments.routes import router as appointments_router
from src.domains.updates.routes import router as updates_router
from src.domains.kitchen.routes import router as kitchen_router
from src.domains.user.routes import user_router, users_router
from src.domains.interests.routes import router as interests_router
from src.domains.pilot.routes import router as pilot_router
from src.domains.sense.routes import router as sense_router
from src.domains.pairing.routes import router as pairing_router
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
    # Create indexes for appointments collection
    database = db.get_db()
    logger = get_logger(__name__)
    try:
        await database.appointments.create_index("datetime")
        await database.appointments.create_index([("datetime", 1), ("status", 1)])
    except Exception as e:
        logger.warning(f"Could not create indexes for appointments: {e}")
    
    # Create indexes for pairings collection
    try:
        await database.pairings.create_index("code")
        await database.pairings.create_index([("code", 1), ("status", 1)])
        await database.pairings.create_index("patientId")
        await database.pairings.create_index("caregiverId")
        await database.pairings.create_index([("status", 1), ("expiresAt", 1)])
    except Exception as e:
        logger.warning(f"Could not create indexes for pairings: {e}")

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
app.include_router(appointments_router)
app.include_router(updates_router)
app.include_router(kitchen_router, prefix="/kitchen", tags=["Kitchen"])
app.include_router(user_router)
app.include_router(users_router)
app.include_router(interests_router)
app.include_router(pilot_router)
app.include_router(sense_router)
app.include_router(pairing_router)

@app.get("/")
async def root():
    return {"message": "Hacking Health API is running"}
