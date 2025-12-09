"""
PeopleExt Router - List, search and upload operations
"""
import csv
import io
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import get_db, verify_token
from app.schemas.people_ext import PeopleExt, PeopleExtWithRelations, SyncPeopleInfobipResult
from app.services.people_service import PeopleService
from app.models.people_ext import PeopleExt as PeopleExtModel
from app.models.conversation_ext import ConversationExt

router = APIRouter()


@router.get("/", response_model=List[PeopleExt], dependencies=[Depends(verify_token)])
def list_people(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """Retrieve all People with pagination"""
    return PeopleService.get_all(db, skip=skip, limit=limit)


@router.get("/search", response_model=PeopleExtWithRelations, dependencies=[Depends(verify_token)])
def find_people_by_party(
    db: Session = Depends(get_db),
    party_id: Optional[int] = Query(None, description="Party ID to search"),
    party_number: Optional[int] = Query(None, description="Party Number to search"),
    infobip_id: Optional[str] = Query(None, description="Infobip ID to search")
):
    """
    Search People by party_id, party_number or infobip_id.
    Returns People info with ALL RDVs (vendedoras) and ALL conversations.
    """
    if party_id is None and party_number is None and infobip_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one parameter (party_id, party_number or infobip_id) must be provided"
        )
    
    # Query con eager loading de conversaciones y rdv de cada conversación
    query = db.query(PeopleExtModel).options(
        joinedload(PeopleExtModel.conversaciones).joinedload(ConversationExt.rdv)
    )
    
    if party_id:
        people = query.filter(PeopleExtModel.party_id == party_id).first()
    elif party_number:
        people = query.filter(PeopleExtModel.party_number == party_number).first()
    else:
        people = query.filter(PeopleExtModel.infobip_id == infobip_id).first()
    
    if not people:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="People not found"
        )
    
    # El modelo tiene la property rdvs que obtiene los RDVs únicos
    return {
        "id": people.id,
        "party_id": people.party_id,
        "party_number": people.party_number,
        "telefono": people.telefono,
        "created_at": people.created_at,
        "updated_at": people.updated_at,
        "rdvs": people.rdvs,
        "conversaciones": people.conversaciones
    }


@router.post("/upload-csv", dependencies=[Depends(verify_token)])
async def upload_people_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Upload a CSV file to populate people_ext table (bulk insert).
    First removes duplicates from CSV, then inserts all unique people.
    People are unique by party_id + party_number.
    
    Expected CSV columns:
    - cliente.party_id
    - cliente.party_number
    - Telefono-Limpio
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are allowed"
        )
    
    try:
        content = await file.read()
        decoded = content.decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(decoded))
        
        # Preparar registros únicos (por party_id + party_number)
        unique_records = {}
        skipped = 0
        total_rows = 0
        duplicates_in_csv = 0
        
        for row in csv_reader:
            total_rows += 1
            party_id = row.get('cliente.party_id')
            party_number = row.get('cliente.party_number')
            telefono = row.get('Telefono-Limpio')
            
            if not party_id or not party_number or not telefono:
                skipped += 1
                continue
            
            key = (int(party_id), int(party_number))
            if key in unique_records:
                duplicates_in_csv += 1
            else:
                unique_records[key] = {
                    'party_id': int(party_id),
                    'party_number': int(party_number),
                    'telefono': str(telefono).strip()
                }
        
        records_to_insert = list(unique_records.values())
        
        # Bulk insert
        if records_to_insert:
            db.bulk_insert_mappings(PeopleExtModel, records_to_insert)
            db.commit()
        
        return {
            "message": "CSV processed successfully",
            "total_rows_in_csv": total_rows,
            "duplicates_removed": duplicates_in_csv,
            "rows_without_required_fields": skipped,
            "unique_people_inserted": len(records_to_insert)
        }
        
    except Exception as e:
        db.rollback()
        error_msg = str(e)
        if "UNIQUE constraint failed" in error_msg or "duplicate" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Error: Some people already exist in database. party_id + party_number must be unique."
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing CSV: {error_msg}"
        )


@router.post("/sync-people-infobip", response_model=SyncPeopleInfobipResult, dependencies=[Depends(verify_token)])
def sync_people_infobip(db: Session = Depends(get_db)):
    """
    Sincroniza People entre Infobip y la BD local.
    
    Infobip es la fuente de verdad.
    Compara por party_number y sincroniza: party_id, telefono, infobip_id.
    - UPDATE: si alguno de los 3 campos cambió
    - INSERT: si existe en Infobip pero no en local (requiere teléfono)
    
    Este endpoint debe ejecutarse 1 vez al día.
    
    Returns:
        Resumen de la sincronización con estadísticas
    """
    try:
        resultado = PeopleService.sincronizar_telefonos(db)
        return resultado
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en sincronización: {str(e)}"
        )
