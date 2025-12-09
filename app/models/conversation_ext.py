"""
Database model for ConversationExt
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.models.base import Base


class ConversationExt(Base):
    """
    ConversationExt model
    """
    __tablename__ = "conversation_ext"
    
    id = Column(Integer, primary_key=True, index=True)
    id_conversation = Column(String, nullable=False, index=True)
    id_people = Column(Integer, ForeignKey("people_ext.id"), nullable=True)
    id_rdv = Column(Integer, ForeignKey("rdv_ext.id"), nullable=True)
    estado_conversacion = Column(String, nullable=True)
    telefono_creado = Column(String, nullable=True, index=True)    
    proxima_sincronizacion = Column(DateTime, nullable=True)
    ultima_sincronizacion = Column(DateTime, nullable=True)
    # Nuevos campos de Oracle Sales Cloud
    codigo_crm = Column(String, nullable=True, index=True)  # Osc.Conversation.codigoCRM
    lead_id = Column(String, nullable=True, index=True)     # Osc.Conversation.LeadId
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    rdv = relationship("RdvExt", back_populates="conversations")
    people = relationship("PeopleExt", back_populates="conversaciones")
    mensajes = relationship(
        "MensajeExt",
        back_populates="conversacion",
        foreign_keys="MensajeExt.id_conversation",
        primaryjoin="ConversationExt.id_conversation == MensajeExt.id_conversation",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self):
        return f"<ConversationExt(id={self.id}, id_conversation='{self.id_conversation}')>"
