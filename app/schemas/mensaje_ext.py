"""
Pydantic schemas for MensajeExt
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class MensajeExtBase(BaseModel):
    """Base schema for MensajeExt"""
    id_conversation: str = Field(..., description="ID de la conversación")
    tipo: Optional[str] = Field(None, description="Tipo: MESSAGE, NOTE")
    contenido: Optional[str] = Field(None, description="Contenido del mensaje")
    direccion: Optional[str] = Field(None, description="Dirección: INBOUND, OUTBOUND, INTERNAL")
    remitente: Optional[str] = Field(None, description="Quien envió el mensaje")
    infobip_message_id: Optional[str] = Field(None, description="ID del mensaje en Infobip")
    created_at_infobip: Optional[datetime] = Field(None, description="Fecha original de Infobip para ordenar cronológicamente")


class MensajeExtCreate(MensajeExtBase):
    """Schema for creating a MensajeExt"""
    pass


class MensajeExt(MensajeExtBase):
    """Schema for MensajeExt response"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class MensajeExtSimple(BaseModel):
    """Simple schema for MensajeExt (sin relaciones)"""
    id: int
    id_conversation: str
    tipo: Optional[str] = None
    contenido: Optional[str] = None
    direccion: Optional[str] = None
    remitente: Optional[str] = None
    infobip_message_id: Optional[str] = None
    created_at_infobip: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class MensajeTimeline(BaseModel):
    """Schema para timeline de mensajes (ordenado cronológicamente)"""
    id: int
    tipo: Optional[str] = None
    contenido: Optional[str] = None
    direccion: Optional[str] = None
    remitente: Optional[str] = None
    created_at_infobip: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)
