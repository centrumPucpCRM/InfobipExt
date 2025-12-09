"""
Schemas para sincronización de chat
"""
from pydantic import BaseModel
from typing import Optional


class ChatSyncRequest(BaseModel):
    """Schema para la request de sincronización de chat"""
    telefono_to: str
    telefono_from: str
    conversacion: str
    persona: Optional[str] = None
    estado_conversacion: str = "OPEN"


class ChatSyncResponse(BaseModel):
    """Schema para la response de sincronización de chat"""
    telefono: str
    conversationId: str
    person_id: Optional[str] = None
    agentId: Optional[str] = None
    rdv: Optional[dict] = None
    syncResult: Optional[dict] = None
    status: str = "success"
    message: Optional[str] = None