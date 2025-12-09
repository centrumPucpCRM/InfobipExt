"""
Database model for MensajeExt
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.models.base import Base


class MensajeExt(Base):
    """
    MensajeExt model - Representa un mensaje o comentario en una conversación.
    Una conversación puede tener muchos mensajes, pero un mensaje solo pertenece a una conversación.
    """
    __tablename__ = "mensaje_ext"
    
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    id_conversation = Column(String, ForeignKey("conversation_ext.id_conversation"), nullable=False, index=True)
    tipo = Column(String, nullable=True, index=True)  # 'MESSAGE', 'NOTE'
    contenido = Column(Text, nullable=True)  # Contenido del mensaje
    direccion = Column(String, nullable=True)  # 'INBOUND', 'OUTBOUND', 'INTERNAL'
    remitente = Column(String, nullable=True)  # Quien envió el mensaje
    infobip_message_id = Column(String, nullable=True, index=True)  # ID del mensaje en Infobip
    created_at_infobip = Column(DateTime, nullable=True, index=True)  # Fecha original de Infobip para ordenar cronológicamente
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    conversacion = relationship(
        "ConversationExt",
        back_populates="mensajes",
        foreign_keys=[id_conversation],
        primaryjoin="MensajeExt.id_conversation == ConversationExt.id_conversation"
    )
    
    def __repr__(self):
        return f"<MensajeExt(id={self.id}, id_conversation='{self.id_conversation}', tipo='{self.tipo}')>"
