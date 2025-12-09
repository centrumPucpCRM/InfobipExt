"""
ConversationExt Router - List and sync operations
"""
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
import logging

logger = logging.getLogger(__name__)

from app.core.dependencies import get_db, verify_token
from app.schemas.conversation_ext import (
    ConversationExt, 
    SyncFromInfobipRequest, 
    SyncFromInfobipResponse,
    ConversationDetailResponse,
    MensajeTimelineItem,
    ProgramaSummary,
    ConversationSummary,
    AsignarVendedorRequest,
    AsignarVendedorResponse,
    ActualizarLeadRequest,
    ActualizarLeadResponse
)
from app.services.conversation_service import ConversationService
from app.services.people_service import PeopleService
from app.services.mensaje_service import MensajeService
from app.schemas.people_ext import PeopleExtCreateFlexible
from app.models.people_ext import PeopleExt
from app.models.rdv_ext import RdvExt

router = APIRouter()


@router.get("/", response_model=List[ConversationExt], dependencies=[Depends(verify_token)])
def list_conversations(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """Retrieve all Conversations with pagination"""
    return ConversationService.get_all(db, skip=skip, limit=limit)


@router.post("/sync-from-infobip", response_model=SyncFromInfobipResponse, dependencies=[Depends(verify_token)])
def sync_conversation_from_infobip(
    data: SyncFromInfobipRequest,
    db: Session = Depends(get_db)
):
    """
    Sincroniza datos de conversación desde Infobip al sistema Ext.
    Siempre inserta un nuevo registro.
    
    - Busca People por infobip_id (personId)
    - Si no existe en BD local, lo crea con infobip_id y telefono (party_id y party_number en blanco)
    - Si viene agentId, busca RDV por infobip_external_id
    - Inserta nuevo registro en conversation_ext
    """
    # 1. Buscar People por infobip_id en BD local
    people = db.query(PeopleExt).filter(PeopleExt.infobip_id == data.personId).first()
    
    # 2. Si no existe en BD local, crear con infobip_id y telefono
    if not people and data.personId:
        people_create = PeopleExtCreateFlexible(
            party_id=None,
            party_number=None,
            telefono=data.telefono,
            infobip_id=data.personId
        )
        people = PeopleService.create_flexible(db=db, people_data=people_create)
    
    id_people = people.id if people else None
    
    # 3. Buscar RDV por infobip_external_id (si viene agentId)
    id_rdv = None
    if data.agentId:
        rdv = db.query(RdvExt).filter(RdvExt.infobip_external_id == data.agentId).first()
        if rdv:
            id_rdv = rdv.id
    
    # 4. Calcular próxima sincronización (ahora + 1 día)
    proxima_sync = datetime.now() + timedelta(days=1)
    
    # 5. Insertar nueva conversación usando el service (estado viene del Lambda)
    nueva_conversacion = ConversationService.create_flexible(
        db=db,
        id_conversation=data.conversationId,
        id_people=id_people,
        id_rdv=id_rdv,
        telefono_creado=data.telefono,
        estado_conversacion=data.estado_conversacion,
        proxima_sincronizacion=proxima_sync
    )
    
    # 5.1 Cerrar conversación anterior del mismo usuario (si existe)
    if id_people:
        # Buscar conversaciones anteriores del mismo id_people (excluyendo la recién creada)
        from app.models.conversation_ext import ConversationExt as ConversationExtModel
        conversacion_anterior = db.query(ConversationExtModel).filter(
            ConversationExtModel.id_people == id_people,
            ConversationExtModel.id != nueva_conversacion.id  # Excluir la recién creada
        ).order_by(ConversationExtModel.created_at.desc()).first()
        
        if conversacion_anterior:
            # Sincronizar mensajes una última vez antes de cerrar
            try:
                MensajeService.sync_mensajes_from_infobip(
                    db=db,
                    id_conversation=conversacion_anterior.id_conversation
                )
            except Exception as e:
                print(f"Error sincronizando mensajes de conversación anterior: {e}")
            
            # Cerrar la conversación anterior
            conversacion_anterior.estado_conversacion = "CLOSED"
            db.commit()
    
    # 6. Sincronizar mensajes y notas desde Infobip
    try:
        total_infobip, nuevos_insertados = MensajeService.sync_mensajes_from_infobip(
            db=db,
            id_conversation=data.conversationId
        )
    except Exception as e:
        print(f"Error sincronizando mensajes: {e}")
        total_infobip = 0
        nuevos_insertados = 0
    
    return SyncFromInfobipResponse(
        success=True,
        message="Conversación registrada y mensajes sincronizados",
        conversation_id=nueva_conversacion.id,
        id_conversation=nueva_conversacion.id_conversation,
        id_people=nueva_conversacion.id_people,
        id_rdv=nueva_conversacion.id_rdv,
        mensajes_total_infobip=total_infobip,
        mensajes_nuevos_insertados=nuevos_insertados
    )


@router.get("/detail", response_model=ConversationDetailResponse, dependencies=[Depends(verify_token)])
def get_conversation_detail(
    id_conversation: Optional[str] = Query(None, description="ID de conversación en Infobip"),
    lead_id: Optional[str] = Query(None, description="Lead ID de Oracle"),
    db: Session = Depends(get_db)
):
    """
    Obtiene el detalle de una conversación con su timeline de mensajes.
    
    Se puede buscar por:
    - id_conversation: ID de conversación en Infobip
    - lead_id: Lead ID de Oracle Sales Cloud
    
    Retorna la conversación con todos sus mensajes ordenados cronológicamente por created_at_infobip.
    """
    if not id_conversation and not lead_id:
        raise HTTPException(
            status_code=400, 
            detail="Debe proporcionar id_conversation o lead_id"
        )
    
    # Buscar la conversación MÁS RECIENTE (por created_at DESC)
    # Ya que puede haber múltiples registros de la misma conversación
    conversation = None
    if id_conversation:
        conversation = ConversationService.get_latest_by_external_id(db, id_conversation)
    elif lead_id:
        conversation = ConversationService.get_latest_by_lead_id(db, lead_id)
    
    if not conversation:
        raise HTTPException(
            status_code=404, 
            detail="Conversación no encontrada"
        )
    
    # Obtener mensajes ordenados cronológicamente
    mensajes = MensajeService.get_by_conversation(db, conversation.id_conversation)
    
    # Construir response
    mensajes_timeline = [
        MensajeTimelineItem(
            id=m.id,
            tipo=m.tipo,
            contenido=m.contenido,
            direccion=m.direccion,
            remitente=m.remitente,
            created_at_infobip=m.created_at_infobip
        )
        for m in mensajes
    ]
    
    # Obtener party_number del People
    people_party_number = None
    if conversation.id_people:
        people = db.query(PeopleExt).filter(PeopleExt.id == conversation.id_people).first()
        if people:
            people_party_number = people.party_number
    
    return ConversationDetailResponse(
        id=conversation.id,
        id_conversation=conversation.id_conversation,
        people_party_number=people_party_number,
        codigo_crm=conversation.codigo_crm,
        lead_id=conversation.lead_id,
        estado_conversacion=conversation.estado_conversacion,
        telefono_creado=conversation.telefono_creado,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        total_mensajes=len(mensajes_timeline),
        mensajes=mensajes_timeline
    )


# ==================== ENDPOINTS ORIENTADOS A PEOPLE (CLIENTE) ====================

@router.get("/people/{party_number}/programs", response_model=List[ProgramaSummary], dependencies=[Depends(verify_token)])
def get_people_programs(
    party_number: int,
    db: Session = Depends(get_db)
):
    """
    Obtiene todos los programas (codigo_crm) en los que participa un cliente específico.
    
    Parámetros:
    - party_number: Party number del cliente (People)
    
    Retorna lista de programas con resumen de actividad.
    """
    # 1. Buscar id_people por party_number
    people = db.query(PeopleExt).filter(PeopleExt.party_number == party_number).first()
    if not people:
        raise HTTPException(status_code=404, detail=f"Cliente con party_number {party_number} no encontrado")
    
    # 2. Obtener TODAS las conversaciones de este id_people
    from app.models.conversation_ext import ConversationExt as ConversationExtModel
    from app.models.mensaje_ext import MensajeExt
    from sqlalchemy import func, desc
    
    conversaciones = db.query(ConversationExtModel).filter(
        ConversationExtModel.id_people == people.id
    ).all()
    
    if not conversaciones:
        return []
    
    # 3. Agrupar por codigo_crm
    programas_dict = {}
    
    for conv in conversaciones:
        codigo_crm = conv.codigo_crm
        if not codigo_crm:
            continue
        
        if codigo_crm not in programas_dict:
            programas_dict[codigo_crm] = {
                "conversaciones": [],
                "lead_ids": set()
            }
        
        programas_dict[codigo_crm]["conversaciones"].append(conv)
        if conv.lead_id:
            programas_dict[codigo_crm]["lead_ids"].add(conv.lead_id)
    
    # 4. Construir response con estadísticas
    programas_response = []
    
    for codigo_crm, data in programas_dict.items():
        conversaciones_programa = data["conversaciones"]
        
        # Contar conversaciones activas
        activas = sum(1 for c in conversaciones_programa if c.estado_conversacion == "ACTIVE")
        
        # Obtener última actividad (último mensaje de cualquier conversación de este programa)
        ultima_actividad = None
        for conv in conversaciones_programa:
            ultimo_mensaje = db.query(MensajeExt).filter(
                MensajeExt.id_conversation == conv.id_conversation
            ).order_by(desc(MensajeExt.created_at_infobip)).first()
            
            if ultimo_mensaje and ultimo_mensaje.created_at_infobip:
                if not ultima_actividad or ultimo_mensaje.created_at_infobip > ultima_actividad:
                    ultima_actividad = ultimo_mensaje.created_at_infobip
        
        programas_response.append(ProgramaSummary(
            codigo_crm=codigo_crm,
            total_conversaciones=len(conversaciones_programa),
            conversaciones_activas=activas,
            ultima_actividad=ultima_actividad,
            lead_ids=list(data["lead_ids"])
        ))
    
    # Ordenar por última actividad (más reciente primero)
    programas_response.sort(key=lambda x: x.ultima_actividad or datetime.min, reverse=True)
    
    return programas_response


@router.get("/people/{party_number}/programs/{codigo_crm}/conversations", response_model=List[ConversationSummary], dependencies=[Depends(verify_token)])
def get_people_program_conversations(
    party_number: int,
    codigo_crm: str,
    db: Session = Depends(get_db)
):
    """
    Obtiene todas las conversaciones de un cliente en un programa específico.
    
    Parámetros:
    - party_number: Party number del cliente (People)
    - codigo_crm: Código del programa CRM
    
    Retorna lista de conversaciones con resumen (sin mensajes).
    """
    # 1. Buscar id_people por party_number
    people = db.query(PeopleExt).filter(PeopleExt.party_number == party_number).first()
    if not people:
        raise HTTPException(status_code=404, detail=f"Cliente con party_number {party_number} no encontrado")
    
    # 2. Buscar conversaciones del cliente en este programa
    from app.models.conversation_ext import ConversationExt as ConversationExtModel
    from app.models.mensaje_ext import MensajeExt
    from sqlalchemy import desc, func
    
    conversaciones = db.query(ConversationExtModel).filter(
        ConversationExtModel.id_people == people.id,
        ConversationExtModel.codigo_crm == codigo_crm
    ).order_by(desc(ConversationExtModel.updated_at)).all()
    
    if not conversaciones:
        return []
    
    # 3. Construir response con resumen de cada conversación
    conversaciones_response = []
    
    for conv in conversaciones:
        # Contar mensajes
        total_mensajes = db.query(func.count(MensajeExt.id)).filter(
            MensajeExt.id_conversation == conv.id_conversation
        ).scalar()
        
        # Obtener último mensaje
        ultimo_mensaje = db.query(MensajeExt).filter(
            MensajeExt.id_conversation == conv.id_conversation
        ).order_by(desc(MensajeExt.created_at_infobip)).first()
        
        ultimo_mensaje_preview = None
        fecha_ultimo_mensaje = None
        
        if ultimo_mensaje:
            # Preview del contenido (primeros 100 caracteres)
            if ultimo_mensaje.contenido:
                ultimo_mensaje_preview = ultimo_mensaje.contenido[:100]
                if len(ultimo_mensaje.contenido) > 100:
                    ultimo_mensaje_preview += "..."
            fecha_ultimo_mensaje = ultimo_mensaje.created_at_infobip
        
        conversaciones_response.append(ConversationSummary(
            id=conv.id,
            id_conversation=conv.id_conversation,
            codigo_crm=conv.codigo_crm,
            lead_id=conv.lead_id,
            estado_conversacion=conv.estado_conversacion,
            telefono_creado=conv.telefono_creado,
            total_mensajes=total_mensajes or 0,
            ultimo_mensaje_preview=ultimo_mensaje_preview,
            fecha_ultimo_mensaje=fecha_ultimo_mensaje,
            created_at=conv.created_at,
            updated_at=conv.updated_at
        ))
    
    return conversaciones_response


@router.get("/lead/{lead_id}/conversations", response_model=List[ConversationSummary], dependencies=[Depends(verify_token)])
def get_lead_conversations(
    lead_id: str,
    db: Session = Depends(get_db)
):
    """
    Obtiene todas las conversaciones vinculadas a un lead_id específico.
    
    Parámetros:
    - lead_id: Lead ID de Oracle Sales Cloud
    
    Retorna lista de conversaciones con resumen (sin mensajes).
    """
    from app.models.conversation_ext import ConversationExt as ConversationExtModel
    from app.models.mensaje_ext import MensajeExt
    from sqlalchemy import func
    
    # Buscar todas las conversaciones con este lead_id
    conversaciones = db.query(ConversationExtModel).filter(
        ConversationExtModel.lead_id == lead_id
    ).order_by(desc(ConversationExtModel.updated_at)).all()
    
    if not conversaciones:
        return []
    
    # Construir response con resumen de cada conversación
    conversaciones_response = []
    
    for conv in conversaciones:
        # Contar mensajes
        total_mensajes = db.query(func.count(MensajeExt.id)).filter(
            MensajeExt.id_conversation == conv.id_conversation
        ).scalar()
        
        # Obtener último mensaje
        ultimo_mensaje = db.query(MensajeExt).filter(
            MensajeExt.id_conversation == conv.id_conversation
        ).order_by(desc(MensajeExt.created_at_infobip)).first()
        
        ultimo_mensaje_preview = None
        fecha_ultimo_mensaje = None
        
        if ultimo_mensaje:
            # Preview del contenido (primeros 100 caracteres)
            if ultimo_mensaje.contenido:
                ultimo_mensaje_preview = ultimo_mensaje.contenido[:100]
                if len(ultimo_mensaje.contenido) > 100:
                    ultimo_mensaje_preview += "..."
            fecha_ultimo_mensaje = ultimo_mensaje.created_at_infobip
        
        conversaciones_response.append(ConversationSummary(
            id=conv.id,
            id_conversation=conv.id_conversation,
            codigo_crm=conv.codigo_crm,
            lead_id=conv.lead_id,
            estado_conversacion=conv.estado_conversacion,
            telefono_creado=conv.telefono_creado,
            total_mensajes=total_mensajes or 0,
            ultimo_mensaje_preview=ultimo_mensaje_preview,
            fecha_ultimo_mensaje=fecha_ultimo_mensaje,
            created_at=conv.created_at,
            updated_at=conv.updated_at
        ))
    
    return conversaciones_response


@router.get("/{id_conversation}/messages", response_model=ConversationDetailResponse, dependencies=[Depends(verify_token)])
def get_conversation_messages(
    id_conversation: str,
    db: Session = Depends(get_db)
):
    """
    Obtiene el detalle completo de una conversación con todos sus mensajes.
    
    Parámetros:
    - id_conversation: ID de conversación en Infobip
    
    Retorna conversación con timeline completo de mensajes ordenados cronológicamente.
    """
    # Buscar la conversación MÁS RECIENTE
    from app.models.conversation_ext import ConversationExt as ConversationExtModel
    conversation = db.query(ConversationExtModel).filter(
        ConversationExtModel.id_conversation == id_conversation
    ).order_by(desc(ConversationExtModel.created_at)).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    
    # Obtener mensajes ordenados cronológicamente
    mensajes = MensajeService.get_by_conversation(db, conversation.id_conversation)
    
    # Construir timeline
    mensajes_timeline = [
        MensajeTimelineItem(
            id=m.id,
            tipo=m.tipo,
            contenido=m.contenido,
            direccion=m.direccion,
            remitente=m.remitente,
            created_at_infobip=m.created_at_infobip
        )
        for m in mensajes
    ]
    
    # Obtener party_number del People
    people_party_number = None
    if conversation.id_people:
        people = db.query(PeopleExt).filter(PeopleExt.id == conversation.id_people).first()
        if people:
            people_party_number = people.party_number
    
    return ConversationDetailResponse(
        id=conversation.id,
        id_conversation=conversation.id_conversation,
        people_party_number=people_party_number,
        codigo_crm=conversation.codigo_crm,
        lead_id=conversation.lead_id,
        estado_conversacion=conversation.estado_conversacion,
        telefono_creado=conversation.telefono_creado,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        total_mensajes=len(mensajes_timeline),
        mensajes=mensajes_timeline
    )


@router.post("/asignar-vendedor", response_model=AsignarVendedorResponse, dependencies=[Depends(verify_token)])
def asignar_vendedor_a_conversacion(
    data: AsignarVendedorRequest,
    db: Session = Depends(get_db)
):
    """
    Asigna un vendedor a una conversación en Infobip.
    
     Proceso:
     1. Sincroniza todos los mensajes y notas de la conversación
     2. Busca en las notas patrones de vendedor ("Vendedor" o "NuevoVendedor")
         y extrae el número que aparece después de ":" (ej: "Vendedor - Andre Zambrano: 123")
     3. Verifica que el vendedor solicitado esté en la lista autorizada
    4. Obtiene el infobip_external_id del vendedor desde RDV
    5. Asigna la conversación al vendedor en Infobip mediante API
    
    Parámetros:
    - id_conversation: ID de la conversación en Infobip
    - party_number_vendedor: Party number del vendedor a asignar
    
    Retorna:
    - success: true/false
    - message: Descripción del resultado
    - vendedores_encontrados: Lista de vendedores autorizados
    - vendedor_asignado: Party number del vendedor asignado (si éxito)
    - infobip_agent_id: Agent ID usado en Infobip (si éxito)
    - mensajes_sincronizados: Cantidad de mensajes nuevos sincronizados
    """
    # Log de los datos recibidos
    logger.info("=" * 80)
    logger.info("📥 ENDPOINT: /asignar-vendedor - Datos recibidos:")
    logger.info(f"   - id_conversation: {data.id_conversation}")
    logger.info(f"   - party_number_vendedor: {data.party_number_vendedor}")
    logger.info(f"   - Data completa: {data.model_dump()}")
    logger.info("=" * 80)
    
    resultado = ConversationService.asignar_vendedor_a_conversacion(
        db=db,
        id_conversation=data.id_conversation,
        party_number_vendedor=data.party_number_vendedor
    )
    
    # Log del resultado
    logger.info(f"📤 RESULTADO de asignar-vendedor:")
    logger.info(f"   - success: {resultado['success']}")
    logger.info(f"   - message: {resultado['message']}")
    logger.info(f"   - vendedores_encontrados: {resultado.get('vendedores_encontrados', [])}")
    logger.info(f"   - vendedor solicitado: {data.party_number_vendedor}")
    
    # Si no tiene éxito, determinar el código de error HTTP apropiado
    if not resultado["success"]:
        message = resultado["message"]
        
        # Vendedor no autorizado según las notas
        if "no está autorizado" in message:
            raise HTTPException(
                status_code=403,
                detail={
                    "message": message,
                    "id_conversation": resultado["id_conversation"],
                    "vendedores_encontrados": resultado["vendedores_encontrados"],
                    "mensajes_sincronizados": resultado.get("mensajes_sincronizados")
                }
            )
        
        # Vendedor no encontrado en base de datos
        elif "No se encontró el vendedor" in message:
            raise HTTPException(
                status_code=404,
                detail={
                    "message": message,
                    "id_conversation": resultado["id_conversation"],
                    "vendedores_encontrados": resultado["vendedores_encontrados"],
                    "mensajes_sincronizados": resultado.get("mensajes_sincronizados")
                }
            )
        
        # Error de configuración (sin infobip_external_id)
        elif "no tiene infobip_external_id" in message:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": message,
                    "id_conversation": resultado["id_conversation"],
                    "vendedores_encontrados": resultado["vendedores_encontrados"],
                    "mensajes_sincronizados": resultado.get("mensajes_sincronizados")
                }
            )
        
        # Error de API de Infobip o inesperado
        else:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": message,
                    "id_conversation": resultado["id_conversation"],
                    "vendedores_encontrados": resultado["vendedores_encontrados"],
                    "mensajes_sincronizados": resultado.get("mensajes_sincronizados")
                }
            )
    
    return AsignarVendedorResponse(**resultado)


