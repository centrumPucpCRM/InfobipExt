"""
Chat Orchestrator - Maneja la sincronización de chats con Infobip
"""
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
import requests

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
        person_id: Optional[str],
        agent_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Llama al endpoint interno para sincronizar conversación con RDV
        
        Args:
            telefono: Teléfono del usuario
            estado_conversacion: Estado de la conversación
            conversation_id: ID de la conversación
            person_id: ID de la persona
            agent_id: ID del agente (opcional)
            
        Returns:
            Respuesta del endpoint o None si falla
        """
        try:
            url = f"{settings.API_V1_STR}/conversations/sync-from-infobip"
            # Construir URL completa para llamada interna
            base_url = "http://localhost:8000"  # Llamada interna
            full_url = f"{base_url}{url}"
            
            payload = {
                "telefono": telefono,
                "estado_conversacion": estado_conversacion,
                "conversationId": conversation_id,
                "personId": str(person_id) if person_id is not None else None,
            }
            
            if agent_id:
                payload["agentId"] = agent_id
            
            # Quitar claves con None
            payload = {k: v for k, v in payload.items() if v is not None}
            
            headers = {
                "Authorization": f"Bearer {settings.API_TOKEN}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            response = requests.post(full_url, headers=headers, json=payload, timeout=10)
            
            print(f"[ChatOrchestrator] Sync Status: {response.status_code}")
            print(f"[ChatOrchestrator] Sync Body: {response.text}")
            
            if response.ok:
                return response.json()
            else:
                return None
                
        except Exception as e:
            print(f"[ChatOrchestrator] Excepción en sync: {e}")
            return None
    
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
        if not person_id or person_id == "":
            print("[ChatOrchestrator] No se recibió person_id. Iniciando flujo de creación de persona...")
            if telefono_usuario:
                person_id = InfobipService.create_person_with_phone(telefono_usuario)
            else:
                print("[ChatOrchestrator] No hay teléfono de usuario para crear persona.")
        else:
            print(f"[ChatOrchestrator] Usando person_id existente: {person_id}")
        
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
            person_id=person_id,
            agent_id=agent_id
        )
        
        print(f"[ChatOrchestrator] Resultado sync: {sync_result}")
        
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