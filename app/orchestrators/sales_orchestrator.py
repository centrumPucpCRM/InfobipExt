"""
Sales Orchestrator - Contiene los flujos de venta directamente
"""
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import requests
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import re

from app.services.people_service import PeopleService
from app.services.conversation_service import ConversationService
from app.services.rdv_service import RdvService
from app.schemas.people_ext import PeopleExtCreate
from app.core.config import settings

# URL Lambda para validación de números


class SalesOrchestrator:
    """
    Orquestador principal que contiene los flujos de venta activa y pasiva
    
    Aquí iremos implementando paso a paso la lógica según necesidades
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def validar_telefono(self, telefono: str) -> bool:
        """
        Valida un número de teléfono usando la Lambda de validación.
        
        Args:
            telefono: Número de teléfono a validar (ej: "51987659876")
            
        Returns:
            True si el número es válido, False si no lo es
        """
        try:
            payload = {"number": telefono}
            response = requests.post("https://c2kltclq36brhdbbxtu6m7w5qu0jvhzb.lambda-url.us-east-1.on.aws/", json=payload, timeout=10)
            data = response.json()
            return data.get("is_valid", False)
        except Exception:
            return False
    
    def crear_people_infobip(
        self,
        party_id: int,
        party_number: int,
        telefono: str
    ) -> Optional[Dict[str, Any]]:
        """
        Crea un nuevo People en Infobip usando la API.
        
        Args:
            party_id: Party ID del cliente
            party_number: Party Number del cliente
            telefono: Teléfono del cliente (formato: 51987654321)
            
        Returns:
            Diccionario con la respuesta de Infobip o None si falló
        """
        try:
            url = f"https://{settings.INFOBIP_API_HOST}/people/2/persons"
            
            headers = {
                "Authorization": f"App {settings.INFOBIP_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            payload = {
                "contactInformation": {
                    "phone": [
                        {
                            "number": telefono
                        }
                    ]
                },
                "customAttributes": {
                    "party_id": str(party_id),
                    "party_number": str(party_number)
                }
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            
            if response.status_code in [200, 201]:
                data = response.json()
                return {
                    "success": True,
                    "id": data.get("id"),
                    "party_id": party_id,
                    "party_number": party_number,
                    "telefono": telefono,
                    "response": data
                }
            else:
                return {
                    "success": False,
                    "error": response.text,
                    "status_code": response.status_code
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def actualizar_people_infobip(
        self,
        telefono: str,
        party_id: int,
        party_number: int
    ) -> Optional[Dict[str, Any]]:
        """
        Actualiza un People existente en Infobip buscándolo por teléfono.
        Actualiza los custom attributes party_id y party_number.
        
        Args:
            telefono: Teléfono del cliente para buscar
            party_id: Party ID a asignar
            party_number: Party Number a asignar
            
        Returns:
            Diccionario con la respuesta de Infobip o None si falló
        """
        try:
            # Primero buscar el People por teléfono
            url_search = f"https://{settings.INFOBIP_API_HOST}/people/2/persons"
            
            headers = {
                "Authorization": f"App {settings.INFOBIP_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            params = {
                "phone": telefono
            }
            
            response_search = requests.get(url_search, headers=headers, params=params, timeout=15)
            
            if response_search.status_code != 200:
                return {
                    "success": False,
                    "error": f"Error buscando People: {response_search.text}",
                    "status_code": response_search.status_code
                }
            
            data_search = response_search.json()
            persons = data_search.get("persons", [])
            
            if not persons:
                return {
                    "success": False,
                    "error": "No se encontró People con ese teléfono"
                }
            
            # Tomar el primer resultado
            person_id = persons[0].get("id")
            
            # Actualizar el People con los custom attributes
            url_update = f"https://{settings.INFOBIP_API_HOST}/people/2/persons/{person_id}"
            
            payload = {
                "customAttributes": {
                    "Party_id": str(party_id),
                    "Party_number": str(party_number)
                }
            }
            
            response_update = requests.put(url_update, headers=headers, json=payload, timeout=15)
            
            if response_update.status_code in [200, 204]:
                return {
                    "success": True,
                    "id": person_id,
                    "party_id": party_id,
                    "party_number": party_number,
                    "telefono": telefono
                }
            else:
                return {
                    "success": False,
                    "error": f"Error actualizando People: {response_update.text}",
                    "status_code": response_update.status_code
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def crear_o_actualizar_people_infobip(
        self,
        party_id: int,
        party_number: int,
        telefono: str
    ) -> Dict[str, Any]:
        """
        Intenta crear un People en Infobip. Si falla, intenta actualizar uno existente por teléfono.
        
        Args:
            party_id: Party ID del cliente
            party_number: Party Number del cliente
            telefono: Teléfono del cliente
            
        Returns:
            Diccionario con el resultado de la operación
        """
        # Intentar crear
        nuevo_people = self.crear_people_infobip(
            party_id=party_id,
            party_number=party_number,
            telefono=telefono
        )
        
        if nuevo_people and nuevo_people.get("success"):
            return {
                "success": True,
                "id": nuevo_people.get("id"),
                "party_id": party_id,
                "party_number": party_number,
                "telefono": telefono,
                "actividad": "Create"
            }
        
        # Falló crear - intentar actualizar por teléfono
        people_actualizado = self.actualizar_people_infobip(
            telefono=telefono,
            party_id=party_id,
            party_number=party_number
        )
        
        if people_actualizado and people_actualizado.get("success"):
            return {
                "success": True,
                "id": people_actualizado.get("id"),
                "party_id": party_id,
                "party_number": party_number,
                "telefono": telefono,
                "actividad": "Update"
            }
        
        # Ambos fallaron
        return {
            "success": False,
            "error_crear": nuevo_people.get("error") if nuevo_people else "Desconocido",
            "error_actualizar": people_actualizado.get("error") if people_actualizado else "Desconocido"
        }
    
    def crear_people_local(
        self,
        party_id: int,
        party_number: int,
        telefono: str,
        infobip_id: Optional[str] = None
    ) -> None:
        """
        Crea un People en la base de datos local y hace commit.
        
        Args:
            party_id: Party ID del cliente
            party_number: Party Number del cliente
            telefono: Teléfono del cliente
            infobip_id: ID del People en Infobip (opcional)
        """
        people_create = PeopleExtCreate(
            party_id=party_id,
            party_number=party_number,
            telefono=telefono,
            infobip_id=infobip_id
        )
        PeopleService.create(db=self.db, people_data=people_create)
    
    def enviar_correo(self, destino: str, asunto: str, cuerpo: str) -> bool:
        """
        Envía un correo electrónico usando SMTP de Gmail.
        
        Args:
            destino: Email del destinatario
            asunto: Asunto del correo
            cuerpo: Contenido del correo
            
        Returns:
            True si se envió correctamente, False si falló
        """
        remitente = "isidorosantivanez@gmail.com"
        contraseña = "jrny qwcr bjyn aodg"
        intentos = 2
        tiempo_espera = 3
        
        mensaje = MIMEMultipart()
        mensaje["From"] = remitente
        mensaje["To"] = destino
        mensaje["Cc"] = "gestordecuentascrmcentrum@pucp.edu.pe"
        mensaje["Subject"] = asunto
        mensaje.attach(MIMEText(cuerpo, "plain"))
        
        # Correos a los que se enviará (To + Cc)
        destinatarios = [destino,'isidorosantivanez@gmail.com','andre.zambrano@pucp.edu.pe', "gestordecuentascrmcentrum@pucp.edu.pe"]
        
        for i in range(intentos):
            try:
                server = smtplib.SMTP("smtp.gmail.com", 587)
                server.starttls()
                server.login(remitente, contraseña)
                server.sendmail(remitente, destinatarios, mensaje.as_string())
                server.quit()
                print(f"Correo enviado con éxito a: {destinatarios}")
                return True
            except Exception as e:
                print(f"Error al enviar correo (intento {i+1}/{intentos}): {str(e)}")
                if i < intentos - 1:
                    print(f"Reintentando en {tiempo_espera} segundos...")
                    time.sleep(tiempo_espera)
        
        return False
    
    def buscar_people_party(
        self,
        party_id: Optional[int] = None,
        party_number: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Busca un People por party_id o party_number.
        
        Args:
            party_id: ID del party (prioridad)
            party_number: Número del party (alternativo)
            
        Returns:
            Diccionario con la información del People o None si no existe
        """
        people = PeopleService.find_by_party(
            db=self.db,
            party_id=party_id,
            party_number=party_number
        )
        
        if not people:
            return None
        
        return {
            "id": people.id,
            "party_id": people.party_id,
            "party_number": people.party_number,
            "telefono": people.telefono,
            "infobip_id": people.infobip_id
        }

    def _obtener_nombre_programa(self, codigo_crm: str) -> Optional[str]:
        """
        Consulta Oracle Sales Cloud para obtener el nombre del programa
        dado un `ProductGroupId` (código CRM).

        Args:
            codigo_crm: Código del producto/programa en Oracle (ProductGroupId)

        Returns:
            El nombre del programa si se encuentra, o None en caso contrario.
        """
        try:
            base_url = f"{settings.ORACLE_CRM_URL}/catalogProductGroups/"
            headers = {
                "Authorization": settings.ORACLE_CRM_AUTH,
                "Content-Type": "application/json"
            }
            params = {
                "onlyData": "true",
                "fields": "ProductGroupName",
                "q": f"ProductGroupId={codigo_crm}",
                "limit": 1
            }
            resp = requests.get(base_url, headers=headers, params=params, timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json()
            items = data.get("items") or []
            if not items:
                return None
            return items[0].get("ProductGroupName")
        except Exception:
            return None

    def obtener_nombre_por_dni(self, numero_doc: str) -> Optional[str]:
        """
        Consulta Oracle Contacts por número de documento (DNI) y devuelve el
        `ContactName`.

        Args:
            numero_doc: DNI / número de documento a buscar

        Returns:
            El nombre del contacto (`ContactName`) si se encuentra, o `None`.
        """
        try:
            base_url = f"{settings.ORACLE_CRM_URL}/contacts"
            headers = {
                "Authorization": settings.ORACLE_CRM_AUTH,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            params = {
                "onlyData": "true",
                "fields": "ContactName",
                "q": f"PersonDEO_CTRNrodedocumento_c={numero_doc}",
                "limit": 1,
            }

            resp = requests.get(base_url, headers=headers, params=params, timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json()
            items = data.get("items") or []
            if not items:
                return None
            nombre = items[0].get("ContactName")
            # Imprimir el nombre (según lo solicitado)
            try:
                print(nombre)
            except Exception:
                pass
            return nombre
        except Exception:
            return None
    
    def buscar_people_telefono(
        self,
        telefono: str
    ) -> Optional[Dict[str, Any]]:
        """
        Busca un People por teléfono.
        
        Args:
            telefono: Teléfono del People
            
        Returns:
            Diccionario con la información del People o None si no existe
        """
        people = PeopleService.get_by_phone(
            db=self.db,
            telefono=telefono
        )
        
        if not people:
            return None
        
        return {
            "id": people.id,
            "party_id": people.party_id,
            "party_number": people.party_number,
            "telefono": people.telefono,
            "infobip_id": people.infobip_id
        }

    def _get_rdv_contact(self, osc: Dict[str, Any]):
        """
        Resolve RDV contact (RdvExt ORM object) from the `osc` payload.

        Tries `osc_rdv_party_number` first, then `osc_rdv_party_id`.
        Accepts numeric strings and ints; returns the RdvExt object or None.
        """
        try:
            rdv_party = osc.get('osc_rdv_party_number') if isinstance(osc, dict) else None
            rdv_party_id = osc.get('osc_rdv_party_id') if isinstance(osc, dict) else None

            # prefer party_number when provided
            if rdv_party is not None:
                try:
                    pn = int(rdv_party)
                except Exception:
                    pn = None
                if pn is not None:
                    rdv = RdvService.find_by_party(db=self.db, party_number=pn)
                    if rdv:
                        return rdv

            if rdv_party_id is not None:
                try:
                    pid = int(rdv_party_id)
                except Exception:
                    pid = None
                if pid is not None:
                    rdv = RdvService.find_by_party(db=self.db, party_id=pid)
                    if rdv:
                        return rdv

        except Exception:
            return None

        return None

    def obtenerLeadIdPorNumber(self, leadNumber: int) -> Optional[str]:
        """
        Consulta Oracle Sales Cloud por LeadNumber y devuelve el LeadId.

        Usa `settings.ORACLE_CRM_URL` y `settings.ORACLE_CRM_AUTH`.
        """
        #Esperando
        time.sleep(5)
        try:
            base_url = f"{settings.ORACLE_CRM_URL}/leads/"
            headers = {
                "Authorization": settings.ORACLE_CRM_AUTH,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            params = {
                "onlyData": "true",
                "fields": "LeadId",
                "q": f"LeadNumber={leadNumber}",
                "limit": 1,
            }

            resp = requests.get(base_url, headers=headers, params=params, timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json()
            items = data.get("items") or []
            if not items:
                return None
            return items[0].get("LeadId")
        except Exception:
            return None
    def obtenerPartyNumberRDV(self, PartyId):
        url = "https://cang.fa.us2.oraclecloud.com/crmRestApi/resources/11.13.18.05/resourceUsers/"
        request_headers = {
            'Authorization': "Basic QVBJQ1JNOlZ3ZXVlMTIzNDU=",
            'Content-Type': 'application/json'
        }
        params = {
            #"fields":"PartyName,ResourceEmail",
            'onlyData': 'true',
            "q":f"ResourcePartyId={PartyId}"
        }
        response = requests.get(url, params=params, headers=request_headers)
        return response.json()["items"][0]["ResourcePartyNumber"]


    def flujo_venta_activa(
        self,
        osc_people_dni: str,  # DNI obligatorio
        osc_people_party_id: Optional[int] = None,
        osc_people_party_number: Optional[int] = None,
        osc_people_telefono: Optional[str] = None,
        osc_rdv_party_id: Optional[int] = None,
        osc_rdv_party_number: Optional[int] = None,
        osc_conversation_codigo_crm: Optional[str] = None,
        osc_conversation_lead_id: Optional[str] = None,
        osc_conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Flujo de venta activa: Usuario comienza conversación
        
        Recibe datos de Oracle Sales Cloud para implementar lógica
        
        Args:
            osc_people_dni: DNI del cliente (obligatorio)
            osc_conversation_id: ID de conversación existente en Infobip (opcional)
        """
        # Normalizar teléfono: quitar '+' al inicio, eliminar espacios,
        # si viene con duplicado de prefijo '51' al inicio (ej: '5151...')
        # eliminar el primer '51', y si viene como '9...' añadir '51' adelante.
        print(osc_people_telefono)
        if osc_people_telefono:
            telefono_normalizado = osc_people_telefono.strip()
            # Eliminar todo lo que esté entre paréntesis (ej: 51(1)9919... -> 519919...)
            telefono_normalizado = re.sub(r"\([^)]*\)", "", telefono_normalizado)
            # Eliminar todos los signos '+' en cualquier posición y espacios
            telefono_normalizado = telefono_normalizado.replace("+", "").replace(" ", "")

            # Caso: duplicado de prefijo '51' al inicio, p.ej '5151...'
            if telefono_normalizado.startswith("5151"):
                telefono_normalizado = telefono_normalizado[2:]
            # Caso: número móvil sin prefijo, p.ej '9xxxxxxx' -> anteponer '51'
            elif telefono_normalizado.startswith("9"):
                telefono_normalizado = "51" + telefono_normalizado

            osc_people_telefono = telefono_normalizado
        print(osc_people_telefono)
        print("osc_conversation_lead_id que es leadNumber:",osc_conversation_lead_id)
        if osc_rdv_party_number is None:
           osc_rdv_party_number = self.obtenerPartyNumberRDV(osc_rdv_party_id)

        # Validar teléfono de Oracle    
        OT_valido = self.validar_telefono(osc_people_telefono)
        
        # Buscar People por party
        MatchParty = self.buscar_people_party(
            party_id=osc_people_party_id,
            party_number=osc_people_party_number
        )
        
        # Buscar People por teléfono
        MatchTelefono = self.buscar_people_telefono(
            telefono=osc_people_telefono
        )
        
        people_a_usar = None  # El People que se usará en el flujo
        
        if(MatchParty != None): 
            if(MatchTelefono != None): # Existe Match por Party + Existe Match por Teléfono
                if(MatchParty["telefono"] != MatchTelefono["telefono"]):
                    # Teléfonos diferentes - hay conflicto entre Party y Teléfono
                    if(OT_valido == False):
                        # [Existe Match Party] + [Existe Match Teléfono] + [Teléfonos Diferentes] + [Teléfono Oracle INVÁLIDO]
                        comentario = (
                            f"El telefono enviado por el postulante es incorrecto.\n"
                            f"Se usara el registrado en el CRM"
                        )
                        MatchParty["comentario"] = comentario
                        people_a_usar = MatchParty
                    elif(OT_valido == True):
                        # [Existe Match Party] + [Existe Match Teléfono] + [Teléfonos Diferentes] + [Teléfono Oracle VÁLIDO]
                        comentario = (
                            "El teléfono enviado es válido, pero hay inconsistencias entre los contactos.\n"
                            "Puede continuar la conversacion, por favor de notificar al administrador."
                        )
                        MatchTelefono["comentario"] = comentario
                        people_a_usar = MatchTelefono
                        
                elif(MatchParty["telefono"] == MatchTelefono["telefono"]):
                    # [Existe Match Party] + [Existe Match Teléfono] + [Teléfonos Coinciden]
                    comentario = (
                        "El teléfono proporcionado es correcto y coincide con el registrado.\n"
                        "Puedes continuar con la conversación."
                    )
                    MatchParty["comentario"] = comentario
                    people_a_usar = MatchParty

            elif(MatchTelefono == None): # Existe Match por Party + NO Existe Match por Teléfono
                if(MatchParty["telefono"] == osc_people_telefono):
                    # [Existe Match Party] + [NO Existe Match Teléfono] + [Teléfono Party = Teléfono Oracle]
                    comentario = (
                        "El teléfono proporcionado es correcto y coincide con el registrado.\n"
                        "Puedes continuar con la conversación."
                    )
                    MatchParty["telefono_actualizado"] = osc_people_telefono  # Nuevo teléfono a actualizar
                    MatchParty["actividad"] = "Update"
                    MatchParty["comentario"] = comentario
                    people_a_usar = MatchParty
                elif(MatchParty["telefono"] != osc_people_telefono):
                    if(OT_valido == False):
                        # [Existe Match Party] + [NO Existe Match Teléfono] + [Teléfono Party ≠ Teléfono Oracle] + [Teléfono Oracle INVÁLIDO]
                        comentario = (
                            f"El telefono enviado por el postulante es incorrecto.\n"
                            f"Se usara el registrado en el CRM"
                        )
                        MatchParty["comentario"] = comentario
                        people_a_usar = MatchParty
                    elif(OT_valido == True):
                        # [Existe Match Party] + [NO Existe Match Teléfono] + [Teléfono Party ≠ Teléfono Oracle] + [Teléfono Oracle VÁLIDO]
                        comentario = (
                            "El teléfono proporcionado es correcto y coincide con el registrado.\n"
                            "Puedes continuar con la conversación."
                        )
                        MatchParty["comentario"] = comentario
                        MatchParty["telefono_actualizado"] = osc_people_telefono  # Nuevo teléfono a actualizar
                        MatchParty["actividad"] = "Update"
                        people_a_usar = MatchParty
        elif(MatchParty == None):
            if(MatchTelefono == None): # NO Existe Match por Party + NO Existe Match por Teléfono
                if(OT_valido == True):
                    # [NO Existe Match Party] + [NO Existe Match Teléfono] + [Teléfono Oracle VÁLIDO] → CREAR NUEVO
                    resultado_infobip = self.crear_o_actualizar_people_infobip(
                        party_id=osc_people_party_id,
                        party_number=osc_people_party_number,
                        telefono=osc_people_telefono
                    )
                    
                    # Obtener infobip_id del resultado y convertir a string
                    infobip_id = None
                    if resultado_infobip and resultado_infobip.get("success"):
                        id_value = resultado_infobip.get("id")
                        infobip_id = str(id_value) if id_value is not None else None
                    
                    self.crear_people_local(
                        party_id=osc_people_party_id,
                        party_number=osc_people_party_number,
                        telefono=osc_people_telefono,
                        infobip_id=infobip_id
                    )
                    people_a_usar = self.buscar_people_party(
                        party_number=osc_people_party_number
                    )
                    if people_a_usar:
                        people_a_usar["comentario"] = (
                            "El teléfono proporcionado es correcto.\n"
                            "Puedes continuar con la conversación."
                        )

                elif(OT_valido == False):
                    
                    # [NO Existe Match Party] + [NO Existe Match Teléfono] + [Teléfono Oracle INVÁLIDO] → FALLO + CORREO
                    correo_asunto = f"Notificación Infobip - Cliente DNI: {osc_people_dni} - No se pudo crear conversación"
                    correo_cuerpo = (
                        f"No fue posible crear la conversación para el cliente con DNI: {osc_people_dni}\n\n"
                        f"Teléfono enviado por Oracle: {osc_people_telefono} (INVÁLIDO)\n"
                        f"Nombre del programa: {self._obtener_nombre_programa(osc_conversation_codigo_crm)}\n"
                        f"Codigo del programa: {osc_conversation_codigo_crm}\n"
                        f"Motivo: No se encontró ningún registro en Infobip (ni por CRM ni por Teléfono enviado por el postulante)\n"
                        f"Acción requerida: Por favor verificar y corregir el número de teléfono del cliente en CRM.\n"
                        f"Debe generar la conversacion en infobip, no se generara automaticamente\n"
                    )
                    
                    # Enviar correo SOLO si el RDV tiene correo configurado
                    correo_enviado = False
                    try:
                        # Here `osc` dict isn't built yet; use the function args available
                        rdv_contact = None
                        if osc_rdv_party_number is not None:
                            try:
                                pn = int(osc_rdv_party_number)
                            except Exception:
                                pn = None
                            if pn is not None:
                                rdv_contact = RdvService.find_by_party(db=self.db, party_number=pn)
                        if not rdv_contact and osc_rdv_party_id is not None:
                            try:
                                pid = int(osc_rdv_party_id)
                            except Exception:
                                pid = None
                            if pid is not None:
                                rdv_contact = RdvService.find_by_party(db=self.db, party_id=pid)

                        if rdv_contact and getattr(rdv_contact, 'correo', None):
                            correo_enviado = self.enviar_correo(
                                destino=rdv_contact.correo,
                                asunto=correo_asunto,
                                cuerpo=correo_cuerpo
                            )
                    except Exception:
                        correo_enviado = False
                    
                    return {
                        "status": 200,
                        "correo_enviado": correo_enviado,
                        "content": "No se pudo crear conversación",
                        "comentario": "[NO Existe Match Party] + [NO Existe Match Teléfono] + [Teléfono Oracle INVÁLIDO]"
                    }
                
            elif(MatchTelefono != None): # NO Existe Match por Party + Existe Match por Teléfono
                # [NO Existe Match Party] + [Existe Match Teléfono]
                comentario = (
                    "El teléfono enviado es válido, pero actualmente está asociado a otro contacto en el CRM.\n"
                    "Por favor, revisa y actualiza la información en el CRM si es necesario para evitar confusiones."
                )
                MatchTelefono["comentario"] = comentario
                people_a_usar = MatchTelefono

        # Crear objeto OSC con todos los parámetros
        osc = {
            "osc_people_dni": osc_people_dni,
            "osc_people_party_id": osc_people_party_id,
            "osc_people_party_number": osc_people_party_number,
            "osc_people_telefono": osc_people_telefono,
            "osc_rdv_party_id": osc_rdv_party_id,
            "osc_rdv_party_number": osc_rdv_party_number,
            "osc_conversation_codigo_crm": osc_conversation_codigo_crm,
            "osc_conversation_lead_id": osc_conversation_lead_id,
            "osc_conversation_id": osc_conversation_id,
        }

        # Crear conversación y retornar resultado
        return self.crear_conversacion(osc, people_a_usar)
    
    def crear_conversacion(self, osc: Dict[str, Any], people_a_usar: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Crea una conversación en Infobip usando los datos de OSC y el People seleccionado.
        
        Flujo simplificado (infobip_id ya está sincronizado en people_ext):
        1. Obtener infobip_id del people_a_usar
        2. Si no tiene infobip_id → enviar correo error y retornar fallo
        3. Si requiere actualización de teléfono → actualizar en Infobip y BD local
        4. Obtener conversaciones del People
        
        Args:
            osc: Diccionario con los datos de Oracle Sales Cloud
            people_a_usar: Diccionario con el People que se usará para la conversación
            
        Returns:
            Diccionario con el resultado de la creación
        """
        if people_a_usar is None:
            return {
                "success": False,
                "error": "No hay People para crear conversación"
            }
        
        # Obtener infobip_id del people_a_usar (ya sincronizado)
        person_id = people_a_usar.get("infobip_id")
        
        if not person_id:
            # No tiene infobip_id → enviar correo de error
            correo_asunto = f"Notificación Infobip - Cliente DNI: {osc.get('osc_people_dni')} - People sin infobip_id"
            correo_cuerpo = (
                f"ERROR: No se pudo crear la conversación\n\n"
                f"Motivo: El People no tiene infobip_id sincronizado.\n\n"
                f"=== DATOS DEL CLIENTE ===\n"
                f"DNI: {osc.get('osc_people_dni')}\n"
                f"Party ID: {osc.get('osc_people_party_id')}\n"
                f"Party Number: {osc.get('osc_people_party_number')}\n"
                f"Teléfono Oracle: {osc.get('osc_people_telefono')}\n"
                f"Teléfono People: {people_a_usar.get('telefono')}\n\n"
                f"=== DATOS DE LA CONVERSACIÓN ===\n"
                f"Código CRM: {osc.get('osc_conversation_codigo_crm')}\n"
                f"Lead ID: {osc.get('osc_conversation_lead_id')}\n\n"
                f"=== DATOS DEL RDV ===\n"
                f"RDV Party ID: {osc.get('osc_rdv_party_id')}\n"
                f"RDV Party Number: {osc.get('osc_rdv_party_number')}\n\n"
                f"Acción requerida: Ejecutar sincronización de People con Infobip."
            )
            
            # Enviar correo SOLO si el RDV tiene correo configurado
            try:
                rdv_lookup = self._get_rdv_contact(osc)
                if rdv_lookup and getattr(rdv_lookup, 'correo', None):
                    self.enviar_correo(
                        destino=rdv_lookup.correo,
                        asunto=correo_asunto,
                        cuerpo=correo_cuerpo
                    )
            except Exception:
                pass
            
            return {
                "success": False,
                "error": "People no tiene infobip_id sincronizado",
                "people_id": people_a_usar.get("id")
            }
        
        # Determinar si requiere actualización de teléfono
        telefono_final = people_a_usar.get("telefono")
        requiere_actualizacion = False
        
        if people_a_usar.get("telefono_actualizado"):
            telefono_nuevo = people_a_usar["telefono_actualizado"]
            requiere_actualizacion = True
            
            # Actualizar teléfono en Infobip
            actualizacion_exitosa = self._actualizar_telefono_people_infobip(person_id, telefono_nuevo)
            
            if not actualizacion_exitosa:
                # Falló la actualización → enviar correo de error
                correo_asunto = f"Notificación Infobip - Cliente DNI: {osc.get('osc_people_dni')} - Error al actualizar teléfono"
                correo_cuerpo = (
                    f"ERROR: No se pudo crear la conversación\n\n"
                    f"Motivo: Falló la actualización del teléfono en Infobip.\n\n"
                    f"=== DATOS DEL CLIENTE ===\n"
                    f"DNI: {osc.get('osc_people_dni')}\n"
                    f"Party ID: {osc.get('osc_people_party_id')}\n"
                    f"Party Number: {osc.get('osc_people_party_number')}\n"
                    f"Teléfono Oracle: {osc.get('osc_people_telefono')}\n"
                    f"Teléfono anterior: {telefono_final}\n"
                    f"Teléfono nuevo (no se pudo actualizar): {telefono_nuevo}\n\n"
                    f"=== DATOS DE LA CONVERSACIÓN ===\n"
                    f"Código CRM: {osc.get('osc_conversation_codigo_crm')}\n"
                    f"Lead ID: {osc.get('osc_conversation_lead_id')}\n\n"
                    f"=== DATOS DEL RDV ===\n"
                    f"RDV Party ID: {osc.get('osc_rdv_party_id')}\n"
                    f"RDV Party Number: {osc.get('osc_rdv_party_number')}\n\n"
                    f"=== DATOS DE INFOBIP ===\n"
                    f"Person ID: {person_id}\n\n"
                    f"Acción requerida: Actualizar manualmente el teléfono del People en Infobip."
                )
                
                try:
                    rdv_lookup = self._get_rdv_contact(osc)
                    if rdv_lookup and getattr(rdv_lookup, 'correo', None):
                        self.enviar_correo(
                            destino=rdv_lookup.correo,
                            asunto=correo_asunto,
                            cuerpo=correo_cuerpo
                        )
                except Exception:
                    pass
                
                return {
                    "success": False,
                    "error": "Falló la actualización del teléfono en Infobip",
                    "telefono_anterior": telefono_final,
                    "telefono_nuevo": telefono_nuevo,
                    "person_id": person_id
                }
            
            # Actualización exitosa - el teléfono final es el nuevo
            telefono_final = telefono_nuevo
            
            # También actualizar en BD local
            self._actualizar_telefono_people_local(people_a_usar.get("id"), telefono_nuevo)
        
        # Obtener conversación activa
        id_people_local = people_a_usar.get("id")
        
        # Si viene osc_conversation_id, usar esa conversación en lugar de buscar una activa
        conversation_id_proporcionado = osc.get("osc_conversation_id")
        
        if conversation_id_proporcionado:
            # Usar conversación existente proporcionada
            conversacion_activa = self._obtener_conversacion_por_id(conversation_id_proporcionado)
        else:
            # Buscar conversación activa (OPEN o WAITING más reciente) usando id local del People
            conversacion_activa = self._obtener_conversacion_activa_infobip(id_people_local)

        # 1. Buscar el RDV para obtener el external_id del agente
        rdv_party_number = osc.get("osc_rdv_party_number")
        print("rdv_party_number: ",rdv_party_number)
        agente_external_id = self._obtener_agente_external_id(rdv_party_number)
        print("agente_external_id1: ",agente_external_id)
        # 6. Buscar el id del RDV usando helper (maneja tipos)
        rdv = self._get_rdv_contact(osc)
        rdv_id_local = rdv.id if rdv else None
        # Obtener nombre del vendedor desde el RDV si está disponible
        seller_name = None
        if rdv:
            fn = getattr(rdv, 'first_name', None)
            ln = getattr(rdv, 'last_name', None)
            if fn or ln:
                seller_name = f"{fn or ''} {ln or ''}".strip()

        if conversacion_activa is None and not conversation_id_proporcionado:
            # No hay conversación activa → Crear nueva conversación
            
            # 2. Crear conversación en Infobip
            topic_str = f"Dni: {osc.get('osc_people_dni')} Telefono: {telefono_final} Nombre: (completar)"
            nueva_conversacion = self._crear_conversacion_infobip(
                telefono=telefono_final,
                agente_external_id=agente_external_id,
                topic=topic_str
            )
            
            if nueva_conversacion and nueva_conversacion.get("id"):
                conversation_id = nueva_conversacion.get("id")
                # Enviar plantilla WhatsApp inmediatamente después de crear la conversación (best-effort)


                # Enviar plantilla (simple) para la conversación existente
                # Comprobar si el lead_id que viene desde OSC ya existe en la tabla local `conversation_ext`.
                # Si existe, OMITIR el envío de la plantilla; si no existe, enviarla.
                lead_id = osc.get('osc_conversation_lead_id')
                enviar_plantilla = True
                if lead_id:
                    try:
                        from app.models.conversation_ext import ConversationExt

                        existe = (
                            self.db.query(ConversationExt)
                            .filter(ConversationExt.lead_id == lead_id)
                            .first()
                        )
                        if existe:
                            enviar_plantilla = False
                            print(f"Lead {lead_id} ya existe en conversation_ext; se omite envio de plantilla.")
                    except Exception as e:
                        # Si hay un error consultando la BD, registrarlo y continuar con el envío
                        print(f"Error consultando conversation_ext por lead_id {lead_id}: {e}")

                if enviar_plantilla:
                    try:
                        resp_template = self.enviar_template_conversacion(
                            to_number=telefono_final,
                            conversation_id=conversation_id,
                            template_name="robot_saludo_automatico",
                            seller_name=seller_name,
                            codigo_crm=osc.get('osc_conversation_codigo_crm'),
                            from_number=None,
                            agent_id=agente_external_id,
                            language="es_PE",
                        )
                        print(f"enviar_template_conversacion (existing) result: {resp_template}")
                    except Exception as e:
                        print(f"Error llamando enviar_template_conversacion (existing): {e}")



                # 3. Agregar nota con el comentario del flujo
                comentario = people_a_usar.get("comentario", "")
                if comentario:
                    self._agregar_nota_conversacion(conversation_id, comentario)
                
                # 4. Agregar nota con el código CRM
                codigo_crm = osc.get("osc_conversation_codigo_crm")
                if codigo_crm:
                    nombre_programa = self._obtener_nombre_programa(codigo_crm)
                    # Obtener el nombre del cliente por DNI (best-effort)
                    nombre_cliente = None
                    try:
                        nombre_cliente = self.obtener_nombre_por_dni(osc.get('osc_people_dni'))
                        if nombre_cliente:
                            print(f"Nombre cliente: {nombre_cliente}")
                    except Exception:
                        nombre_cliente = None

                    nombre_programa_text = nombre_programa or ""
                    nota = (
                        f"Dni Cliente: {osc.get('osc_people_dni')}\n"
                        f"Nombre Cliente: {nombre_cliente or ''}\n"
                        f"Codigo programa: {codigo_crm}\n"
                        f"Nombre Programa: {nombre_programa_text}"
                    )
                    self._agregar_nota_conversacion(conversation_id, nota)
                
                # 5. Agregar nota con el vendedor (party_number del RDV)
                if rdv_party_number:
                    if seller_name:
                        self._agregar_nota_conversacion(conversation_id, f"Vendedor - {seller_name}: {rdv_party_number}")
                    else:
                        self._agregar_nota_conversacion(conversation_id, f"Vendedor:{rdv_party_number}")
                

                
                # 7. Guardar conversación en BD local
                ConversationService.create_flexible(
                    db=self.db,
                    id_conversation=conversation_id,
                    id_people=id_people_local,
                    id_rdv=rdv_id_local,
                    estado_conversacion=nueva_conversacion.get("status"),
                    telefono_creado=telefono_final,
                    codigo_crm=codigo_crm,
                    lead_id=osc.get("osc_conversation_lead_id")
                )
                
                conversacion_activa = nueva_conversacion
                
        elif conversacion_activa is not None:
            # Existe conversación activa → Actualizar conversación
            conversation_id = conversacion_activa.get("id")

            #Aca quiero que se obtengan todos los 
# id	id_conversation	id_people	id_rdv	estado_conversacion	telefono_creado	proxima_sincronizacion	ultima_sincronizacion	codigo_crm	lead_id	created_at	updated_at
# 276	bcbdfdb4-9968-4ccc-80f1-ece2fc3c3d95	63953	NULL	OPEN	51968352136	2025-12-11 15:14:19.319004	NULL	NULL	NULL	2025-12-10 15:14:19.319409	2025-12-10 15:14:19.31
            
            # Lo que quiero es que usando el lead_id que pasas de osc, consultes si ese lead id existe en la tabla rdv_ext, si existe que ya no cree el mensaje de enviar template conversation sino que si lo envie
            #
            print(conversacion_activa)
            print("conversation_id",conversation_id)

            
            # 2. Agregar nota con el comentario del flujo
            comentario = people_a_usar.get("comentario", "")
            if comentario:
                self._agregar_nota_conversacion(conversation_id, comentario)
            
            # 3. Agregar nota con el nuevo código CRM
            codigo_crm = osc.get("osc_conversation_codigo_crm")
            if codigo_crm:
                nombre_programa = self._obtener_nombre_programa(codigo_crm)
                # Obtener e imprimir el nombre del cliente por DNI (best-effort)
                nombre_cliente = None
                try:
                    nombre_cliente = self.obtener_nombre_por_dni(osc.get('osc_people_dni'))
                    if nombre_cliente:
                        print(f"Nombre cliente: {nombre_cliente}")
                except Exception:
                    nombre_cliente = None

                nombre_programa_text = nombre_programa or ""
                nota = (
                    f"Dni Cliente: {osc.get('osc_people_dni')}\n"
                    f"Nombre Cliente: {nombre_cliente or ''}\n"
                    f"Codigo programa: {codigo_crm}\n"
                    f"Nombre Programa: {nombre_programa_text}"
                )
                self._agregar_nota_conversacion(conversation_id, nota)
            
            # 4. Agregar nota con el nuevo vendedor
            if rdv_party_number:
                if seller_name:
                    self._agregar_nota_conversacion(conversation_id, f"Vendedor {seller_name}:{rdv_party_number}")
                else:
                    self._agregar_nota_conversacion(conversation_id, f"Vendedor:{rdv_party_number}")
            
            # 5. Reasignar conversación al nuevo agente
            if agente_external_id:
                self._reasignar_conversacion_infobip(conversation_id, agente_external_id)

            # Enviar plantilla (simple) para la conversación existente
            # Comprobar si el lead_id que viene desde OSC ya existe en la tabla local `conversation_ext`.
            # Si existe, OMITIR el envío de la plantilla; si no existe, enviarla.
            lead_id = osc.get('osc_conversation_lead_id')
            enviar_plantilla = True
            if lead_id:
                try:
                    from app.models.conversation_ext import ConversationExt

                    existe = (
                        self.db.query(ConversationExt)
                        .filter(ConversationExt.lead_id == lead_id)
                        .first()
                    )
                    if existe:
                        enviar_plantilla = False
                        print(f"Lead {lead_id} ya existe en conversation_ext; se omite envio de plantilla.")
                except Exception as e:
                    # Si hay un error consultando la BD, registrarlo y continuar con el envío
                    print(f"Error consultando conversation_ext por lead_id {lead_id}: {e}")
        
            # 7. Guardar conversación en BD local
            ConversationService.create_flexible(
                db=self.db,
                id_conversation=conversation_id,
                id_people=id_people_local,
                id_rdv=rdv_id_local,
                estado_conversacion=conversacion_activa.get("status"),
                telefono_creado=telefono_final,
                codigo_crm=codigo_crm,
                lead_id=osc.get("osc_conversation_lead_id")
            )
            if enviar_plantilla:
                try:
                    resp_template = self.enviar_template_conversacion(
                        to_number=telefono_final,
                        conversation_id=conversation_id,
                        template_name="robot_saludo_automatico",
                        seller_name=seller_name,
                        codigo_crm=osc.get('osc_conversation_codigo_crm'),
                        from_number=None,
                        agent_id=agente_external_id,
                        language="es_PE",
                    )
                    print(f"enviar_template_conversacion (existing) result: {resp_template}")
                except Exception as e:
                    print(f"Error llamando enviar_template_conversacion (existing): {e}")
        self._agregar_etiqueta_conversacion(conversation_id)
        return {
            "success": True,
            "person_id": person_id,
            "telefono_final": telefono_final,
            "telefono_actualizado": requiere_actualizacion,
            "conversacion_activa": conversacion_activa,
            "osc_conversation_codigo_crm": osc.get("osc_conversation_codigo_crm"),
            "osc_rdv_party_number": osc.get("osc_rdv_party_number"),
            "osc_conversation_lead_id": osc.get("osc_conversation_lead_id"),
            "people_a_usar": people_a_usar
        }
    
    def _actualizar_telefono_people_infobip(self, person_id: str, telefono_nuevo: str) -> bool:
        """
        Actualiza el teléfono de un People en Infobip.
        
        Args:
            person_id: ID del People en Infobip
            telefono_nuevo: Nuevo teléfono a asignar
            
        Returns:
            True si se actualizó correctamente, False si falló
        """
        try:
            url = f"https://{settings.INFOBIP_API_HOST}/people/2/persons"
            headers = {
                "Authorization": f"App {settings.INFOBIP_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            params = {
                "identifier": person_id,
                "type": "ID"
            }
            
            payload = {
                "contactInformation": {
                    "phone": [
                        {"number": telefono_nuevo}
                    ]
                }
            }
            
            response = requests.put(url, headers=headers, params=params, json=payload, timeout=15)
            
            if response.status_code not in [200, 204]:
                print(f"Error actualizando teléfono en Infobip - Status: {response.status_code}, Response: {response.text}")
            
            return response.status_code in [200, 204]
            
        except Exception as e:
            print(f"Excepción actualizando teléfono en Infobip: {str(e)}")
            return False
    
    def _actualizar_telefono_people_local(self, people_id: int, telefono_nuevo: str) -> bool:
        """
        Actualiza el teléfono de un People en la BD local.
        
        Args:
            people_id: ID del People en BD local
            telefono_nuevo: Nuevo teléfono a asignar
            
        Returns:
            True si se actualizó correctamente, False si falló
        """
        try:
            from app.models.people_ext import PeopleExt
            people = self.db.query(PeopleExt).filter(PeopleExt.id == people_id).first()
            if people:
                people.telefono = telefono_nuevo
                self.db.commit()
                return True
            return False
        except Exception:
            self.db.rollback()
            return False
    
    def _obtener_conversaciones_infobip(self, person_id: str) -> list:
        """
        Obtiene las conversaciones de un People en Infobip.
        
        Args:
            person_id: ID del People en Infobip
            
        Returns:
            Lista de conversaciones
        """
        try:
            url = f"https://{settings.INFOBIP_API_HOST}/ccaas/1/conversations"
            headers = {
                "Authorization": f"App {settings.INFOBIP_API_KEY}",
                "Accept": "application/json"
            }
            params = {"personId": person_id}
            
            response = requests.get(url, headers=headers, params=params, timeout=15)
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            return data.get("conversations", [])
            
        except Exception:
            return []
    
    def _obtener_conversacion_activa_infobip(self, id_people_local: int) -> Optional[Dict[str, Any]]:
        """
        Obtiene la conversación activa más reciente de un People.
        
        Flujo:
        1. Buscar en tabla conversation_ext por id_people el registro más reciente (último creado)
        2. Tomar el id_conversation de ese registro
        3. Consultar el estado de esa conversación en la API de Infobip
        4. Si el estado es OPEN o WAITING, devolverlo
        
        Args:
            id_people_local: ID del People en la BD local (conversation_ext.id_people)
            
        Returns:
            Diccionario con la conversación activa o None si no hay o no está activa
        """
        try:
            from app.models.conversation_ext import ConversationExt
            
            # 1. Buscar la conversación más reciente en BD local por id_people
            conversacion_local = (
                self.db.query(ConversationExt)
                .filter(ConversationExt.id_people == id_people_local)
                .order_by(ConversationExt.created_at.desc())
                .first()
            )
            
            if not conversacion_local:
                return None
            
            # 2. Obtener el id_conversation
            conversation_id = conversacion_local.id_conversation
            
            if not conversation_id:
                return None
            
            # 3. Consultar estado de esa conversación en Infobip
            conversacion_infobip = self._obtener_conversacion_por_id_infobip(conversation_id)
            
            if not conversacion_infobip:
                return None
            
            # 4. Verificar si está en estado OPEN o WAITING
            estado = conversacion_infobip.get("status")
            if estado in ["OPEN", "WAITING","SOLVED"]:
                return conversacion_infobip
            
            return None
            
        except Exception as e:
            print(f"Error obteniendo conversación activa: {str(e)}")
            return None
    
    def _obtener_conversacion_por_id_infobip(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene una conversación específica de Infobip por su ID.
        
        Args:
            conversation_id: ID de la conversación en Infobip
            
        Returns:
            Diccionario con la conversación o None si no existe
        """
        try:
            url = f"https://{settings.INFOBIP_API_HOST}/ccaas/1/conversations/{conversation_id}"
            headers = {
                "Authorization": f"App {settings.INFOBIP_API_KEY}",
                "Accept": "application/json"
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error obteniendo conversación {conversation_id}: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Excepción obteniendo conversación: {str(e)}")
            return None
    
    def _obtener_conversacion_por_id(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene una conversación específica por su ID (wrapper de _obtener_conversacion_por_id_infobip).
        
        Args:
            conversation_id: ID de la conversación en Infobip
            
        Returns:
            Diccionario con la conversación o None si no existe
        """
        return self._obtener_conversacion_por_id_infobip(conversation_id)
    
    def _obtener_agente_external_id(self, rdv_party_number: Optional[int]) -> Optional[str]:
        """
        Obtiene el external_id del agente (RDV) buscando por party_number.
        
        Args:
            rdv_party_number: Party number del RDV
            
        Returns:
            El infobip_external_id del RDV o None si no existe
        """
        if not rdv_party_number:
            return None
        
        try:
            pn = int(rdv_party_number)
        except Exception:
            pn = None

        if pn is None:
            return None

        rdv = RdvService.find_by_party(
            db=self.db,
            party_number=pn
        )
        
        if rdv:
            return rdv.infobip_external_id
        return None
    
    def _crear_conversacion_infobip(
        self,
        telefono: str,
        agente_external_id: Optional[str] = None,
        topic: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Crea una nueva conversación en Infobip.

        Args:
            telefono: Teléfono del cliente (solo lo usamos como contexto, no se envía como campo dedicado).
            agente_external_id: ID del agente (en tu caso, el que mapeas a agentId).

        Returns:
            Diccionario con la conversación creada o None si falló
        """
        try:
            url = f"https://{settings.INFOBIP_API_HOST}/ccaas/1/conversations"
            headers = {
                "Authorization": f"App {settings.INFOBIP_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            payload: Dict[str, Any] = {
                # Campo oficial del endpoint
                "channel": "WHATSAPP",
                # Topic: usar el valor pasado (si se proporciona) o el fallback por teléfono
                "topic": topic if topic is not None else f"Conversación WhatsApp con {telefono}",
                # "priority": "NORMAL",  # opcional
            }
            print("agente_external_id: ",agente_external_id)
            if agente_external_id:
                # En la API el campo se llama agentId
                payload["agentId"] = agente_external_id

            response = requests.post(url, headers=headers, json=payload, timeout=15)

            if response.status_code in (200, 201):
                return response.json()
            else:
                print(
                    f"Error creando conversación: "
                    f"{response.status_code} - {response.text}"
                )
                return None

        except Exception as e:
            print(f"Excepción creando conversación: {str(e)}")
            return None

    def _agregar_nota_conversacion(self, conversation_id: str, nota: str) -> bool:
        """
        Agrega una nota a una conversación en Infobip.
        
        Args:
            conversation_id: ID de la conversación
            nota: Texto de la nota
            
        Returns:
            True si se agregó correctamente, False si falló
        """
        try:
            url = f"https://{settings.INFOBIP_API_HOST}/ccaas/1/conversations/{conversation_id}/notes"
            headers = {
                "Authorization": f"App {settings.INFOBIP_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            payload = {
                "content": nota
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            
            return response.status_code in [200, 201]
            
        except Exception:
            return False

    def _agregar_etiqueta_conversacion(self, conversation_id: str) -> bool:
        """
        Agrega una etiqueta (tag) a una conversación en Infobip.

        Args:
            conversation_id: ID de la conversación en Infobip
            etiqueta: Texto de la etiqueta a agregar

        Returns:
            True si se agregó correctamente, False si falló
        """
        try:
            url = f"https://{settings.INFOBIP_API_HOST}/ccaas/1/conversations/{conversation_id}/tags"
            headers = {
                "Authorization": f"App {settings.INFOBIP_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }


            # Payload según documentación Infobip: enviar 'tagName'
            payload = {"tagName": "CRM"}

            response = requests.post(url, headers=headers, json=payload, timeout=15)

            # Logs de depuración (similar al snippet de ejemplo)
            try:
                print("Add tag - Status:", response.status_code)
                print("Add tag - Body:", response.text)
            except Exception:
                pass

            return response.status_code in (200, 201, 204)

        except Exception:
            return False
    
    def _reasignar_conversacion_infobip(self, conversation_id: str, agente_external_id: str) -> bool:
        """
        Reasigna una conversación a un nuevo agente en Infobip usando el endpoint oficial:
        PUT /ccaas/1/conversations/{conversationId}/assignee
        """
        try:
            # Endpoint correcto según documentación
            url = (
                f"https://{settings.INFOBIP_API_HOST}"
                f"/ccaas/1/conversations/{conversation_id}/assignee"
            )

            headers = {
                "Authorization": f"App {settings.INFOBIP_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }

            # Campo correcto: agentId
            payload = {
                "agentId": agente_external_id
            }

            response = requests.put(url, headers=headers, json=payload, timeout=15)

            if response.status_code in (200, 204):
                return True
            else:
                print(
                    f"Error reasignando conversación: "
                    f"{response.status_code} - {response.text}"
                )
                return False

        except Exception as e:
            print(f"Excepción reasignando conversación: {str(e)}")
            return False

    
    def flujo_venta_pasiva(self) -> Dict[str, Any]:
        """
        Flujo de venta pasiva: Responsable comienza conversación
        
        Se trabaja netamente en Infobip, no hay lógica backend
        """
        return {
            "message": "Este flujo se trabaja netamente en infobip, no hay logica backend"
        }

    def enviar_template_conversacion(
        self,
        to_number: str,
        conversation_id: str,
        template_name: str = "mkt_bienvenida_v1",
        parameters: Optional[Dict[str, Any]] = None,
        from_number: Optional[str] = None,
        agent_id: Optional[str] = None,
        language: str = "es_PE",
        seller_name: Optional[str] = None,
        codigo_crm: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Envía un mensaje tipo TEMPLATE (WhatsApp) dentro de una conversación existente en Infobip.

        Retorna un diccionario con `success`, `status_code` y `body` o `error`.
        """
        try:
            url = f"https://{settings.INFOBIP_API_HOST}/ccaas/1/conversations/{conversation_id}/messages"
            headers = {
                "Authorization": f"App {settings.INFOBIP_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            if agent_id:
                headers["x-agent-id"] = agent_id

            # Construir parámetros si no se pasaron explícitamente
            if parameters is None:
                nombre_programa = None
                try:
                    if codigo_crm:
                        nombre_programa = self._obtener_nombre_programa(codigo_crm)
                except Exception:
                    nombre_programa = None

                parameters_payload = {
                    "{{1}}": seller_name or "",
                    "{{2}}": nombre_programa or "",
                }
            else:
                parameters_payload = parameters

            # Asegurar que el campo 'from' no sea vacío (Infobip lo valida)
            from_number_final = from_number or "51992948046"

            payload = {
                "from": from_number_final,
                "to": to_number,
                "channel": "WHATSAPP",
                "contentType": "TEMPLATE",
                "content": {
                    "templateName": template_name,
                    "language": language,
                    "parameters": [parameters_payload]
                }
            }

            resp = requests.post(url, headers=headers, json=payload, timeout=15)

            return {
                "success": resp.status_code in (200, 201),
                "status_code": resp.status_code,
                "body": resp.text,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}