@router.post("/actualizar-lead", response_model=ActualizarLeadResponse, dependencies=[Depends(verify_token)])
def actualizar_lead_oracle(
    data: ActualizarLeadRequest,
    db: Session = Depends(get_db)
):
    """
    Actualiza un Lead en Oracle Sales Cloud.
    
    Proceso:
    1. Si viene codigocrm: busca por codigo_crm + id_conversation
    2. Si NO viene codigocrm: busca por id_conversation y valida que haya solo 1 lead_id
    3. Obtiene datos actuales del Lead desde Oracle (GET)
    4. Concatena el comentario nuevo con fecha a los anteriores
    5. Actualiza el Lead en Oracle (PATCH) según la etapa
    
    Body según etapa:
    - Si etapa == "QUALIFIED": actualiza StatusCode
    - Si etapa != "QUALIFIED": actualiza StatusCode a QUALIFIED y agrega Rank con la etapa
    
    Parámetros:
    - etapa: Etapa del lead (QUALIFIED, Poco Prometedora, etc)
    - comentario: Comentario a agregar (se concatena con fecha)
    - codigocrm: Código CRM (opcional, para filtrar búsqueda)
    - id_conversation: ID de conversación en Infobip
    
    Retorna:
    - success: true/false
    - message: Descripción del resultado
    - lead_id: ID del lead actualizado
    - etapa: Etapa aplicada
    - comentario_agregado: Comentario con fecha agregado
    - oracle_response: Respuesta de Oracle
    """
    # Log de los datos recibidos
    logger.info("=" * 80)
    logger.info("📥 ENDPOINT: /actualizar-lead - Datos recibidos:")
    logger.info(f"   - id_conversation: {data.id_conversation}")
    logger.info(f"   - etapa: {data.etapa}")
    logger.info(f"   - comentario: {data.comentario}")
    logger.info(f"   - codigocrm: {data.codigocrm}")
    logger.info("=" * 80)
    
    resultado = ConversationService.actualizar_lead_oracle(
        db=db,
        id_conversation=data.id_conversation,
        etapa=data.etapa,
        comentario=data.comentario,
        codigocrm=data.codigocrm
    )
    
    # Log del resultado
    logger.info(f"📤 RESULTADO de actualizar-lead:")
    logger.info(f"   - success: {resultado['success']}")
    logger.info(f"   - message: {resultado['message']}")
    logger.info(f"   - lead_id: {resultado.get('lead_id')}")
    
    # Si no tiene éxito, determinar el código de error HTTP apropiado
    if not resultado["success"]:
        message = resultado["message"]
        
        # No se encontró conversación o lead
        if "No se encontró" in message or "no tiene lead_id" in message:
            raise HTTPException(
                status_code=404,
                detail={
                    "message": message,
                    "lead_id": resultado.get("lead_id")
                }
            )
        
        # Múltiples leads asociados
        elif "múltiples leads" in message:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": message,
                    "lead_id": resultado.get("lead_id")
                }
            )
        
        # Error de comunicación con Oracle
        elif "Error al comunicarse con Oracle" in message:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": message,
                    "lead_id": resultado.get("lead_id")
                }
            )
        
        # Error inesperado
        else:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": message,
                    "lead_id": resultado.get("lead_id")
                }
            )
    
    return ActualizarLeadResponse(**resultado)
