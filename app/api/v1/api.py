"""
API Router - Aggregates all v1 routers
"""
from fastapi import APIRouter

from app.api.v1.endpoints import rdv_ext, people_ext, conversation_ext, mensaje_ext, sales, chat_sync

api_router = APIRouter()

# Sales Orchestration
api_router.include_router(sales.router, prefix="/sales", tags=["Sales Orchestration"])

# Chat Synchronization
api_router.include_router(chat_sync.router, prefix="/chat", tags=["Chat Sync"])

# Entity CRUD
api_router.include_router(rdv_ext.router, prefix="/rdv", tags=["RDV"])
api_router.include_router(people_ext.router, prefix="/people", tags=["People"])
api_router.include_router(conversation_ext.router, prefix="/conversations", tags=["Conversations"])
api_router.include_router(mensaje_ext.router, prefix="/messages", tags=["Messages"])
