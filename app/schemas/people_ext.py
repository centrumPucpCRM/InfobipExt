"""
Pydantic schemas for PeopleExt
"""
from datetime import datetime
from typing import List
from pydantic import BaseModel, Field, ConfigDict


from typing import Optional


class PeopleExtBase(BaseModel):
    """Base schema for PeopleExt"""
    party_id: int = Field(..., description="Party ID of the person")
    party_number: int = Field(..., description="Party Number")
    telefono: str = Field(..., min_length=1, max_length=20, description="Phone number")


class PeopleExtCreate(PeopleExtBase):
    """Schema for creating a PeopleExt"""
    infobip_id: Optional[str] = Field(None, description="Infobip Person ID")


class PeopleExtCreateFlexible(BaseModel):
    """Schema for creating a PeopleExt with optional party fields (usado en sync)"""
    party_id: Optional[int] = Field(None, description="Party ID of the person")
    party_number: Optional[int] = Field(None, description="Party Number")
    telefono: str = Field(..., min_length=1, max_length=20, description="Phone number")
    infobip_id: Optional[str] = Field(None, description="Infobip Person ID")


class PeopleExt(PeopleExtBase):
    """Schema for PeopleExt response"""
    id: int
    infobip_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Schema simple sin relaciones (para evitar circularidad)
class PeopleExtSimple(BaseModel):
    """Simple schema for PeopleExt (without nested relations)"""
    id: int
    party_id: Optional[int] = None
    party_number: Optional[int] = None
    telefono: str
    infobip_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Import diferido para evitar circularidad
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.schemas.rdv_ext import RdvExtSimple
    from app.schemas.conversation_ext import ConversationExtSimple


class PeopleExtWithRelations(BaseModel):
    """PeopleExt with all RDVs (vendedoras) and all conversations"""
    id: int
    party_id: Optional[int] = None
    party_number: Optional[int] = None
    telefono: str
    infobip_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    rdvs: List["RdvExtSimple"] = []  # Todas las vendedoras asociadas
    conversaciones: List["ConversationExtSimple"] = []  # Todas las conversaciones
    
    model_config = ConfigDict(from_attributes=True)


# Resolver forward references
from app.schemas.rdv_ext import RdvExtSimple
from app.schemas.conversation_ext import ConversationExtSimple
PeopleExtWithRelations.model_rebuild()


class SyncPeopleInfobipResult(BaseModel):
    """Schema for People Infobip sync result"""
    fecha: str = Field(..., description="Fecha y hora de la sincronización")
    duracion_segundos: float = Field(..., description="Duración en segundos")
    total_infobip: int = Field(..., description="Total People en Infobip con party_number")
    total_local: int = Field(..., description="Total People en BD local")
    actualizados: int = Field(..., description="Registros actualizados (party_id, telefono o infobip_id cambió)")
    sin_cambios: int = Field(..., description="Registros sin cambios")
    insertados: int = Field(..., description="Registros nuevos insertados desde Infobip")
    omitidos_sin_telefono: int = Field(..., description="Registros de Infobip omitidos por no tener teléfono")
    no_encontrados_en_infobip: int = Field(..., description="Registros locales no encontrados en Infobip")
    errores: int = Field(..., description="Errores durante la sincronización")
    
    model_config = ConfigDict(from_attributes=True)
