"""
Database model for PeopleExt
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.base import Base


class PeopleExt(Base):
    """
    PeopleExt model - Representa una persona/cliente.
    Único por party_id + party_number.
    """
    __tablename__ = "people_ext"
    __table_args__ = (
        UniqueConstraint('party_id', 'party_number', name='uq_people_party'),
    )
    
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    party_id = Column(Integer, nullable=True, index=True)
    party_number = Column(Integer, nullable=True, index=True)
    telefono = Column(String, nullable=False, index=True)
    infobip_id = Column(String, nullable=True, index=True)  # ID del People en Infobip
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    conversaciones = relationship(
        "ConversationExt",
        back_populates="people",
        cascade="all, delete-orphan"
    )
    
    @property
    def rdvs(self):
        """Obtener todos los RDVs asociados a través de las conversaciones"""
        seen = set()
        result = []
        for conv in self.conversaciones:
            if conv.rdv and conv.rdv.id not in seen:
                seen.add(conv.rdv.id)
                result.append(conv.rdv)
        return result
    
    def __repr__(self):
        return f"<PeopleExt(id={self.id}, party_id={self.party_id}, telefono='{self.telefono}')>"
