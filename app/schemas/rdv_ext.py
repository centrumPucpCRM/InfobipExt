"""
Pydantic schemas for RdvExt
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class RdvExtBase(BaseModel):
    """Base schema for RdvExt"""
    party_id: int = Field(..., description="Party ID")
    party_number: int = Field(..., description="Party Number")
    infobip_external_id: Optional[str] = Field(None, description="External ID for Infobip")
    correo: Optional[str] = Field(None, description="Correo electrónico")
    first_name: Optional[str] = Field(None, description="First name from Infobip")
    last_name: Optional[str] = Field(None, description="Last name from Infobip")


class RdvExtCreate(RdvExtBase):
    """Schema for creating a RdvExt"""
    pass


class RdvExt(RdvExtBase):
    """Schema for RdvExt response"""
    id: int
    infobip_external_id: Optional[str] = None
    correo: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Schema simple sin relaciones (para evitar circularidad)
class RdvExtSimple(BaseModel):
    """Simple schema for RdvExt (without nested relations)"""
    id: int
    party_id: int
    party_number: int
    infobip_external_id: Optional[str] = None
    correo: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Import diferido para evitar circularidad
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.schemas.conversation_ext import ConversationExtSimple
    from app.schemas.people_ext import PeopleExtSimple


class RdvExtWithRelations(BaseModel):
    """RdvExt with people and conversations"""
    id: int
    party_id: int
    party_number: int
    infobip_external_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    people: List["PeopleExtSimple"] = []  # Todas las personas asociadas
    conversations: List["ConversationExtSimple"] = []  # Todas las conversaciones
    
    model_config = ConfigDict(from_attributes=True)


# Resolver forward references
from app.schemas.conversation_ext import ConversationExtSimple
from app.schemas.people_ext import PeopleExtSimple
RdvExtWithRelations.model_rebuild()
