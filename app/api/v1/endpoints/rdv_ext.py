"""
RdvExt Router - List, search and sync operations
"""
import http.client
import json
from urllib.parse import quote
from typing import List, Optional
import requests
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_

from app.core.dependencies import get_db, verify_token
from app.core.config import settings
from app.schemas.rdv_ext import RdvExt, RdvExtWithRelations
from app.services.rdv_service import RdvService
from app.models.rdv_ext import RdvExt as RdvExtModel
from app.models.conversation_ext import ConversationExt

router = APIRouter()


@router.get("/", response_model=List[RdvExt], dependencies=[Depends(verify_token)])
def list_rdv(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """Retrieve all RDV with pagination"""
    return RdvService.get_all(db, skip=skip, limit=limit)


@router.get("/search", response_model=RdvExtWithRelations, dependencies=[Depends(verify_token)])
def find_rdv_by_party(
    db: Session = Depends(get_db),
    party_id: Optional[int] = Query(None, description="Party ID to search"),
    party_number: Optional[int] = Query(None, description="Party Number to search"),
    infobip_external_id: Optional[str] = Query(None, description="Infobip External ID to search")
):
    """
    Search RDV by party_id, party_number or infobip_external_id.
    Returns RDV info with all People and all conversations.
    """
    if party_id is None and party_number is None and infobip_external_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one parameter (party_id, party_number or infobip_external_id) must be provided"
        )
    
    # Query con eager loading de conversaciones y people de cada conversación
    query = db.query(RdvExtModel).options(
        joinedload(RdvExtModel.conversations).joinedload(ConversationExt.people)
    )
    
    if party_id:
        rdv = query.filter(RdvExtModel.party_id == party_id).first()
    elif party_number:
        rdv = query.filter(RdvExtModel.party_number == party_number).first()
    else:
        rdv = query.filter(RdvExtModel.infobip_external_id == infobip_external_id).first()
    
    if not rdv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RDV not found"
        )
    
    # El modelo tiene la property people que obtiene los People únicos
    return {
        "id": rdv.id,
        "party_id": rdv.party_id,
        "party_number": rdv.party_number,
        "infobip_external_id": rdv.infobip_external_id,
        "created_at": rdv.created_at,
        "updated_at": rdv.updated_at,
        "people": rdv.people,
        "conversations": rdv.conversations
    }


def sincronizar_rdv(db: Session):
    """
    Sincroniza los RDV con la API de Infobip People.
    
    - Obtiene todos los agentes de Infobip con party_id/party_number
    - Verifica si ya existe por party_id, party_number o infobip_external_id
    - Solo inserta los que no existen (llave compuesta: party_id OR party_number OR external_id)
    - Actualiza el infobip_external_id si el RDV existe pero no tiene external_id
    """
    if not settings.INFOBIP_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INFOBIP_API_KEY no configurada"
        )
    
    # Obtener agentes de Infobip
    try:
        agents = _get_infobip_agents()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error conectando a Infobip: {str(e)}"
        )
    
    inserted = 0
    updated = 0
    skipped = 0
    details = []
    
    for agent in agents:
        party_id = agent.get("party_id")
        party_number = agent.get("party_number")
        external_id = agent.get("external_id")
        nombre = agent.get("nombre")
        correo = agent.get("correo")
        first_name = agent.get("first_name")
        last_name = agent.get("last_name")
        
        if not external_id:
            skipped += 1
            continue
        
        # Convertir a int si es posible
        try:
            party_id_int = int(party_id) if party_id else None
            party_number_int = int(party_number) if party_number else None
        except ValueError:
            skipped += 1
            continue
        
        # Buscar si existe por cualquiera de los 3 campos
        existing = db.query(RdvExtModel).filter(
            or_(
                RdvExtModel.party_id == party_id_int,
                RdvExtModel.party_number == party_number_int,
                RdvExtModel.infobip_external_id == external_id
            )
        ).first()
        
        if existing:
            # Verificar si hay cambios en external_id o correo
            necesita_actualizacion = False
            cambios = []
            
            if not existing.infobip_external_id and external_id:
                existing.infobip_external_id = external_id
                necesita_actualizacion = True
                cambios.append("external_id")
            
            # Actualizar correo si cambió o si no tenía correo
            if correo and existing.correo != correo:
                existing.correo = correo
                necesita_actualizacion = True
                cambios.append("correo")
            # Actualizar nombres si cambiaron
            if first_name and existing.first_name != first_name:
                existing.first_name = first_name
                necesita_actualizacion = True
                cambios.append("first_name")
            if last_name and existing.last_name != last_name:
                existing.last_name = last_name
                necesita_actualizacion = True
                cambios.append("last_name")
            
            if necesita_actualizacion:
                db.add(existing)  # Agregar a la sesión para el commit
                updated += 1
                details.append(f"Actualizado: {nombre} (party_id={party_id}) - Campos: {', '.join(cambios)}")
            else:
                skipped += 1
        else:
            # No existe, insertar nuevo
            new_rdv = RdvExtModel(
                party_id=party_id_int,
                party_number=party_number_int,
                infobip_external_id=external_id,
                correo=correo,
                first_name=first_name,
                last_name=last_name
            )
            db.add(new_rdv)
            inserted += 1
            details.append(f"Insertado: {nombre} (party_id={party_id})")
    
    db.commit()
    
    return {
        "message": "Sincronización completada",
        "total_agents_infobip": len(agents),
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "details": details
    }


