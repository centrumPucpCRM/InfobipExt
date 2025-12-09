"""
Database model for RdvExt
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.base import Base


class RdvExt(Base):
    """
    RdvExt (Vendedor/Representante) model.
    Único por party_id.
    """
    __tablename__ = "rdv_ext"
    __table_args__ = (
        UniqueConstraint('party_id', name='uq_rdv_party_id'),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    party_id = Column(Integer, nullable=False, index=True)
    party_number = Column(Integer, nullable=False)
    infobip_external_id = Column(String, nullable=True, index=True)  # ID externo para Infobip
    correo = Column(String, nullable=True)  # Correo electrónico del vendedor
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    conversations = relationship(
        "ConversationExt",
        back_populates="rdv",
        cascade="all, delete-orphan"
    )
    
    @property
    def people(self):
        """Obtener todos los People asociados a través de las conversaciones"""
        seen = set()
        result = []
        for conv in self.conversations:
            if conv.people and conv.people.id not in seen:
                seen.add(conv.people.id)
                result.append(conv.people)
        return result
    
    def __repr__(self):
        return f"<RdvExt(id={self.id}, party_id={self.party_id})>"
