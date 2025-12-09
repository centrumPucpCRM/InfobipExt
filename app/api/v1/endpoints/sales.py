"""
Sales Router - Orchestrated sales processes
"""
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.dependencies import get_db, verify_token
from app.orchestrators.sales_orchestrator import SalesOrchestrator

router = APIRouter()


# Request Models
class ActiveSaleRequest(BaseModel):
    """Request para venta activa - Datos de Oracle Sales Cloud"""
    osc_people_dni: str = Field(..., description="Osc.People.DNI (obligatorio)", example="72923744")
    osc_people_party_id: Optional[int] = Field(None, description="Osc.People.PartyId", example=300000061580828)
    osc_people_party_number: Optional[int] = Field(None, description="Osc.People.PartyNumber", example=827482)
    osc_people_telefono: Optional[str] = Field(None, description="Osc.People.telefóno", example="51900020023")
    osc_rdv_party_id: Optional[int] = Field(None, description="Osc.RdvExt.PartyId", example=300000004123456)
    osc_rdv_party_number: Optional[int] = Field(None, description="Osc.RdvExt.PartyNumber", example=4123456)
    osc_conversation_codigo_crm: Optional[str] = Field(None, description="Osc.Conversation.codigoCRM", example="CRM-2024-001")
    osc_conversation_lead_id: Optional[str] = Field(None, description="Osc.Conversation.LeadId", example="LEAD-12345")
    osc_conversation_id: Optional[str] = Field(None, description="Osc.Conversation.Id - ID de conversación existente en Infobip (opcional)", example="abc123-def456")


@router.post(
    "/active",
    response_model=Dict[str, Any],
    dependencies=[Depends(verify_token)],
    summary="Flujo Venta Activa",
    description="Flujo de venta activa (usuario comienza conversación) - Recibe datos de Oracle Sales Cloud"
)
def flujo_venta_activa(
    request: ActiveSaleRequest,
    db: Session = Depends(get_db)
):
    """
    **Flujo de venta activa** - Usuario comienza conversación
    
    Recibe datos de Oracle Sales Cloud:
    - Osc.People.DNI (obligatorio)
    - Osc.People.PartyId, Osc.People.PartyNumber, Osc.People.telefóno
    - Osc.RdvExt.PartyId, Osc.RdvExt.PartyNumber
    - Osc.Conversation.codigoCRM, Osc.Conversation.LeadId
    - Osc.Conversation.Id (opcional) - Si se proporciona, usa conversación existente en lugar de crear nueva
    """
    orchestrator = SalesOrchestrator(db)
    return orchestrator.flujo_venta_activa(
        osc_people_dni=request.osc_people_dni,
        osc_people_party_id=request.osc_people_party_id,
        osc_people_party_number=request.osc_people_party_number,
        osc_people_telefono=request.osc_people_telefono,
        osc_rdv_party_id=request.osc_rdv_party_id,
        osc_rdv_party_number=request.osc_rdv_party_number,
        osc_conversation_codigo_crm=request.osc_conversation_codigo_crm,
        osc_conversation_lead_id=request.osc_conversation_lead_id,
        osc_conversation_id=request.osc_conversation_id
    )


@router.post(
    "/passive",
    response_model=Dict[str, Any],
    dependencies=[Depends(verify_token)],
    summary="Flujo Venta Pasiva",
    description="Flujo de venta pasiva - Se trabaja netamente en Infobip"
)
def flujo_venta_pasiva(
    db: Session = Depends(get_db)
):
    """
    **Flujo de venta pasiva** - Responsable comienza conversación
    
    Se trabaja netamente en Infobip, no hay lógica backend.
    """
    orchestrator = SalesOrchestrator(db)
    return orchestrator.flujo_venta_pasiva()
