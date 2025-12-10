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
        Si ya existe, busca y devuelve el ID existente.
        
        Args:
            phone_number: Número de teléfono en formato E.164 sin '+'
            person_type: Tipo de persona (default: "CUSTOMER")
            
        Returns:
            ID de la persona (creada o existente) o None en caso de error
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
            elif response.status_code == 400 and "already exists" in response.text:
                # Si ya existe, buscar la persona por teléfono
                print(f"[InfobipService] Persona ya existe, buscando ID existente...")
                return InfobipService.find_person_by_phone(phone_number)
            else:
                print(f"[InfobipService] Error al crear persona: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"[InfobipService] Excepción al crear persona: {e}")
            return None
    
    @staticmethod
    def find_person_by_phone(phone_number: str) -> Optional[str]:
        """
        Busca una persona en Infobip por número de teléfono.
        
        Args:
            phone_number: Número de teléfono a buscar
            
        Returns:
            ID de la persona encontrada o None si no existe
        """
        try:
            url = f"https://{settings.INFOBIP_API_HOST}/people/2/persons"
            headers = {
                "Authorization": f"App {settings.INFOBIP_API_KEY}",
                "Accept": "application/json"
            }
            
            params = {
                "phone": phone_number
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=15)
            
            if response.ok:
                data = response.json()
                persons = data.get("persons", [])
                
                if persons:
                    person_id = persons[0].get("id")
                    print(f"[InfobipService] Persona encontrada con ID: {person_id}")
                    return person_id
                else:
                    print(f"[InfobipService] No se encontró persona con teléfono: {phone_number}")
                    return None
            else:
                print(f"[InfobipService] Error al buscar persona: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"[InfobipService] Excepción al buscar persona: {e}")
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