def _get_infobip_agents() -> list:
    """Obtener agentes de Infobip People API"""
    conn = http.client.HTTPSConnection(settings.INFOBIP_API_HOST)
    
    headers = {
        "Authorization": f"App {settings.INFOBIP_API_KEY}",
        "Accept": "application/json"
    }
    
    # Filtro: solo personas tipo AGENT
    filtro = {"type": "AGENT"}
    filter_str = quote(json.dumps(filtro))
    
    all_agents = []
    page = 1
    limit = 100
    
    while True:
        path = f"/people/2/persons?limit={limit}&page={page}&filter={filter_str}"
        conn.request("GET", path, headers=headers)
        res = conn.getresponse()
        
        if res.status != 200:
            raise Exception(f"Error {res.status}: {res.reason}")
        
        data = json.loads(res.read())
        persons = data.get("persons", [])
        
        if not persons:
            break
        
        for p in persons:
            custom = p.get("customAttributes", {}) or {}
            
            # Extraer correo de contactInformation.email
            correo = None
            contact_info = p.get("contactInformation", {}) or {}
            emails = contact_info.get("email", [])
            if emails and len(emails) > 0:
                correo = emails[0].get("address")
            # Extraer nombres
            first_name = p.get("firstName")
            last_name = p.get("lastName")
            
            item = {
                "nombre": f"{p.get('firstName', '')} {p.get('lastName', '')}".strip(),
                "external_id": p.get("externalId"),
                "party_id": custom.get("party_id"),
                "party_number": custom.get("party_number"),
                "correo": correo,
                "first_name": first_name,
                "last_name": last_name,
            }
            # Solo agregar si tiene party_id o party_number
            if item["party_id"] or item["party_number"]:
                all_agents.append(item)
        
        page += 1
        
        # Si recibimos menos del límite, ya no hay más páginas
        if len(persons) < limit:
            break
    
    conn.close()
    return all_agents


@router.post("/sincronizar-oracle-infobip", dependencies=[Depends(verify_token)])
def sincronizar_oracle_infobip(db: Session = Depends(get_db)):
    """
    Proceso combinado:
    1) Sincroniza correos desde Oracle hacia Infobip y actualiza BD local
    2) Luego ejecuta la sincronización Infobip -> sistema local (rdv)

    Retorna los resultados de ambos procesos.
    """
    result = {
        "oracle_to_infobip": None,
        "infobip_to_sistemaext": None,
        "errors": []
    }

    # 1) Oracle -> Infobip
    try:
        oracle_res = sincronizar_correos_desde_oracle(db)
        result["oracle_to_infobip"] = oracle_res
    except Exception as e:
        result["errors"].append(f"Oracle->Infobip error: {str(e)}")

    # 2) Infobip -> sistema local (existing sync)
    try:
        infobip_res = sincronizar_rdv(db)
        result["infobip_to_sistemaext"] = infobip_res
    except Exception as e:
        result["errors"].append(f"Infobip->SistemaExt error: {str(e)}")

    # Si no hubieron errores, devolver éxito
    # 3) Push local name changes to Infobip when differ (delegated)
    try:
        push_res = _push_local_names_to_infobip(db)
        result['pushed_names_to_infobip'] = push_res.get('pushed', 0)
        if push_res.get('errors'):
            result.setdefault('errors', []).extend(push_res.get('errors'))
    except Exception as e:
        result.setdefault('errors', []).append(f"PushNames error: {str(e)}")

    return {
        "message": "Proceso combinado ejecutado",
        "result": result
    }


