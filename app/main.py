"""
Main FastAPI Application
"""
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1.api import api_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.DESCRIPTION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Configuración de CORS - Leer orígenes desde .env (via `ALLOWED_ORIGINS`)
# Si en el .env pones un único origen "*" se permitirá cualquier origen.
raw_allowed = [o.strip() for o in settings.get_allowed_origins() if o and o.strip()]
if any(o == "*" for o in raw_allowed):
    allow_origins = ["*"]
else:
    allow_origins = raw_allowed

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Incluir routers
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
async def root():
    """Root endpoint - No requiere autenticación"""
    return {
        "message": "InfobipExt API",
        "version": settings.VERSION,
        "docs": "/docs",
        "authentication": "Required - Use Bearer Token"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint - No requiere autenticación"""
    return {"status": "healthy", "message": "Soy el health de la version dockerizada 2.0"}
