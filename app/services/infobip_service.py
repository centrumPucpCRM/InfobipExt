"""
Servicio para interactuar con APIs de Infobip
"""
import requests
from typing import Optional, Dict, Any
from app.core.config import settings


class InfobipService:
    """Servicio para manejar operaciones con Infobip"""
    
    @staticmethod
    def create_person_with_phone(phone_number: str, person_type: str = "CUSTOMER") -> Optional[str]:
        """
        Crea una persona en Infobip People usando solo el número de teléfono.
        
        Args:
            phone_number: Número de teléfono en formato E.164 sin '+'
            person_type: Tipo de persona (default: "CUSTOMER")
            
        Returns:
            ID de la persona creada o None en caso de error
        """
        try:
            url = f"https://{settings.INFOBIP_API_HOST}/people/2/persons"
            headers = {
                "Authorization": f"App {settings.INFOBIP_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            payload = {
                "type": person_type,
                "contactInformation": {
                    "phone": [
                        {
                            "number": phone_number
                        }
                    ]
                }
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            
            if response.ok:
                data = response.json()
                person_id = data.get("id")
                print(f"[InfobipService] Persona creada con ID: {person_id}")
                return person_id
            else:
                print(f"[InfobipService] Error al crear persona: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"[InfobipService] Excepción al crear persona: {e}")
            return None
    
    @staticmethod
    def get_agent_id_from_conversation(conversation_id: str) -> Optional[str]:
        """
        Consulta la conversación en Conversations y devuelve el agentId.
        
        Args:
            conversation_id: ID de la conversación
            
        Returns:
            agentId o None si no existe o hay error
        """
        try:
            url = f"https://{settings.INFOBIP_API_HOST}/ccaas/1/conversations/{conversation_id}"
            headers = {
                "Authorization": f"App {settings.INFOBIP_API_KEY}",
                "Accept": "application/json"
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.ok:
                data = response.json()
                agent_id = data.get("agentId")
                print(f"[InfobipService] agentId encontrado: {agent_id}")
                return agent_id
            else:
                print(f"[InfobipService] Error al consultar conversación: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"[InfobipService] Excepción al consultar conversación: {e}")
            return None