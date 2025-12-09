"""
Pydantic schemas for ConversationExt
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class ConversationExtBase(BaseModel):
    """Base schema for ConversationExt"""
    id_conversation: str = Field(..., description="Conversation ID") #ok
    id_people: Optional[int] = Field(None, description="People ID reference") #ok
    id_rdv: Optional[int] = Field(None, description="RDV ID reference")
    estado_conversacion: Optional[str] = Field(None, description="Conversation state")
    telefono_creado: Optional[str] = Field(None, description="Teléfono con el que se creó la conversación") #ok
    proxima_sincronizacion: Optional[datetime] = Field(None, description="Next synchronization")
    ultima_sincronizacion: Optional[datetime] = Field(None, description="Last synchronization")
    # Nuevos campos de Oracle Sales Cloud
    codigo_crm: Optional[str] = Field(None, description="Oracle Sales Cloud - Codigo CRM")
    lead_id: Optional[str] = Field(None, description="Oracle Sales Cloud - Lead ID")


class ConversationExtCreate(ConversationExtBase):
    """Schema for creating a ConversationExt"""
    pass


class ConversationExt(ConversationExtBase):
    """Schema for ConversationExt response"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Schema simple sin relaciones (para evitar circularidad)
class ConversationExtSimple(BaseModel):
    """Simple schema for ConversationExt (without nested relations)"""
    id: int
    id_conversation: str
    id_people: Optional[int] = None
    id_rdv: Optional[int] = None
    estado_conversacion: Optional[str] = None
    telefono_creado: Optional[str] = None
    proxima_sincronizacion: Optional[datetime] = None
    ultima_sincronizacion: Optional[datetime] = None
    codigo_crm: Optional[str] = None
    lead_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Schemas para sincronización desde Infobip
class SyncFromInfobipRequest(BaseModel):
    """Schema para sincronizar datos de conversación desde Infobip"""
    telefono: str = Field(..., description="Teléfono con el que se creó la conversación")
    conversationId: str = Field(..., description="ID de la conversación en Infobip")
    personId: str = Field(..., description="ID del People en Infobip (infobip_id)")
    agentId: Optional[str] = Field(None, description="ID del agente en Infobip (infobip_external_id)")
    estado_conversacion: Optional[str] = Field(None, description="Estado de la conversación desde Lambda")


class SyncFromInfobipResponse(BaseModel):
    """Schema de respuesta de sincronización desde Infobip"""
    success: bool
    message: str
    conversation_id: Optional[int] = None
    id_conversation: Optional[str] = None
    id_people: Optional[int] = None
    id_rdv: Optional[int] = None
    # Mensajes sincronizados
    mensajes_total_infobip: Optional[int] = Field(None, description="Total mensajes/notas en Infobip")
    mensajes_nuevos_insertados: Optional[int] = Field(None, description="Nuevos mensajes insertados")


# Schema flexible para creación genérica (solo id_conversation es obligatorio)
class ConversationExtCreateFlexible(BaseModel):
    """Schema flexible para crear conversación - solo id_conversation es obligatorio"""
    id_conversation: str = Field(..., description="ID de conversación en Infobip (obligatorio)")
    id_people: Optional[int] = Field(None, description="ID del People en BD local")
    id_rdv: Optional[int] = Field(None, description="ID del RDV en BD local")
    estado_conversacion: Optional[str] = Field(None, description="Estado de la conversación")
    telefono_creado: Optional[str] = Field(None, description="Teléfono con el que se creó")
    proxima_sincronizacion: Optional[datetime] = Field(None, description="Próxima sincronización")
    ultima_sincronizacion: Optional[datetime] = Field(None, description="Última sincronización")
    codigo_crm: Optional[str] = Field(None, description="Código CRM de Oracle")
    lead_id: Optional[str] = Field(None, description="Lead ID de Oracle")


# Schema para detalle de conversación con timeline de mensajes
class MensajeTimelineItem(BaseModel):
    """Item del timeline de mensajes"""
    id: int
    tipo: Optional[str] = None
    contenido: Optional[str] = None
    direccion: Optional[str] = None
    remitente: Optional[str] = None
    created_at_infobip: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


# Schemas para endpoints orientados a People (cliente)
class ProgramaSummary(BaseModel):
    """Resumen de un programa (codigo_crm) para un cliente específico"""
    codigo_crm: str = Field(..., description="Código del programa CRM")
    total_conversaciones: int = Field(..., description="Total de conversaciones en este programa")
    conversaciones_activas: int = Field(..., description="Conversaciones en estado ACTIVE")
    ultima_actividad: Optional[datetime] = Field(None, description="Fecha del último mensaje/actualización")
    lead_ids: List[str] = Field(default_factory=list, description="Lead IDs asociados")


class ConversationSummary(BaseModel):
    """Resumen de una conversación (sin mensajes)"""
    id: int
    id_conversation: str
    codigo_crm: Optional[str] = None
    lead_id: Optional[str] = None
    estado_conversacion: Optional[str] = None
    telefono_creado: Optional[str] = None
    total_mensajes: int = 0
    ultimo_mensaje_preview: Optional[str] = Field(None, description="Preview del último mensaje")
    fecha_ultimo_mensaje: Optional[datetime] = Field(None, description="Fecha del último mensaje")
    created_at: datetime
    updated_at: datetime


class ConversationDetailResponse(BaseModel):
    """Schema de respuesta con detalle completo de conversación y mensajes"""
    # Datos de la conversación
    id: int
    id_conversation: str
    people_party_number: Optional[int] = Field(None, description="Party number del People")
    codigo_crm: Optional[str] = None
    lead_id: Optional[str] = None
    estado_conversacion: Optional[str] = None
    telefono_creado: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # Timeline de mensajes ordenado cronológicamente
    total_mensajes: int
    mensajes: List[MensajeTimelineItem] = []
    
    model_config = ConfigDict(from_attributes=True)


# Schema para asignación de vendedor
class AsignarVendedorRequest(BaseModel):
    """Schema para asignar vendedor a conversación"""
    id_conversation: str = Field(..., description="ID de conversación en Infobip")
    party_number_vendedor: int = Field(..., description="Party number del vendedor que se quiere asignar")


class AsignarVendedorResponse(BaseModel):
    """Schema de respuesta de asignación de vendedor"""
    success: bool
    message: str
    id_conversation: str
    vendedores_encontrados: List[int] = Field(default_factory=list, description="Party numbers de vendedores encontrados en notas")
    vendedor_asignado: Optional[int] = None
    infobip_agent_id: Optional[str] = None
    mensajes_sincronizados: Optional[int] = None


# Schema para actualización de Lead en Oracle
class ActualizarLeadRequest(BaseModel):
    """Schema para actualizar Lead en Oracle Sales Cloud"""
    etapa: str = Field(..., description="Etapa del lead (ej: QUALIFIED, Poco Prometedora, etc)")
    comentario: str = Field(default="", description="Comentario a agregar al lead")
    codigocrm: str = Field(default="", description="Código CRM (opcional, si se proporciona se usa para buscar el lead)")
    id_conversation: str = Field(..., description="ID de conversación en Infobip")


class ActualizarLeadResponse(BaseModel):
    """Schema de respuesta de actualización de Lead"""
    success: bool
    message: str
    lead_id: Optional[str] = None
    etapa: Optional[str] = None
    comentario_agregado: Optional[str] = None
    oracle_response: Optional[dict] = None
