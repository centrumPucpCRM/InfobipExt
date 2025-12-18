"""
Conversation Service - Business logic for Conversation operations
"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.conversation_ext import ConversationExt
from app.schemas.conversation_ext import ConversationExtCreate


class ConversationService:
    """Service for Conversation business logic"""
    
    @staticmethod
    def create(db: Session, conversation_data: ConversationExtCreate) -> ConversationExt:
        """Create a new Conversation"""
        db_conversation = ConversationExt(**conversation_data.model_dump())
        db.add(db_conversation)
        db.commit()
        db.refresh(db_conversation)
        return db_conversation
    
    @staticmethod
    def create_flexible(
        db: Session,
        id_conversation: str,
        id_people: Optional[int] = None,
        id_rdv: Optional[int] = None,
        estado_conversacion: Optional[str] = None,
        telefono_creado: Optional[str] = None,
        proxima_sincronizacion = None,
        ultima_sincronizacion = None,
        codigo_crm: Optional[str] = None,
        lead_id: Optional[str] = None
    ) -> ConversationExt:
        """
        Crea una conversación con campos flexibles.
        Solo id_conversation es obligatorio, los demás son opcionales.
        Siempre inserta un nuevo registro.
        """
        db_conversation = ConversationExt(
            id_conversation=id_conversation,
            id_people=id_people,
            id_rdv=id_rdv,
            estado_conversacion=estado_conversacion,
            telefono_creado=telefono_creado,
            proxima_sincronizacion=proxima_sincronizacion,
            ultima_sincronizacion=ultima_sincronizacion,
            codigo_crm=codigo_crm,
            lead_id=lead_id
        )
        db.add(db_conversation)
        db.commit()
        db.refresh(db_conversation)
        return db_conversation
    
    @staticmethod
    def get_by_id(db: Session, conversation_id: int) -> Optional[ConversationExt]:
        """Get Conversation by ID"""
        return db.query(ConversationExt).filter(ConversationExt.id == conversation_id).first()
    
    @staticmethod
    def get_by_external_id(db: Session, id_conversation: str) -> Optional[ConversationExt]:
        """Get Conversation by external conversation ID"""
        return db.query(ConversationExt).filter(ConversationExt.id_conversation == id_conversation).first()
    
    @staticmethod
    def get_by_lead_id(db: Session, lead_id: str) -> Optional[ConversationExt]:
        """Get Conversation by Oracle Lead ID"""
        return db.query(ConversationExt).filter(ConversationExt.lead_id == lead_id).first()
    
    @staticmethod
    def get_latest_by_external_id(db: Session, id_conversation: str) -> Optional[ConversationExt]:
        """Get the most recent Conversation by external conversation ID (ordered by created_at DESC)"""
        return db.query(ConversationExt).filter(
            ConversationExt.id_conversation == id_conversation
        ).order_by(ConversationExt.created_at.desc()).first()
    
    @staticmethod
    def get_latest_by_lead_id(db: Session, lead_id: str) -> Optional[ConversationExt]:
        """Get the most recent Conversation by Oracle Lead ID (ordered by created_at DESC)"""
        return db.query(ConversationExt).filter(
            ConversationExt.lead_id == lead_id
        ).order_by(ConversationExt.created_at.desc()).first()
    
    @staticmethod
    def get_by_people(db: Session, id_people: int) -> List[ConversationExt]:
        """Get all Conversations for a specific People"""
        return db.query(ConversationExt).filter(ConversationExt.id_people == id_people).all()
    
    @staticmethod
    def get_by_rdv(db: Session, id_rdv: int) -> List[ConversationExt]:
        """Get all Conversations for a specific RDV"""
        return db.query(ConversationExt).filter(ConversationExt.id_rdv == id_rdv).all()
    
    @staticmethod
    def get_active(db: Session) -> List[ConversationExt]:
        """Get all active Conversations"""
        return db.query(ConversationExt).filter(ConversationExt.estado_conversacion == "activo").all()
    
    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100) -> List[ConversationExt]:
        """List Conversations with pagination"""
        return db.query(ConversationExt).offset(skip).limit(limit).all()
    
    @staticmethod
    def update(db: Session, conversation_id: int, conversation_data: ConversationExtCreate) -> Optional[ConversationExt]:
        """Update an existing Conversation"""
        db_conversation = ConversationService.get_by_id(db, conversation_id)
        if not db_conversation:
            return None
        
        for key, value in conversation_data.model_dump().items():
            setattr(db_conversation, key, value)
        
        db.commit()
        db.refresh(db_conversation)
        return db_conversation
    
    @staticmethod
    def update_status(db: Session, conversation_id: int, estado: str) -> Optional[ConversationExt]:
        """Update Conversation status"""
        db_conversation = ConversationService.get_by_id(db, conversation_id)
        if not db_conversation:
            return None
        
        db_conversation.estado_conversacion = estado
        db.commit()
        db.refresh(db_conversation)
        return db_conversation
    
    @staticmethod
    def delete(db: Session, conversation_id: int) -> bool:
        """Delete a Conversation"""
        db_conversation = ConversationService.get_by_id(db, conversation_id)
        if not db_conversation:
            return False
        
        db.delete(db_conversation)
        db.commit()
        return True
    
    @staticmethod
    def asignar_vendedor_a_conversacion(
        db: Session,
        id_conversation: str,
        party_number_vendedor: int
    ) -> dict:
        """
        Asigna un vendedor a una conversación en Infobip.
        
          Pasos:
          1. Sincroniza mensajes de la conversación
          2. Busca en las notas patrones de vendedor ("Vendedor" o "NuevoVendedor")
              y extrae el número que aparece después de ":" (ej: "Vendedor - Nombre: 123")
          3. Verifica que el vendedor esté en la lista
          4. Obtiene el infobip_external_id del vendedor
          5. Asigna la conversación al vendedor en Infobip
        
        Returns:
            dict con success, message, vendedores_encontrados, etc.
        """
        import httpx
        import re
        from app.services.mensaje_service import MensajeService
        from app.services.rdv_service import RdvService
        from app.core.config import settings
        from app.models.rdv_ext import RdvExt
        
        # 1. Sincronizar mensajes
        total_infobip, nuevos_insertados = MensajeService.sync_mensajes_from_infobip(
            db=db,
            id_conversation=id_conversation
        )
        
        # 2. Obtener todas las notas (mensajes tipo NOTE)
        from app.models.mensaje_ext import MensajeExt
        notas = db.query(MensajeExt).filter(
            MensajeExt.id_conversation == id_conversation,
            MensajeExt.tipo == "NOTE"
        ).all()
        
        # 3. Extraer vendedores de las notas.
        # Soporta formatos como:
        # - "Vendedor - Nombre Apellido: 123"
        # - "Vendedor:123"
        # - "NuevoVendedor Nombre: 123"
        # - "NuevoVendedor: 123"
        vendedores_encontrados = []
        patron = r"(?:NuevoVendedor|Vendedor)\s*(?:-?\s*[^:]+)?\s*:\s*(\d+)"

        for nota in notas:
            if nota.contenido:
                matches = re.findall(patron, nota.contenido)
                for match in matches:
                    try:
                        party_number = int(match)
                    except Exception:
                        continue
                    if party_number not in vendedores_encontrados:
                        vendedores_encontrados.append(party_number)
        
        # 4. Verificar que el vendedor esté en la lista
        if party_number_vendedor not in vendedores_encontrados:
            return {
                "success": False,
                "message": f"El vendedor {party_number_vendedor} no está autorizado para esta conversación",
                "id_conversation": id_conversation,
                "vendedores_encontrados": vendedores_encontrados,
                "mensajes_sincronizados": nuevos_insertados
            }
        
        # 5. Obtener el RDV (vendedor) por party_number
        rdv = db.query(RdvExt).filter(RdvExt.party_number == party_number_vendedor).first()
        
        if not rdv:
            return {
                "success": False,
                "message": f"No se encontró el vendedor con party_number {party_number_vendedor} en la base de datos",
                "id_conversation": id_conversation,
                "vendedores_encontrados": vendedores_encontrados,
                "mensajes_sincronizados": nuevos_insertados
            }
        
        if not rdv.infobip_external_id:
            return {
                "success": False,
                "message": f"El vendedor {party_number_vendedor} no tiene infobip_external_id configurado",
                "id_conversation": id_conversation,
                "vendedores_encontrados": vendedores_encontrados,
                "mensajes_sincronizados": nuevos_insertados
            }
        
        # 6. Asignar conversación al vendedor en Infobip
        url = f"https://{settings.INFOBIP_API_HOST}/ccaas/1/conversations/{id_conversation}/assignee"
        headers = {
            "Authorization": f"App {settings.INFOBIP_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "agentId": rdv.infobip_external_id
        }
        
        try:
            with httpx.Client() as client:
                # Asignar conversación al vendedor
                response = client.put(url, headers=headers, json=payload, timeout=30.0)
                response.raise_for_status()
                
                # 7. Agregar nota a la conversación informando el cambio de vendedor
                # Obtener el vendedor anterior (si existe)
                conversation_record = db.query(ConversationExt).filter(
                    ConversationExt.id_conversation == id_conversation
                ).order_by(ConversationExt.created_at.desc()).first()
                
                vendedor_anterior = None
                nombre_vendedor_anterior = None
                if conversation_record and conversation_record.id_rdv:
                    rdv_anterior = db.query(RdvExt).filter(RdvExt.id == conversation_record.id_rdv).first()
                    if rdv_anterior:
                        vendedor_anterior = rdv_anterior.party_number
                        fn_a = getattr(rdv_anterior, 'first_name', None)
                        ln_a = getattr(rdv_anterior, 'last_name', None)
                        if fn_a or ln_a:
                            nombre_vendedor_anterior = f"{fn_a or ''} {ln_a or ''}".strip()

                # Obtener nombre del vendedor nuevo (rdv obtenido arriba)
                nombre_vendedor_nuevo = None
                fn_n = getattr(rdv, 'first_name', None)
                ln_n = getattr(rdv, 'last_name', None)
                if fn_n or ln_n:
                    nombre_vendedor_nuevo = f"{fn_n or ''} {ln_n or ''}".strip()

                # Construir las cadenas a mostrar (nombre si existe, si no party_number)
                display_prev = nombre_vendedor_anterior if nombre_vendedor_anterior else (str(vendedor_anterior) if vendedor_anterior else None)
                display_new = nombre_vendedor_nuevo if nombre_vendedor_nuevo else str(party_number_vendedor)

                # Crear mensaje de la nota usando nombres cuando estén disponibles
                if vendedor_anterior and vendedor_anterior != party_number_vendedor:
                    nota_texto = (
                        f"Conversación reasignada del vendedor {display_prev} ({vendedor_anterior}) "
                        f"al vendedor {display_new} ({party_number_vendedor}) por solicitud del vendedor {display_new}."
                    )
                else:
                    nota_texto = (
                        f"Conversación asignada al vendedor {display_new} ({party_number_vendedor}) "
                        f"por solicitud del vendedor {display_new}."
                    )
                
                # Enviar nota a Infobip
                url_nota = f"https://{settings.INFOBIP_API_HOST}/ccaas/1/conversations/{id_conversation}/notes"
                payload_nota = {
                    "content": nota_texto
                }
                
                response_nota = client.post(url_nota, headers=headers, json=payload_nota, timeout=30.0)
                response_nota.raise_for_status()
                
                # Actualizar id_rdv en el registro de conversación más reciente
                if conversation_record:
                    conversation_record.id_rdv = rdv.id
                    db.commit()
                
            return {
                "success": True,
                "message": f"Conversación asignada exitosamente al vendedor {party_number_vendedor}",
                "id_conversation": id_conversation,
                "vendedores_encontrados": vendedores_encontrados,
                "vendedor_asignado": party_number_vendedor,
                "infobip_agent_id": rdv.infobip_external_id,
                "mensajes_sincronizados": nuevos_insertados
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "message": f"Error al asignar conversación en Infobip: {e.response.status_code} - {e.response.text}",
                "id_conversation": id_conversation,
                "vendedores_encontrados": vendedores_encontrados,
                "mensajes_sincronizados": nuevos_insertados
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error inesperado: {str(e)}",
                "id_conversation": id_conversation,
                "vendedores_encontrados": vendedores_encontrados,
                "mensajes_sincronizados": nuevos_insertados
            }
    
    @staticmethod
    def actualizar_lead_oracle(
        db: Session,
        id_conversation: str,
        etapa: str,
        comentario: str = "",
        codigocrm: str = ""
    ) -> dict:
        """
        Actualiza un Lead en Oracle Sales Cloud.
        
        Pasos:
        1. Busca el lead_id según codigocrm o id_conversation
        2. Obtiene datos actuales del Lead desde Oracle (GET)
        3. Concatena el comentario nuevo con los anteriores
        4. Actualiza el Lead en Oracle (PATCH)
        
        Returns:
            dict con success, message, lead_id, etc.
        """
        import httpx
        from datetime import datetime
        from app.core.config import settings
        from app.models.conversation_ext import ConversationExt as ConversationExtModel
        
        # 1. Determinar el lead_id
        lead_id = None
        
        if codigocrm:
            # Buscar por codigo_crm + id_conversation
            conversation = db.query(ConversationExtModel).filter(
                ConversationExtModel.codigo_crm == codigocrm,
                ConversationExtModel.id_conversation == id_conversation
            ).first()
            
            if not conversation:
                return {
                    "success": False,
                    "message": f"No se encontró conversación con codigo_crm '{codigocrm}' y id_conversation '{id_conversation}'"
                }
            
            lead_id = conversation.lead_id
            
            if not lead_id:
                return {
                    "success": False,
                    "message": f"La conversación encontrada no tiene lead_id asociado"
                }
        else:
            # Si no se pasó codigocrm, primero intentar extraer códigos de programa
            # desde las notas de la conversación (mensajes tipo NOTE). Esto permite
            # detectar si hay múltiples programas en las notas y evitar actualizar
            # el lead en caso de ambigüedad.
            from app.models.mensaje_ext import MensajeExt
            import re

            programas_encontrados = []
            try:
                notas = db.query(MensajeExt).filter(
                    MensajeExt.id_conversation == id_conversation,
                    MensajeExt.tipo == "NOTE"
                ).all()
                # Dni Cliente: 7737373
                # Codigo programa: 46546465 
                # Nombre Programa: NOmbre XYZ
                #->46546465
                patron = re.compile(r"Codigo\s+programa\s*:\s*([^\r\n]+)", re.IGNORECASE)

                

                for nota in notas:
                    if not nota.contenido:
                        continue
                    # Buscar todas las apariciones dentro de la nota
                    for m in patron.findall(nota.contenido):
                        # m es una tupla con hasta 4 grupos; escoger el primero no vacío
                        codigo = None
                        for grp in m:
                            if grp:
                                codigo = grp.strip()
                                break
                        if codigo:
                            if codigo not in programas_encontrados:
                                programas_encontrados.append(codigo)
            except Exception:
                programas_encontrados = []

            # Si encontramos más de un código en las notas -> error de ambigüedad
            if len(programas_encontrados) > 1:
                return {
                    "success": False,
                    "message": f"Se encontraron múltiples programas en las notas: {programas_encontrados}",
                    "lead_id": None
                }

            # Si exactamente uno fue encontrado en notas, usarlo como codigocrm
            if len(programas_encontrados) == 1:
                codigocrm = programas_encontrados[0]

            # Buscar por id_conversation y validar que solo haya 1 lead_id
            conversaciones = db.query(ConversationExtModel).filter(
                ConversationExtModel.id_conversation == id_conversation
            ).all()
            
            if not conversaciones:
                return {
                    "success": False,
                    "message": f"No se encontraron conversaciones con id_conversation '{id_conversation}'"
                }
            
            # Obtener lead_ids únicos (no nulos)
            lead_ids = list(set([c.lead_id for c in conversaciones if c.lead_id]))
            
            if len(lead_ids) == 0:
                return {
                    "success": False,
                    "message": "No se encontró lead_id asociado a la conversación"
                }
            
            if len(lead_ids) > 1:
                return {
                    "success": False,
                    "message": f"Se encontraron múltiples leads asociados a la conversación: {lead_ids}"
                }
            
            lead_id = lead_ids[0]
        
        # 2. Obtener datos actuales del Lead desde Oracle
        url_get = f"{settings.ORACLE_CRM_URL}/leads/"
        headers = {
            "Authorization": settings.ORACLE_CRM_AUTH,
            "Content-Type": "application/json"
        }
        params_get = {
            "onlyData": "true",
            "q": f"LeadNumber={lead_id}",
            "fields": "CTRObservacionesActiv_c,StatusCode,LeadId"
        }
        
        try:
            with httpx.Client() as client:
                # GET para obtener observaciones actuales
                response_get = client.get(url_get, headers=headers, params=params_get, timeout=30.0)
                response_get.raise_for_status()
                lead_data = response_get.json()
                print("lead_data",lead_data)
                # Obtener observaciones anteriores
                observaciones_anteriores = lead_data.get("CTRObservacionesActiv_c", "") or ""
                # If the lead is already converted, post a note in Infobip (best-effort)
                if lead_data.get("StatusCode", "") == 'CONVERTED':
                    try:
                        nota_text = (
                            "No se pudo actualizar el lead porque ya fue convertido previamente en el CRM. "
                        )
                        url_nota = f"https://{settings.INFOBIP_API_HOST}/ccaas/1/conversations/{id_conversation}/notes"
                        payload_nota = {"content": nota_text}
                        headers_infobip = {
                            "Authorization": f"App {settings.INFOBIP_API_KEY}",
                            "Content-Type": "application/json",
                            "Accept": "application/json"
                        }
                        try:
                            client.post(url_nota, headers=headers_infobip, json=payload_nota, timeout=10.0)
                        except Exception as e:
                            print("Error:",e)
                    except Exception as e:
                        print("Error:",e)

                    return {
                        "success": False,
                        "message": f"No se puede actualizar el lead {lead_id}: ya está convertido",
                        "lead_id": lead_id
                    }
                # 3. Construir nuevo comentario con fecha
                fecha_actual = datetime.now().strftime("%d.%m.%Y")
                nuevo_comentario = f"{fecha_actual} - {comentario}" if comentario else ""
                
                # Concatenar comentarios
                if observaciones_anteriores and nuevo_comentario:
                    observaciones_finales = f"|{observaciones_anteriores} \n|{nuevo_comentario}"
                elif nuevo_comentario:
                    observaciones_finales = nuevo_comentario
                else:
                    observaciones_finales = observaciones_anteriores
                
                # 4. Construir body del PATCH según la etapa
                if etapa == "QUALIFIED":
                    body = {
                        "StatusCode": etapa,
                        "CTRActividades_c": "Contacto vIa Mail",
                        "CTRObservacionesActiv_c": observaciones_finales
                    }
                else:
                    body = {
                        "StatusCode": "QUALIFIED",
                        "CTRActividades_c": "Contacto vIa Mail",
                        "CTRObservacionesActiv_c": observaciones_finales,
                        "Rank": etapa
                    }
                
                # 5. Hacer PATCH a Oracle
                params_patch = {
                    "onlyData": "true",
                    "fields": "StatusCode"
                }
                print(url_get)
                print(lead_data)
                print(lead_data.get("LeadId"))
                response_patch = client.patch(url_get+lead_data.get("LeadId"), headers=headers, params=params_patch, json=body, timeout=30.0)
                response_patch.raise_for_status()
                oracle_response = response_patch.json()
                # Publicar nota en Infobip indicando éxito (best-effort)
                try:
                    # Mapear etapa a descripción amigable
                    etapa_descripcion = {
                        "COOL": "Poco Prometedora",
                        "WARM": "Medianamente Prometedora",
                        "HOT": "Prometedora"
                    }.get(etapa, etapa)
                    nota_text = (
                        f"Se clasificó correctamente en el CRM.\nNueva Clasificación: {etapa_descripcion}.\n"
                        f"Observación agregada: {nuevo_comentario}"
                    )
                    url_nota = f"https://{settings.INFOBIP_API_HOST}/ccaas/1/conversations/{id_conversation}/notes"
                    payload_nota = {"content": nota_text}
                    headers_infobip = {
                        "Authorization": f"App {settings.INFOBIP_API_KEY}",
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    }
                    try:
                        client.post(url_nota, headers=headers_infobip, json=payload_nota, timeout=30.0)
                    except Exception:
                        # No bloquear si la nota falla
                        pass
                except Exception:
                    pass

                return {
                    "success": True,
                    "message": f"Lead {lead_id} actualizado exitosamente en Oracle",
                    "lead_id": lead_id,
                    "etapa": etapa,
                    "comentario_agregado": nuevo_comentario,
                    "oracle_response": oracle_response
                }
                
        except httpx.HTTPStatusError as e:
            # Intentar publicar nota de fallo en Infobip (best-effort)
            try:
                nota_text = (
                    f"Error al actualizar el lead\n"
                    f" Mensaje de error: {str(e)}"
                )
                url_nota = f"https://{settings.INFOBIP_API_HOST}/ccaas/1/conversations/{id_conversation}/notes"
                payload_nota = {"content": nota_text}
                headers_infobip = {
                    "Authorization": f"App {settings.INFOBIP_API_KEY}",
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
                try:
                    with httpx.Client() as client2:
                        client2.post(url_nota, headers=headers_infobip, json=payload_nota, timeout=30.0)
                except Exception:
                    pass
            except Exception:
                pass

            return {
                "success": False,
                "message": f"Error al comunicarse con Oracle: {e.response.status_code} - {e.response.text}",
                "lead_id": lead_id
            }
        except Exception as e:
            # Intentar publicar nota de fallo inesperado en Infobip (best-effort)
            try:
                nota_text = (
                    f"Error al actualizar el lead\n"
                    f" Mensaje de error: {str(e)}"
                )
                url_nota = f"https://{settings.INFOBIP_API_HOST}/ccaas/1/conversations/{id_conversation}/notes"
                payload_nota = {"content": nota_text}
                headers_infobip = {
                    "Authorization": f"App {settings.INFOBIP_API_KEY}",
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
                try:
                    with httpx.Client() as client2:
                        client2.post(url_nota, headers=headers_infobip, json=payload_nota, timeout=30.0)
                except Exception:
                    pass
            except Exception:
                pass

            return {
                "success": False,
                "message": f"Error inesperado: {str(e)}",
                "lead_id": lead_id
            }
