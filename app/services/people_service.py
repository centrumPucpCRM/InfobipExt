"""
People Service - Business logic for People operations
"""
from datetime import datetime
from typing import Dict, List, Optional, Any

import requests
from sqlalchemy.orm import Session

from app.models.people_ext import PeopleExt
from app.schemas.people_ext import PeopleExtCreate, PeopleExtCreateFlexible
from app.core.config import settings


class PeopleService:
    """Service for People business logic"""
    
    @staticmethod
    def create(db: Session, people_data: PeopleExtCreate) -> PeopleExt:
        """Create a new People record"""
        db_people = PeopleExt(**people_data.model_dump())
        db.add(db_people)
        db.commit()
        db.refresh(db_people)
        return db_people
    
    @staticmethod
    def create_flexible(db: Session, people_data: PeopleExtCreateFlexible) -> PeopleExt:
        """Create a new People record with optional party fields (usado en sync)"""
        db_people = PeopleExt(**people_data.model_dump())
        db.add(db_people)
        db.commit()
        db.refresh(db_people)
        return db_people
    
    @staticmethod
    def get_by_id(db: Session, people_id: int) -> Optional[PeopleExt]:
        """Get People by ID"""
        return db.query(PeopleExt).filter(PeopleExt.id == people_id).first()
    
    @staticmethod
    def get_by_phone(db: Session, telefono: str) -> Optional[PeopleExt]:
        """Get People by phone number"""
        return db.query(PeopleExt).filter(PeopleExt.telefono == telefono).first()
    
    @staticmethod
    def get_by_party_id(db: Session, party_id: int) -> List[PeopleExt]:
        """Get all People by party_id"""
        return db.query(PeopleExt).filter(PeopleExt.party_id == party_id).all()
    
    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100) -> List[PeopleExt]:
        """List People with pagination"""
        return db.query(PeopleExt).offset(skip).limit(limit).all()
    
    @staticmethod
    def update(db: Session, people_id: int, people_data: PeopleExtCreate) -> Optional[PeopleExt]:
        """Update an existing People record"""
        db_people = PeopleService.get_by_id(db, people_id)
        if not db_people:
            return None
        
        for key, value in people_data.model_dump().items():
            setattr(db_people, key, value)
        
        db.commit()
        db.refresh(db_people)
        return db_people
    
    @staticmethod
    def find_by_party(
        db: Session,
        party_id: Optional[int] = None,
        party_number: Optional[int] = None
    ) -> Optional[PeopleExt]:
        """
        Find People by party_id or party_number.
        At least one parameter must be provided.
        If both are provided, party_id takes precedence.
        """
        if party_id is not None:
            return db.query(PeopleExt).filter(PeopleExt.party_id == party_id).first()
        elif party_number is not None:
            return db.query(PeopleExt).filter(PeopleExt.party_number == party_number).first()
        else:
            return None
    
    @staticmethod
    def delete(db: Session, people_id: int) -> bool:
        """Delete a People record"""
        db_people = PeopleService.get_by_id(db, people_id)
        if not db_people:
            return False
        
        db.delete(db_people)
        db.commit()
        return True

    @staticmethod
    def _obtener_people_infobip() -> List[Dict[str, Any]]:
        """
        Obtiene todos los People de Infobip que tienen party_number en customAttributes.
        Infobip es la fuente de verdad.
        
        Returns:
            Lista de diccionarios con party_number, party_id, telefono, infobip_id
        """
        api_key = settings.INFOBIP_API_KEY
        host = settings.INFOBIP_API_HOST
        
        url = f"https://{host}/people/2/persons"
        headers = {
            "Authorization": f"App {api_key}",
            "Accept": "application/json"
        }
        
        people_infobip = []
        page = 1
        limit = 1000
        max_pages = 1000
        
        while page <= max_pages:
            params = {"limit": limit, "page": page}
            
            try:
                response = requests.get(url, headers=headers, params=params, timeout=60)
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                persons = data.get("persons", [])
                
                if not persons:
                    break
                
                for person in persons:
                    custom_attrs = person.get("customAttributes", {})
                    party_number = custom_attrs.get("party_number") or custom_attrs.get("Party_number")
                    party_id = custom_attrs.get("party_id") or custom_attrs.get("Party_id")
                    infobip_id = person.get("id")  # ID de Infobip
                    
                    if not party_number:
                        continue
                    
                    contact_info = person.get("contactInformation", {})
                    phones = contact_info.get("phone", [])
                    telefono = phones[0].get("number") if phones else None
                    
                    # Incluir aunque no tenga teléfono (para comparación)
                    people_infobip.append({
                        "party_number": str(party_number),
                        "party_id": str(party_id) if party_id else None,
                        "telefono": telefono,
                        "infobip_id": str(infobip_id) if infobip_id else None
                    })
                
                if len(persons) < limit:
                    break
                
                page += 1
                
            except Exception:
                break
        
        return people_infobip

    @staticmethod
    def sincronizar_telefonos(db: Session) -> Dict[str, Any]:
        """
        Sincroniza People entre Infobip y BD local.
        Infobip es la fuente de verdad.
        Match por party_number.
        Compara: party_id, telefono, infobip_id
        
        Returns:
            Resumen de la sincronización
        """
        inicio = datetime.now()
        
        # Obtener datos de Infobip
        people_infobip = PeopleService._obtener_people_infobip()
        
        # Obtener datos locales (solo los campos necesarios)
        people_local = db.query(
            PeopleExt.id,
            PeopleExt.party_number,
            PeopleExt.party_id,
            PeopleExt.telefono,
            PeopleExt.infobip_id
        ).all()
        
        # Crear índice local por party_number
        local_por_party_number = {}
        for row in people_local:
            pn = str(row.party_number) if row.party_number else None
            if pn:
                local_por_party_number[pn] = {
                    "id": row.id,
                    "party_id": str(row.party_id) if row.party_id else None,
                    "telefono": str(row.telefono) if row.telefono else None,
                    "infobip_id": str(row.infobip_id) if row.infobip_id else None
                }
        
        # Crear índice Infobip por party_number
        infobip_por_party_number = {p["party_number"]: p for p in people_infobip}
        
        # Contadores
        actualizados = 0
        sin_cambios = 0
        insertados = 0
        omitidos_sin_telefono = 0
        no_encontrados = 0
        errores = 0
        
        # Listas para batch operations
        updates_batch = []
        inserts_batch = []
        
        # 1. Comparar registros locales con Infobip
        for party_number, local in local_por_party_number.items():
            if party_number not in infobip_por_party_number:
                no_encontrados += 1
                continue
            
            infobip = infobip_por_party_number[party_number]
            
            # Normalizar valores de Infobip para comparación
            inf_party_id = str(infobip["party_id"]) if infobip["party_id"] else None
            inf_telefono = str(infobip["telefono"]) if infobip["telefono"] else None
            inf_infobip_id = str(infobip["infobip_id"]) if infobip["infobip_id"] else None
            
            # Comparar los 3 campos
            cambio = False
            if local["party_id"] != inf_party_id:
                cambio = True
            if local["telefono"] != inf_telefono:
                cambio = True
            if local["infobip_id"] != inf_infobip_id:
                cambio = True
            
            if cambio:
                updates_batch.append({
                    "id": local["id"],
                    "party_id": int(inf_party_id) if inf_party_id else None,
                    "telefono": inf_telefono,
                    "infobip_id": inf_infobip_id
                })
            else:
                sin_cambios += 1
        
        # 2. Buscar registros en Infobip que no existen en local (INSERT)
        for party_number, infobip in infobip_por_party_number.items():
            if party_number not in local_por_party_number:
                # Solo insertar si tiene teléfono
                if infobip["telefono"]:
                    inserts_batch.append({
                        "party_number": int(party_number),
                        "party_id": int(infobip["party_id"]) if infobip["party_id"] else None,
                        "telefono": infobip["telefono"],
                        "infobip_id": infobip["infobip_id"]
                    })
                else:
                    omitidos_sin_telefono += 1
        
        # 3. Ejecutar UPDATEs en batch
        try:
            for update_data in updates_batch:
                db.query(PeopleExt).filter(PeopleExt.id == update_data["id"]).update({
                    PeopleExt.party_id: update_data["party_id"],
                    PeopleExt.telefono: update_data["telefono"],
                    PeopleExt.infobip_id: update_data["infobip_id"]
                })
            db.commit()
            actualizados = len(updates_batch)
        except Exception:
            db.rollback()
            errores += len(updates_batch)
        
        # 4. Ejecutar INSERTs en batch
        try:
            for insert_data in inserts_batch:
                nuevo = PeopleExt(
                    party_number=insert_data["party_number"],
                    party_id=insert_data["party_id"],
                    telefono=insert_data["telefono"],
                    infobip_id=insert_data["infobip_id"]
                )
                db.add(nuevo)
            db.commit()
            insertados = len(inserts_batch)
        except Exception:
            db.rollback()
            errores += len(inserts_batch)
        
        fin = datetime.now()
        duracion = (fin - inicio).total_seconds()
        
        return {
            "fecha": inicio.strftime('%Y-%m-%d %H:%M:%S'),
            "duracion_segundos": round(duracion, 2),
            "total_infobip": len(people_infobip),
            "total_local": len(people_local),
            "actualizados": actualizados,
            "sin_cambios": sin_cambios,
            "insertados": insertados,
            "omitidos_sin_telefono": omitidos_sin_telefono,
            "no_encontrados_en_infobip": no_encontrados,
            "errores": errores
        }