def sincronizar_correos_desde_oracle(db: Session):
    """
    Sincroniza correos desde Oracle hacia Infobip.
    
    - Obtiene todos los agentes de Infobip con party_number
    - Para cada agente, consulta su correo en Oracle CRM (ResourceEmail)
    - Si el correo en Infobip es diferente o no existe, lo actualiza con el de Oracle
    - También actualiza el correo en la BD local (rdv_ext)
    """
    if not settings.INFOBIP_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INFOBIP_API_KEY no configurada"
        )
    
    # Obtener agentes de Infobip
    try:
        agents = _get_infobip_agents()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error conectando a Infobip: {str(e)}"
        )
    
    actualizados_infobip = 0
    actualizados_bd = 0
    skipped = 0
    errores = 0
    details = []
    
    for agent in agents:
        party_number = agent.get("party_number")
        external_id = agent.get("external_id")
        nombre = agent.get("nombre")
        correo_infobip = agent.get("correo")
        first_name = agent.get("first_name")
        last_name = agent.get("last_name")
        
        if not party_number or not external_id:
            skipped += 1
            continue
        
        # 1. Obtener correo desde Oracle
        try:
            correo_oracle = _obtener_correo_desde_oracle(str(party_number))
        except Exception as e:
            details.append(f"Error Oracle: {nombre} (party_number={party_number}) - {str(e)}")
            errores += 1
            continue
        
        if not correo_oracle:
            details.append(f"Sin correo Oracle: {nombre} (party_number={party_number})")
            skipped += 1
            continue
        
        # 2. Verificar si necesita actualización en Infobip
        if correo_infobip and correo_infobip.strip().lower() == correo_oracle.strip().lower():
            # Mismo correo, solo actualizar BD local si es diferente
            try:
                party_number_int = int(party_number)
                rdv = db.query(RdvExtModel).filter(
                    or_(
                        RdvExtModel.party_number == party_number_int,
                        RdvExtModel.infobip_external_id == external_id
                    )
                ).first()
                
                if rdv and rdv.correo != correo_oracle:
                    rdv.correo = correo_oracle
                    # Mantener nombres si vienen desde Infobip
                    if first_name and rdv.first_name != first_name:
                        rdv.first_name = first_name
                    if last_name and rdv.last_name != last_name:
                        rdv.last_name = last_name
                    db.add(rdv)
                    actualizados_bd += 1
                    details.append(f"BD actualizada: {nombre} (party_number={party_number}) - {correo_oracle}")
                else:
                    skipped += 1
            except Exception:
                skipped += 1
            continue
        
        # 3. Actualizar en Infobip
        try:
            success = _actualizar_correo_en_infobip(external_id, correo_oracle)
            if success:
                actualizados_infobip += 1
                details.append(f"Infobip actualizado: {nombre} (party_number={party_number}) - {correo_oracle}")
                
                # 4. Actualizar en BD local
                try:
                    party_number_int = int(party_number)
                    rdv = db.query(RdvExtModel).filter(
                        or_(
                            RdvExtModel.party_number == party_number_int,
                            RdvExtModel.infobip_external_id == external_id
                        )
                    ).first()
                    
                    if rdv:
                        rdv.correo = correo_oracle
                        if first_name and rdv.first_name != first_name:
                            rdv.first_name = first_name
                        if last_name and rdv.last_name != last_name:
                            rdv.last_name = last_name
                        db.add(rdv)
                        actualizados_bd += 1
                except Exception as e:
                    details.append(f"Error BD: {nombre} - {str(e)}")
            else:
                errores += 1
                details.append(f"Error Infobip: {nombre} (party_number={party_number})")
        except Exception as e:
            errores += 1
            details.append(f"Excepción: {nombre} (party_number={party_number}) - {str(e)}")
    
    db.commit()
    
    return {
        "message": "Sincronización de correos desde Oracle completada",
        "total_agents_infobip": len(agents),
        "actualizados_infobip": actualizados_infobip,
        "actualizados_bd": actualizados_bd,
        "skipped": skipped,
        "errores": errores,
        "details": details[:50]  # Limitar a 50 detalles
    }


