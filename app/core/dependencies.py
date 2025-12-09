"""
Common dependencies for dependency injection
"""
from typing import Generator
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db as get_database_session

security = HTTPBearer()


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """
    Dependency para verificar el token de autenticación
    """
    token = credentials.credentials
    if token != settings.API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


def get_db() -> Generator[Session, None, None]:
    """
    Dependency to get database session
    """
    db = next(get_database_session())
    try:
        yield db
    finally:
        db.close()
