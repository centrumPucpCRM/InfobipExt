"""
MensajeExt Router - List and sync operations for messages
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_db, verify_token
from app.schemas.mensaje_ext import MensajeExt, MensajeExtSimple
from app.services.mensaje_service import MensajeService
from pydantic import BaseModel, Field


router = APIRouter()


class SyncMensajesRequest(BaseModel):
    """Request para sincronizar mensajes de una conversación"""
    id_conversation: str = Field(..., description="ID de conversación en Infobip")


class SyncMensajesResponse(BaseModel):
    """Response de sincronización de mensajes"""
    success: bool
    message: str
    id_conversation: str
    total_from_infobip: int
    nuevos_insertados: int
    total_en_bd: int


@router.get("/", response_model=List[MensajeExtSimple], dependencies=[Depends(verify_token)])
def list_mensajes(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """Retrieve all Mensajes with pagination"""
    return MensajeService.get_all(db, skip=skip, limit=limit)


@router.get("/by-conversation/{id_conversation}", response_model=List[MensajeExtSimple], dependencies=[Depends(verify_token)])
def get_mensajes_by_conversation(
    id_conversation: str,
    db: Session = Depends(get_db)
):
    """Get all mensajes for a specific conversation ID"""
    mensajes = MensajeService.get_by_conversation(db, id_conversation)
    return mensajes


@router.get("/{mensaje_id}", response_model=MensajeExtSimple, dependencies=[Depends(verify_token)])
def get_mensaje(
    mensaje_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific mensaje by ID"""
    mensaje = MensajeService.get_by_id(db, mensaje_id)
    if not mensaje:
        raise HTTPException(status_code=404, detail="Mensaje not found")
    return mensaje


@router.post("/sync", response_model=SyncMensajesResponse, dependencies=[Depends(verify_token)])
def sync_mensajes_from_infobip(
    data: SyncMensajesRequest,
    db: Session = Depends(get_db)
):
    """
    Sincroniza mensajes y notas desde Infobip para una conversación específica.
    
    - Obtiene todos los mensajes y notas de la API de Infobip
    - Verifica cuáles ya existen en BD local (por infobip_message_id)
    - Inserta solo los nuevos registros
    """
    try:
        total_from_infobip, nuevos_insertados = MensajeService.sync_mensajes_from_infobip(
            db=db,
            id_conversation=data.id_conversation
        )
        
        total_en_bd = MensajeService.count_by_conversation(db, data.id_conversation)
        
        return SyncMensajesResponse(
            success=True,
            message=f"Sincronización completada: {nuevos_insertados} nuevos mensajes insertados",
            id_conversation=data.id_conversation,
            total_from_infobip=total_from_infobip,
            nuevos_insertados=nuevos_insertados,
            total_en_bd=total_en_bd
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sincronizando mensajes: {str(e)}")


@router.delete("/{mensaje_id}", dependencies=[Depends(verify_token)])
def delete_mensaje(
    mensaje_id: int,
    db: Session = Depends(get_db)
):
    """Delete a specific mensaje"""
    deleted = MensajeService.delete(db, mensaje_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Mensaje not found")
    return {"success": True, "message": "Mensaje deleted"}
