"""
Chat Orchestrator - Maneja la sincronización de chats con Infobip
"""
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.services.infobip_service import InfobipService
from app.services.rdv_service import RdvService
from app.core.config import settings


class ChatOrchestrator:
    """Orquestador para sincronización de chats"""
    
    def __init__(self, db: Session):
        self.db = db
        # Número de la línea de atención (desde config)
        self.mi_numero = "51992948046"  # TODO: Mover a settings
    
    def sync_conversation_with_rdv(
        self,
        telefono: str,
        estado_conversacion: str,
        conversation_id: str,
        local_people: Optional[Any],
        agent_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Sincroniza conversación con RDV usando métodos internos directos
        
        Args:
            telefono: Teléfono del usuario
            estado_conversacion: Estado de la conversación
            conversation_id: ID de la conversación
            local_people: Objeto People local (ya obtenido)
            agent_id: ID del agente (opcional)
            
        Returns:
            Respuesta de la sincronización o None si falla
        """
        try:
            from app.services.conversation_service import ConversationService
            from app.services.rdv_service import RdvService
            
            # Usar el people que ya se obtuvo/creó
            people = local_people
            
            # Buscar RDV por agent_id si existe
            rdv = None
            if agent_id:
                rdv = RdvService.find_by_infobip_external_id(self.db, agent_id)
            
            # Crear o actualizar conversación
            existing_conversation = ConversationService.get_by_external_id(self.db, conversation_id)
            
            if existing_conversation:
                # Actualizar conversación existente
                existing_conversation.estado_conversacion = estado_conversacion
                if people:
                    existing_conversation.id_people = people.id
                if rdv:
                    existing_conversation.id_rdv = rdv.id
                self.db.commit()
                self.db.refresh(existing_conversation)
                conversation = existing_conversation
            else:
                # Crear nueva conversación
                conversation = ConversationService.create_flexible(
                    db=self.db,
                    id_conversation=conversation_id,
                    id_people=people.id if people else None,
                    id_rdv=rdv.id if rdv else None,
                    estado_conversacion=estado_conversacion,
                    telefono_creado=telefono
                )
            
            print(f"[ChatOrchestrator] Conversación sincronizada: {conversation.id}")
            
            return {
                "success": True,
                "conversation_id": conversation.id,
                "external_id": conversation.id_conversation,
                "people_id": conversation.id_people,
                "rdv_id": conversation.id_rdv,
                "estado": conversation.estado_conversacion
            }
            
        except Exception as e:
            print(f"[ChatOrchestrator] Excepción en sync: {e}")
            return None
    
    def create_or_find_person(self, telefono: str) -> tuple[Optional[str], Optional[Any]]:
        """
        Crea o encuentra una persona, manejando todos los casos:
        1. Intenta crear en Infobip
        2. Si ya existe, busca en Infobip
        3. Si no encuentra en Infobip, busca en sistema local
        4. Si no existe en local, crea en local con datos básicos
        
        Args:
            telefono: Número de teléfono
            
        Returns:
            Tupla (infobip_person_id, local_people_object)
        """
        try:
            from app.services.people_service import PeopleService
            
            # 1. Intentar crear/buscar en Infobip
            infobip_person_id = InfobipService.create_person_with_phone(telefono)
            
            if infobip_person_id:
                # Asegurar que infobip_id sea string (Pydantic espera str)
                infobip_person_id = str(infobip_person_id)
                print(f"[ChatOrchestrator] Persona obtenida de Infobip: {infobip_person_id}")
                # Buscar o crear el people local
                local_people = PeopleService.get_by_phone(self.db, telefono)
                if not local_people:
                    # Crear people local con el infobip_id
                    from app.schemas.people_ext import PeopleExtCreateFlexible
                    people_create = PeopleExtCreateFlexible(
                        party_id=None,
                        party_number=None,
                        telefono=telefono,
                        infobip_id=infobip_person_id
                    )
                    local_people = PeopleService.create_flexible(self.db, people_create)
                return infobip_person_id, local_people
            
            # 2. Si falla Infobip, buscar en sistema local
            print(f"[ChatOrchestrator] Buscando persona en sistema local por teléfono: {telefono}")
            local_people = PeopleService.get_by_phone(self.db, telefono)
            
            if local_people and local_people.infobip_id:
                print(f"[ChatOrchestrator] Persona encontrada en local con infobip_id: {local_people.infobip_id}")
                return local_people.infobip_id, local_people
            
            # 3. Si no existe en local, obtener datos completos de Infobip
            print(f"[ChatOrchestrator] Obteniendo datos completos de Infobip para: {telefono}")
            
            infobip_person_data = InfobipService.get_person_data_by_phone(telefono)
            
            if infobip_person_data:
                # Crear registro local con datos completos de Infobip
                from app.schemas.people_ext import PeopleExtCreateFlexible
                # cast id to string to satisfy pydantic string_type
                infobip_id_str = None
                if infobip_person_data.get("id") is not None:
                    infobip_id_str = str(infobip_person_data.get("id"))

                people_create = PeopleExtCreateFlexible(
                    party_id=infobip_person_data.get("party_id"),
                    party_number=infobip_person_data.get("party_number"),
                    telefono=telefono,
                    infobip_id=infobip_id_str
                )
                
                new_people = PeopleService.create_flexible(self.db, people_create)
                print(f"[ChatOrchestrator] Persona creada en local con datos de Infobip: {new_people.id}")
                return infobip_person_data.get("id"), new_people
            else:
                # Si no se encuentra en Infobip, crear con datos mínimos
                from app.schemas.people_ext import PeopleExtCreateFlexible
                
                people_create = PeopleExtCreateFlexible(
                    party_id=None,
                    party_number=None,
                    telefono=telefono,
                    infobip_id=None
                )
                
                new_people = PeopleService.create_flexible(self.db, people_create)
                print(f"[ChatOrchestrator] Persona creada en local con datos básicos: {new_people.id}")
                
                # Intentar crear en Infobip
                infobip_person_id = InfobipService.create_person_with_phone(telefono)
                
                if infobip_person_id:
                    # Guardar como string
                    new_people.infobip_id = str(infobip_person_id)
                    self.db.commit()
                    print(f"[ChatOrchestrator] Actualizado con infobip_id: {infobip_person_id}")
                    return str(infobip_person_id), new_people
                else:
                    return None, new_people
            
        except Exception as e:
            print(f"[ChatOrchestrator] Error en create_or_find_person: {e}")
            return None, None
    
    def get_rdv_by_external_id(self, external_id: str) -> Optional[Dict[str, Any]]:
        """
        Consulta RDV por infobip_external_id usando el servicio interno
        
        Args:
            external_id: ID externo de Infobip
            
        Returns:
            Datos del RDV o None si no existe
        """
        try:
            rdv = RdvService.find_by_infobip_external_id(self.db, external_id)
            
            if rdv:
                return {
                    "id": rdv.id,
                    "party_id": rdv.party_id,
                    "party_number": rdv.party_number,
                    "infobip_external_id": rdv.infobip_external_id,
                    "correo": rdv.correo,
                    "first_name": rdv.first_name,
                    "last_name": rdv.last_name
                }
            else:
                print(f"[ChatOrchestrator] RDV no encontrado para agentId: {external_id}")
                return None
                
        except Exception as e:
            print(f"[ChatOrchestrator] Excepción al consultar RDV: {e}")
            return None
    
    def sincronizar_chat(
        self,
        telefono_to: str,
        telefono_from: str,
        conversacion: str,
        persona: Optional[str] = None,
        estado_conversacion: str = "OPEN"
    ) -> Dict[str, Any]:
        """
        Flujo principal de sincronización de chat (equivalente a lambda_handler)
        
        Args:
            telefono_to: Teléfono destino
            telefono_from: Teléfono origen
            conversacion: ID de la conversación
            persona: ID de la persona (opcional)
            estado_conversacion: Estado de la conversación
            
        Returns:
            Diccionario con el resultado de la sincronización
        """
        print(f"[ChatOrchestrator] Iniciando sincronización de chat")
        print(f"[ChatOrchestrator] Parámetros: to={telefono_to}, from={telefono_from}, conv={conversacion}")
        
        # 1. Validar conversationId obligatorio
        conversation_id = conversacion
        if not conversation_id:
            error_msg = "No se puede ejecutar el flujo sin un conversationId."
            print(f"[ChatOrchestrator] Error: {error_msg}")
            return {
                "status": "error",
                "message": error_msg
            }
        
        # 2. Determinar el teléfono del usuario (cliente)
        telefono_usuario = ""
        if telefono_from == self.mi_numero:
            telefono_usuario = telefono_to
        elif telefono_to == self.mi_numero:
            telefono_usuario = telefono_from
        
        print(f"[ChatOrchestrator] telefono_from: {telefono_from}")
        print(f"[ChatOrchestrator] telefono_to: {telefono_to}")
        print(f"[ChatOrchestrator] telefono_usuario (cliente): {telefono_usuario}")
        
        # 3. Resolver person_id (usar el que viene o crearlo)
        person_id = persona
        local_people = None  # Para asociar a la conversación
        
        if not person_id or person_id == "":
            print("[ChatOrchestrator] No se recibió person_id. Iniciando flujo de creación de persona...")
            if telefono_usuario:
                person_id, local_people = self.create_or_find_person(telefono_usuario)
            else:
                print("[ChatOrchestrator] No hay teléfono de usuario para crear persona.")
        else:
            print(f"[ChatOrchestrator] Usando person_id existente: {person_id}")
            # Buscar el people local por teléfono para asociar a la conversación
            from app.services.people_service import PeopleService
            local_people = PeopleService.get_by_phone(self.db, telefono_usuario)
        
        # 4. Obtener agentId desde la conversación
        agent_id = InfobipService.get_agent_id_from_conversation(conversation_id)
        
        # 4.1. Consultar RDV si tenemos agentId
        rdv_data = None
        if agent_id:
            rdv_data = self.get_rdv_by_external_id(agent_id)
        
        # 5. Registrar la conversación en el sistema externo
        sync_result = self.sync_conversation_with_rdv(
            telefono=telefono_usuario,
            estado_conversacion=estado_conversacion,
            conversation_id=conversation_id,
            local_people=local_people,  # Pasar el objeto people local
            agent_id=agent_id
        )
        
        print(f"[ChatOrchestrator] Resultado sync: {sync_result}")
        # 6.1. Sincronizar mensajes y notas de Infobip para esta conversación
        try:
            from app.services.mensaje_service import MensajeService
            total_msgs, nuevos = MensajeService.sync_mensajes_from_infobip(self.db, conversation_id)
            print(f"[ChatOrchestrator] Mensajes sincronizados: total={total_msgs}, nuevos={nuevos}")
            respuesta["messages_sync"] = {
                "total_from_infobip": total_msgs,
                "new_inserted": nuevos
            }
        except Exception as e:
            print(f"[ChatOrchestrator] Error sincronizando mensajes: {e}")
            respuesta["messages_sync_error"] = str(e)
        
        # 6. Armar respuesta
        respuesta = {
            "telefono": telefono_usuario,
            "conversationId": conversation_id,
            "person_id": person_id,
            "status": "success"
        }
        
        # Añadir agentId si existe
        if agent_id:
            respuesta["agentId"] = agent_id
        
        # Añadir info de RDV si existe
        if rdv_data:
            respuesta["rdv"] = rdv_data
        
        # Añadir resultado del sync si existe
        if sync_result:
            respuesta["syncResult"] = sync_result
        
        print(f"[ChatOrchestrator] Respuesta final: {respuesta}")
        return respuesta