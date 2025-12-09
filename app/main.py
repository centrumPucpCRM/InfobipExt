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

# Configuración de CORS - Solo para IPs autorizadas
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins(),  # Solo orígenes específicos
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
    return {"status": "healthy"}
