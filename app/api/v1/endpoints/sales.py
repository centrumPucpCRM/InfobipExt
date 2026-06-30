"""
Sales Router - Orchestrated sales processes
"""
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.dependencies import get_db, verify_token
from app.orchestrators.sales_orchestrator import SalesOrchestrator
from app.services.rdv_service import RdvService

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


class VincularLeadRequest(BaseModel):
    """Request para vincular un lead con una conversación"""
    lead_id: str = Field(..., description="LeadId del lead en Oracle", example="300000123456789")
    conversation_id: str = Field(..., description="ID de la conversación en Infobip", example="abc123-def456-ghi789")
    nota: Optional[str] = Field(None, description="Nota opcional para agregar a la conversación", example="Lead sincronizado desde CRM")


@router.post(
    "/vincular-lead",
    response_model=Dict[str, Any],
    dependencies=[Depends(verify_token)],
    summary="Vincular Lead con Conversación",
    description="Actualiza el campo CTRIdConversacionInfobip_c del lead en Oracle con el ID de conversación de Infobip"
)
def vincular_lead_conversation(
    request: VincularLeadRequest,
    db: Session = Depends(get_db)
):
    """
    **Vincular Lead con Conversación**
    
    Actualiza el lead en Oracle Sales Cloud con el ID de conversación de Infobip.
    
    - **lead_id**: LeadId del lead en Oracle (ej: 300000123456789)
    - **conversation_id**: ID de la conversación en Infobip
    - **nota**: (Opcional) Nota a agregar a la conversación
    """
    orchestrator = SalesOrchestrator(db)
    resultado = orchestrator._vincular_lead_conversation_id(
        lead_id=request.lead_id,
        conversation_id=request.conversation_id
    )
    
    nota_agregada = False
    if resultado and request.nota:
        nota_agregada = orchestrator._agregar_nota_conversacion(
            conversation_id=request.conversation_id,
            nota=f"Lead sincronizado: {request.nota}"
        )
    
    return {
        "success": resultado,
        "lead_id": request.lead_id,
        "conversation_id": request.conversation_id,
        "nota_agregada": nota_agregada,
        "message": "Lead vinculado exitosamente" if resultado else "Error al vincular lead"
    }


class ReasignarAgenteRequest(BaseModel):
    """Request para reasignar una conversación al vendedor (RDV) en Infobip"""
    conversation_id: str = Field(..., description="ID de la conversación en Infobip", example="abc123-def456-ghi789")
    party_number: int = Field(..., description="Party Number del vendedor (RDV) en Oracle. Se traduce a su infobip_external_id (agentId)", example=4123456)


@router.post(
    "/reasignar-agente",
    response_model=Dict[str, Any],
    dependencies=[Depends(verify_token)],
    summary="Reasignar Conversación a Vendedor",
    description="Asigna/reasigna una conversación de Infobip al vendedor (RDV) indicado por su party_number. Traduce party_number -> infobip_external_id y usa PUT /ccaas/1/conversations/{id}/assignee"
)
def reasignar_agente(
    request: ReasignarAgenteRequest,
    db: Session = Depends(get_db)
):
    """
    **Reasignar Conversación a Vendedor (RDV)**

    Asigna una conversación de Infobip al vendedor indicado por su `party_number`.

    Pasos:
    1. Busca el RDV en `rdv_ext` por `party_number`.
    2. Obtiene su `infobip_external_id` (el `agentId` que entiende Infobip).
    3. Reasigna la conversación vía `PUT /ccaas/1/conversations/{id}/assignee`.

    - **conversation_id**: ID de la conversación en Infobip
    - **party_number**: Party Number del vendedor (RDV) en Oracle
    """
    rdv = RdvService.find_by_party(db=db, party_number=request.party_number)

    if not rdv:
        return {
            "success": False,
            "conversation_id": request.conversation_id,
            "party_number": request.party_number,
            "agente_external_id": None,
            "message": f"No se encontró un RDV con party_number={request.party_number}"
        }

    agente_external_id = rdv.infobip_external_id

    if not agente_external_id:
        return {
            "success": False,
            "conversation_id": request.conversation_id,
            "party_number": request.party_number,
            "agente_external_id": None,
            "message": f"El RDV con party_number={request.party_number} no tiene infobip_external_id configurado"
        }

    orchestrator = SalesOrchestrator(db)
    resultado = orchestrator._reasignar_conversacion_infobip(
        conversation_id=request.conversation_id,
        agente_external_id=agente_external_id
    )

    # Si la reasignación fue exitosa, actualizar el "último RDV por sender" en la
    # reportería externa (best-effort; no afecta la respuesta de este endpoint).
    if resultado:
        orchestrator._registrar_ultimo_rdv_por_sender_desde_conversacion(
            conversation_id=request.conversation_id,
            party_number=request.party_number,
        )

    return {
        "success": resultado,
        "conversation_id": request.conversation_id,
        "party_number": request.party_number,
        "agente_external_id": agente_external_id,
        "message": "Conversación reasignada exitosamente" if resultado else "Error al reasignar conversación"
    }


class SincronizarReporteriaRequest(BaseModel):
    """Request para sincronizar la reportería externa (conversation-lead-relation)"""
    limit: Optional[int] = Field(None, description="Máximo de filas incompletas a procesar en esta corrida (None = todas)", example=500)


@router.post(
    "/sincronizar-reporteria",
    response_model=Dict[str, Any],
    dependencies=[Depends(verify_token)],
    summary="Sincronizar reportería externa",
    description="Rellena telefono_contacto y sender en las filas incompletas de conversation-lead-relation, usando datos locales y la cartera del lead (Oracle)."
)
def sincronizar_reporteria(
    request: SincronizarReporteriaRequest = SincronizarReporteriaRequest(),
    db: Session = Depends(get_db)
):
    """
    **Sincronizar reportería externa**

    Recorre las filas de `conversation-lead-relation` que están incompletas
    (sin `telefono_contacto` y/o sin `sender`) y las completa:
    - `telefono_contacto`: desde `conversation_ext` local (por `infobip_conversation_id`).
    - `sender`: del `telefono_creado` compuesto local, o de la cartera del lead
      (`CTRTipoDeCarteraLead_c`) mapeada a número Infobip.

    Best-effort: las carteras no mapeadas se omiten y se reportan en la respuesta.
    """
    orchestrator = SalesOrchestrator(db)
    resumen = orchestrator.sincronizar_reporteria(limit=request.limit)
    return {"success": True, **resumen}
