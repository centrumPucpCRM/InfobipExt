"""
Sales Router - Orchestrated sales processes
"""
from datetime import date
from typing import Dict, Any, Optional, List
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


class SincronizarUltimoRdvRequest(BaseModel):
    """Request para sincronizar la tabla externa 'último RDV por sender'"""
    limit: Optional[int] = Field(None, description="Máximo de pares (telefono_contacto, sender) a procesar en esta corrida (None = todos)", example=500)


@router.post(
    "/sincronizar-ultimo-rdv",
    response_model=Dict[str, Any],
    dependencies=[Depends(verify_token)],
    summary="Sincronizar último RDV por sender",
    description="Crea/actualiza filas en sender-last-rdv a partir de conversation-lead-relation (pares telefono_contacto+sender con su lead_id), resolviendo el RDV vigente del lead."
)
def sincronizar_ultimo_rdv(
    request: SincronizarUltimoRdvRequest = SincronizarUltimoRdvRequest(),
    db: Session = Depends(get_db)
):
    """
    **Sincronizar último RDV por sender**

    Recorre los pares (telefono_contacto, sender) presentes en
    `conversation-lead-relation`, resuelve el RDV vigente a partir del
    `lead_id` y hace UPSERT en `sender-last-rdv` (crea si no existe,
    actualiza si ya existe).
    """
    orchestrator = SalesOrchestrator(db)
    resumen = orchestrator.sincronizar_ultimo_rdv_por_sender(limit=request.limit)
    return {"success": True, **resumen}


class MigrarHistoricoRequest(BaseModel):
    """Request para la migración histórica de conversaciones a Reportería"""
    cutoff_date: date = Field(default=date(2026, 6, 7), description="Fecha de corte (exclusivo): se migran conversaciones anteriores a esta fecha")
    batch_size: int = Field(default=500, ge=1, le=500, description="Tamaño de cada lote enviado a Reportería")
    limit: Optional[int] = Field(None, description="Límite de candidatos a procesar en esta corrida", example=1000)
    exclude_lead_ids: List[str] = Field(default_factory=lambda: ["2033645"], description="Lead IDs a excluir")
    exclude_telefonos: List[str] = Field(default_factory=lambda: ["51960300000"], description="Teléfonos a excluir")


@router.post(
    "/migrar-historico",
    response_model=Dict[str, Any],
    dependencies=[Depends(verify_token)],
    summary="Migración histórica de conversaciones",
    description="Paso 1 del flujo general: envía las conversaciones históricas (pre-corte) a conversation-lead-relation de Reportería, omitiendo las que ya existen."
)
def migrar_historico(
    request: MigrarHistoricoRequest = MigrarHistoricoRequest(),
    db: Session = Depends(get_db)
):
    """
    **Migración histórica de conversaciones**

    Extrae del SQLite local las conversaciones anteriores a `cutoff_date`
    (una por `id_conversation`, la fila más reciente) y las envía en lotes
    al endpoint `conversation-lead-relation` de Reportería.

    Solo envía las que aún no existen (skip-set por `infobip_conversation_id`).
    `sender` siempre se envía como `null` — el sincronizador de reportería
    completa ese campo en el paso 2.
    """
    orchestrator = SalesOrchestrator(db)
    resumen = orchestrator.sincronizar_historico_conversaciones(
        cutoff_date=request.cutoff_date,
        batch_size=request.batch_size,
        limit=request.limit,
        exclude_lead_ids=request.exclude_lead_ids,
        exclude_telefonos=request.exclude_telefonos,
    )
    return {"success": True, **resumen}


class SincronizarGeneralRequest(BaseModel):
    """Request para el sincronizador general (histórico + reportería + último RDV)."""
    cutoff_date: date = Field(default=date(2026, 6, 7), description="Corte histórico para incluir todo el 6-jun y no dejar huecos")
    batch_size: int = Field(default=500, ge=1, le=500, description="Tamaño máximo de cada lote histórico")
    historico_limit: Optional[int] = Field(None, description="Límite de registros históricos a procesar en esta corrida", example=1000)
    reporteria_limit: Optional[int] = Field(None, description="Límite de filas incompletas para el sincronizador de reportería", example=500)
    ultimo_rdv_limit: Optional[int] = Field(None, description="Límite de pares para el sincronizador de último RDV", example=500)
    exclude_lead_ids: List[str] = Field(default_factory=lambda: ["2033645"], description="Leads a excluir del histórico")
    exclude_telefonos: List[str] = Field(default_factory=lambda: ["51960300000"], description="Teléfonos a excluir del histórico")


@router.post(
    "/sincronizar-general",
    response_model=Dict[str, Any],
    dependencies=[Depends(verify_token)],
    summary="Sincronizador general",
    description="Ejecuta histórico, reportería incompleta y último RDV por sender en el orden lógico acordado."
)
def sincronizar_general(
    request: SincronizarGeneralRequest = SincronizarGeneralRequest(),
    db: Session = Depends(get_db)
):
    """
    **Sincronizador general**

    Orden lógico:
    1. Backfill histórico a reportería externa.
    2. Completar filas incompletas de conversation-lead-relation.
    3. Actualizar sender-last-rdv con el último RDV por sender.
    """
    orchestrator = SalesOrchestrator(db)
    resumen = orchestrator.sincronizar_general(
        cutoff_date=request.cutoff_date,
        batch_size=request.batch_size,
        historico_limit=request.historico_limit,
        reporteria_limit=request.reporteria_limit,
        ultimo_rdv_limit=request.ultimo_rdv_limit,
        exclude_lead_ids=request.exclude_lead_ids,
        exclude_telefonos=request.exclude_telefonos,
    )
    return {"success": True, **resumen}
