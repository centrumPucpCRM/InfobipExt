"""
Chat Sync endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_db, verify_token
from app.schemas.chat_sync import ChatSyncRequest, ChatSyncResponse
from app.orchestrators.chat_orchestrator import ChatOrchestrator

router = APIRouter()


@router.post("/sincroniza-chat", response_model=ChatSyncResponse)
async def sincronizar_chat(
    request: ChatSyncRequest,
    db: Session = Depends(get_db),
    token: str = Depends(verify_token)
):
    """
    Sincroniza un chat de Infobip con el sistema RDV
    
    Flujo equivalente a la Lambda original:
    - Determina el teléfono del usuario (cliente)
    - Crea persona en Infobip si no existe
    - Obtiene agentId de la conversación
    - Consulta datos RDV del agente
    - Sincroniza conversación con sistema externo
    """
    try:
        orchestrator = ChatOrchestrator(db)
        
        result = orchestrator.sincronizar_chat(
            telefono_to=request.telefono_to,
            telefono_from=request.telefono_from,
            conversacion=request.conversacion,
            persona=request.persona,
            estado_conversacion=request.estado_conversacion
        )
        
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result.get("message"))
        
        # Convertir person_id a string si es necesario
        if "person_id" in result and result["person_id"] is not None:
            result["person_id"] = str(result["person_id"])
        
        return result  # Devolver dict directamente, FastAPI lo serializa
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en sincronización: {str(e)}")