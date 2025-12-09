"""
Configuration settings for the application
"""
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""
    
    # API Settings
    PROJECT_NAME: str = "InfobipExt API"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "API para gestión de RDV, People y Conversations con autenticación por token"
    API_V1_STR: str = "/api/v1"
    
    # CORS - Cambiado a str para evitar problemas con .env
    ALLOWED_ORIGINS: str = "http://localhost,http://localhost:3000,http://localhost:8000"
    
    def get_allowed_origins(self) -> List[str]:
        """Convierte el string de ALLOWED_ORIGINS a una lista."""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]
    
    # Database
    DATABASE_URL: str = "sqlite:///./infobip.db"
    
    # Security - Token de autenticación
    API_TOKEN: str
    
    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    
    # Infobip API
    INFOBIP_API_KEY: str = "your-infobip-api-key"
    INFOBIP_API_HOST: str = "your-infobip-host"
    
    # Oracle Sales Cloud API
    ORACLE_CRM_URL: str = "your-oracle-crm-url"
    ORACLE_CRM_AUTH: str = "your-oracle-auth"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
