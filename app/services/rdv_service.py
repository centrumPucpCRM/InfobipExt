"""
RDV Service - Business logic for RDV operations
"""
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.rdv_ext import RdvExt
from app.schemas.rdv_ext import RdvExtCreate


class RdvService:
    """Service for RDV business logic"""
    
    @staticmethod
    def create(db: Session, rdv_data: RdvExtCreate) -> RdvExt:
        """Create a new RDV"""
        db_rdv = RdvExt(**rdv_data.model_dump())
        db.add(db_rdv)
        db.commit()
        db.refresh(db_rdv)
        return db_rdv
    
    @staticmethod
    def get_by_id(db: Session, rdv_id: int) -> Optional[RdvExt]:
        """Get RDV by ID"""
        return db.query(RdvExt).filter(RdvExt.id == rdv_id).first()
    
    @staticmethod
    def get_by_party_id(db: Session, party_id: int) -> Optional[RdvExt]:
        """Get RDV by party_id"""
        return db.query(RdvExt).filter(RdvExt.party_id == party_id).first()
    
    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100) -> List[RdvExt]:
        """List RDVs with pagination"""
        return db.query(RdvExt).offset(skip).limit(limit).all()
    
    @staticmethod
    def update(db: Session, rdv_id: int, rdv_data: RdvExtCreate) -> Optional[RdvExt]:
        """Update an existing RDV"""
        db_rdv = RdvService.get_by_id(db, rdv_id)
        if not db_rdv:
            return None
        
        for key, value in rdv_data.model_dump().items():
            setattr(db_rdv, key, value)
        
        db.commit()
        db.refresh(db_rdv)
        return db_rdv
    
    @staticmethod
    def find_by_party(
        db: Session,
        party_id: Optional[int] = None,
        party_number: Optional[int] = None
    ) -> Optional[RdvExt]:
        """
        Find RDV by party_id or party_number.
        At least one parameter must be provided.
        If both are provided, party_id takes precedence.
        """
        if party_id is not None:
            return db.query(RdvExt).filter(RdvExt.party_id == party_id).first()
        elif party_number is not None:
            return db.query(RdvExt).filter(RdvExt.party_number == party_number).first()
        else:
            return None
    
    @staticmethod
    def find_by_infobip_external_id(db: Session, external_id: str) -> Optional[RdvExt]:
        """Find RDV by infobip_external_id"""
        return db.query(RdvExt).filter(RdvExt.infobip_external_id == external_id).first()
    
    @staticmethod
    def delete(db: Session, rdv_id: int) -> bool:
        """Delete an RDV"""
        db_rdv = RdvService.get_by_id(db, rdv_id)
        if not db_rdv:
            return False
        
        db.delete(db_rdv)
        db.commit()
        return True
