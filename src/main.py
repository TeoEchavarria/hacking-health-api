from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.domains.txagent.routes import router as txagent_router
from src.domains.health.routes import router as health_router
from src.domains.auth.routes import router as auth_router
from src._config.logger import setup_logging
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

@app.get("/")
async def root():
    return {"message": "Hacking Health API is running"}