def _obtener_correo_desde_oracle(party_number: str) -> Optional[str]:
    """
    Consulta Oracle CRM y devuelve ResourceEmail para el party_number dado.
    """
    ORACLE_BASE_URL = f"{settings.ORACLE_CRM_URL}/resourceUsers"
    ORACLE_HEADERS = {
        "Authorization": settings.ORACLE_CRM_AUTH,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    url = f"{ORACLE_BASE_URL}/{party_number}"
    params = {
        "fields": "Username,ResourceEmail",
        "onlyData": "true",
    }
    
    resp = requests.get(url, headers=ORACLE_HEADERS, params=params, timeout=20)
    
    if resp.status_code != 200:
        print(f"[ORACLE] Error {resp.status_code} party_number={party_number}: {resp.text}")
        return None
    
    data = resp.json() or {}
    correo = data.get("ResourceEmail")
    
    if not correo:
        print(f"[ORACLE] Sin ResourceEmail para party_number={party_number}")
    
    return correo


def _actualizar_correo_en_infobip(person_id: str, correo: str) -> bool:
    """
    Actualiza el correo de una persona en Infobip.
    """
    try:
        conn = http.client.HTTPSConnection(settings.INFOBIP_API_HOST)
        
        headers = {
            "Authorization": f"App {settings.INFOBIP_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        body = {
            "contactInformation": {
                "email": [
                    {
                        "address": correo,
                        "isPrimary": True
                    }
                ]
            }
        }
        
        payload = json.dumps(body)
        path = f"/people/2/persons/contactInformation?identifier={person_id}&type=ID"
        
        conn.request("PUT", path, body=payload, headers=headers)
        res = conn.getresponse()
        resp_text = res.read().decode()
        
        if res.status not in [200, 204]:
            print(f"[INFOBIP UPDATE] Error {res.status} person_id={person_id}: {resp_text}")
            return False
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"[INFOBIP UPDATE] Excepción person_id={person_id}: {str(e)}")
        return False


def _actualizar_nombre_en_infobip(person_id: str, first_name: str = None, last_name: str = None) -> bool:
    """
    Actualiza el nombre y apellido de una persona en Infobip.
    """
    try:
        conn = http.client.HTTPSConnection(settings.INFOBIP_API_HOST)
        headers = {
            "Authorization": f"App {settings.INFOBIP_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        body = {}
        if first_name is not None:
            body["firstName"] = first_name
        if last_name is not None:
            body["lastName"] = last_name

        if not body:
            return False

        payload = json.dumps(body)
        path = f"/people/2/persons?identifier={person_id}&type=ID"
        conn.request("PUT", path, body=payload, headers=headers)
        res = conn.getresponse()
        resp_text = res.read().decode()

        if res.status not in [200, 204]:
            print(f"[INFOBIP UPDATE NAME] Error {res.status} person_id={person_id}: {resp_text}")
            return False

        conn.close()
        return True
    except Exception as e:
        print(f"[INFOBIP UPDATE NAME] Excepción person_id={person_id}: {str(e)}")
        return False


def _push_local_names_to_infobip(db: Session) -> dict:
    """
    Recorre los RDV locales con `infobip_external_id` y empuja los cambios
    de `first_name`/`last_name` hacia Infobip cuando difieran.

    Devuelve dict: { 'pushed': int, 'errors': [str,...] }
    """
    pushed = 0
    errors = []
    try:
        agents_current = _get_infobip_agents()
        agents_map = {a.get('external_id'): a for a in agents_current if a.get('external_id')}

        local_rdvs = db.query(RdvExtModel).filter(RdvExtModel.infobip_external_id.isnot(None)).all()
        for rdv in local_rdvs:
            ext = rdv.infobip_external_id
            if not ext:
                continue
            agent = agents_map.get(ext)
            if not agent:
                continue
            inf_first = agent.get('first_name')
            inf_last = agent.get('last_name')
            local_first = rdv.first_name
            local_last = rdv.last_name
            if (local_first and local_first != inf_first) or (local_last and local_last != inf_last):
                ok = _actualizar_nombre_en_infobip(ext, first_name=local_first, last_name=local_last)
                if ok:
                    pushed += 1
                else:
                    errors.append(f"Failed push name for rdv id={rdv.id} ext={ext}")
    except Exception as e:
        errors.append(f"PushNames exception: {str(e)}")

    return { 'pushed': pushed, 'errors': errors }
