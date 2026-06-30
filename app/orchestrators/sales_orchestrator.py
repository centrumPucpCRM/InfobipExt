"""
Sales Orchestrator - Contiene los flujos de venta directamente
"""
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime, date, time as datetime_time
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

    # Número de Infobip (campo 'from' de las plantillas) según la cartera
    # (CTRCartera_c). Se almacena sin el prefijo '+' para que coincida con el
    # formato que espera Infobip en el campo 'from'.
    NUMEROS_INFOBIP_POR_CARTERA = {
        "ALTA_DIRECCION":  "51993263826",
        "PERU_REGIONES":   "51914158946",
        "ME_SECTORIAL":    "51993240119",
        "ME":              "51993240119",
        "MADEN":           "51993240119",
        "LIMA_GRADO":      "51914158946",
        "INCOMPANY":       "51993263826",
        "EXECUTIVE":       "51914158946",
        "EE_TEC_INN_AGL":  "51993459699",
        "EE_OPE_LOG_SCM":  "51993296673",
        "EE_MKT_VTS_COM":  "51993370025",
        "EE_FUERA_LIMA":   "51993296673",
        "EE_FNZ_CON_RIE":  "51993370025",
        "CENTRUMX_PUCP":   "51993240119",
        "EE_AD_INCOM_B2B": "51993263826",
        "EE_EDEX":         "51993459699",
        "EE_EST_GES_TAL":  "51984714442",
    }

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
    
    def asegurar_existe_etiqueta(self, name: str) -> bool:
        """
        Crea una etiqueta (tag) en Infobip si no existe.

        No es bloqueante: captura errores y devuelve False en fallo,
        pero trata el caso 'already exists' como no error.
        """
        try:
            url = f"https://{settings.INFOBIP_API_HOST}/ccaas/1/tags"
            headers = {
                "Authorization": f"App {settings.INFOBIP_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            payload = {"name": name}

            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            try:
                print("asegurar_existe_etiqueta - Status:", resp.status_code)
                print("asegurar_existe_etiqueta - Body:", resp.text)
            except Exception:
                pass

            # 200/201/204 -> creado/ok. 400 con mensaje de 'already exists' -> no bloquear.
            if resp.status_code in (200, 201, 204):
                return True
            if resp.status_code == 400 and "already exists" in (resp.text or ""):
                return True
            return False
        except Exception as e:
            print(f"Excepción asegurar_existe_etiqueta: {e}")
            return False

    def _buscar_cartera_jp(self, codigo_crm):
        """
        Consulta Oracle Sales Cloud para obtener los campos CTRCartera_c,
        CTRJefeDeProducto_c, CTRTipoPrograma_cMeaning y CTRModalidad_cMeaning
        del ProductGroup indicado por `codigo_crm`.

        Usa las credenciales en `settings` para no exponer secretos.
        """
        try:
            base_url = f"{settings.ORACLE_CRM_URL}/catalogProductGroups/"
            headers = {
                "Authorization": settings.ORACLE_CRM_AUTH,
                "Content-Type": "application/json",
            }
            params = {
                "onlyData": "true",
                "fields": "CTRCartera_c,CTRJefeDeProducto_c,CTRTipoPrograma_cMeaning,CTRModalidad_cMeaning",
                "q": f"ProductGroupId={codigo_crm}",
                "limit": 1,
            }
            resp = requests.get(base_url, headers=headers, params=params, timeout=10)
            if resp.status_code != 200:
                return {}
            data = resp.json()
            items = data.get("items") or []
            if not items:
                return {}
            return items[0]
        except Exception as e:
            print(f"Excepción _buscar_cartera_jp: {e}")
            return {}


    def _calcular_subdireccion(self, area: str, modalidad: str) -> str:
        """
        Calcula la Subdirección a partir de CTRArea_cMeaning y CTRModalidad_cMeaning.

        Args:
            area: Valor de CTRArea_cMeaning
            modalidad: Valor de CTRModalidad_cMeaning (ej: 'ASINCRONO')

        Returns:
            'CentrumX', 'Grado', 'Educación Ejecutiva', u 'Otro'
        """
        areas_grado = {
            'EXECUTIVE',
            'LIMA_GRADO',
            'ME',
            'PERU_REGIONES',
            'ME_SECTORIAL',
        }
        areas_ee = {
            'ALTA_DIRECCION',
            'EE_FUERA_LIMA',
            'EE_OPE_LOG_SCM',
            'EE_EST_GES_TAL',
            'EE_MKT_VTS_COM',
            'EE_FNZ_CON_RIE',
            'EE_TEC_INN_AGL',
            'EE_EDEX',
            'INCOMPANY',
        }

        if area in areas_grado:
            return 'CentrumX' if (modalidad or '').upper() == 'ASINCRONO' else 'Grado'
        if area in areas_ee:
            return 'Educación Ejecutiva'
        return 'Otro'

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
        #destinatarios = [destino,'isidorosantivanez@gmail.com','andre.zambrano@pucp.edu.pe', "gestordecuentascrmcentrum@pucp.edu.pe"]
        destinatarios = [destino,"gestordecuentascrmcentrum@pucp.edu.pe"]
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

    def _obtener_numero_infobip_por_cartera(self, cartera: Optional[str]) -> Optional[str]:
        """
        Devuelve el número de Infobip (campo 'from' de las plantillas) que
        corresponde a una cartera (CTRCartera_c).

        Args:
            cartera: Valor de CTRCartera_c (ej: 'ALTA_DIRECCION').

        Returns:
            El número asociado (sin '+') o None si la cartera no está mapeada.
        """
        if not cartera:
            return None
        return self.NUMEROS_INFOBIP_POR_CARTERA.get(cartera)

    def _extraer_telefono_principal(self, telefono_creado: Optional[str]) -> Optional[str]:
        """Devuelve el teléfono base desde el campo compuesto `telefono_creado`."""
        if not telefono_creado:
            return None
        telefono = telefono_creado.split(";")[0].strip()
        return telefono or None

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
        from_number_infobip = 0
        produccion = 0  # 1 = producción (usa la cartera real); 0 = prueba (número fijo)
        if produccion == 1:
            # Obtener la cartera (CTRCartera_c) del catálogo catalogProductGroups
            cartera = self._buscar_cartera_jp(osc_conversation_codigo_crm).get("CTRCartera_c")
            if cartera:
                print(f"Cartera para código {osc_conversation_codigo_crm}: {cartera}")
            else:
                print(f"No se encontró cartera para código {osc_conversation_codigo_crm}")
            # Número de Infobip ('from') según la cartera; si no está mapeada
            # queda None y enviar_template usará el número por defecto.
            from_number_infobip = self._obtener_numero_infobip_por_cartera(cartera)
            print(f"Número Infobip por cartera: {from_number_infobip}")
        else:
            from_number_infobip = "51992948046"
            print("Modo de prueba: no se consultará la cartera en Oracle Sales Cloud.")
            
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
                        f"Nota: Este lead se tiene que calificar desde el CRM, al no poder generar una vinculación directa con infobip."
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
            # Número Infobip (sender) resuelto por cartera; se usa para componer
            # telefono_creado ("telefono_usuario;telefono_infobip") y el lookup.
            "from_number_infobip": from_number_infobip,
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

        # Estos valores se usan en el bloque final (vincular/notificar/etiquetar).
        # Se inicializan aquí para que siempre estén definidos aunque no se entre
        # a ninguna rama (p. ej. si la creación de la conversación en Infobip falla).
        lead_id = osc.get('osc_conversation_lead_id')
        conversation_id = None

        # Número Infobip (sender) resuelto: si no hay número por cartera se usa el
        # default para que coincida con el 'from' realmente enviado.
        telefono_infobip = osc.get("from_number_infobip") or "51992948046"
        # telefono_creado se guarda como "telefono_usuario;telefono_infobip"
        telefono_creado_valor = f"{telefono_final};{telefono_infobip}"

        # Si viene osc_conversation_id, usar esa conversación en lugar de buscar una activa
        conversation_id_proporcionado = osc.get("osc_conversation_id")

        if conversation_id_proporcionado:
            # Usar conversación existente proporcionada
            conversacion_activa = self._obtener_conversacion_por_id(conversation_id_proporcionado)
        else:
            # Buscar conversación activa SOLO por la cadena compuesta
            # (telefono_usuario;telefono_infobip). Si el número Infobip es distinto,
            # no se reutiliza ninguna previa y se creará una conversación nueva.
            conversacion_activa = self._obtener_conversacion_activa_infobip(
                id_people_local,
                telefono_creado_compuesto=telefono_creado_valor,
            )

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
                            .filter(ConversationExt.telefono_creado == telefono_creado_valor)
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
                        resp_template = self._enviar_template_con_fallback(
                            to_number=telefono_final,
                            conversation_id=conversation_id,
                            template_name="robot_saludo_automatico",
                            seller_name=seller_name,
                            codigo_crm=osc.get('osc_conversation_codigo_crm'),
                            from_number=telefono_infobip,
                            agent_id=agente_external_id,
                            language="es_PE",
                        )
                        print(f"Resultado envío plantilla con fallback: {resp_template}")
                    except Exception as e:
                        print(f"Error enviando plantilla con fallback: {e}")



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
                    telefono_creado=telefono_creado_valor,
                    codigo_crm=codigo_crm,
                    lead_id=osc.get("osc_conversation_lead_id")
                )
                
                conversacion_activa = nueva_conversacion
                
        elif conversacion_activa is not None:
            # Existe conversación activa → Actualizar conversación
            conversation_id = conversacion_activa.get("id")
            print(conversacion_activa)
            print("conversation_id",conversation_id)

            # Verificar PRIMERO si el lead_id ya existe en conversation_ext
            # para evitar duplicar notas y plantilla cuando Oracle llama más de una vez
            lead_id = osc.get('osc_conversation_lead_id')
            lead_ya_registrado = False
            if lead_id:
                try:
                    from app.models.conversation_ext import ConversationExt

                    existe = (
                        self.db.query(ConversationExt)
                        .filter(ConversationExt.lead_id == lead_id)
                        .filter(ConversationExt.telefono_creado == telefono_creado_valor)
                        .first()
                    )
                    if existe:
                        lead_ya_registrado = True
                        print(f"Lead {lead_id} ya existe en conversation_ext; se omiten notas y plantilla.")
                except Exception as e:
                    print(f"Error consultando conversation_ext por lead_id {lead_id}: {e}")

            codigo_crm = osc.get("osc_conversation_codigo_crm")

            if not lead_ya_registrado:
                # 2. Agregar nota con el comentario del flujo
                comentario = people_a_usar.get("comentario", "")
                if comentario:
                    self._agregar_nota_conversacion(conversation_id, comentario)
                
                # 3. Agregar nota con el nuevo código CRM
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
            
            # 5. Reasignar conversación al nuevo agente (siempre, es idempotente)
            if agente_external_id:
                self._reasignar_conversacion_infobip(conversation_id, agente_external_id)

            # 7. Guardar conversación en BD local
            ConversationService.create_flexible(
                db=self.db,
                id_conversation=conversation_id,
                id_people=id_people_local,
                id_rdv=rdv_id_local,
                estado_conversacion=conversacion_activa.get("status"),
                telefono_creado=telefono_creado_valor,
                codigo_crm=codigo_crm,
                lead_id=osc.get("osc_conversation_lead_id")
            )
            if not lead_ya_registrado:
                try:
                    resp_template = self._enviar_template_con_fallback(
                        to_number=telefono_final,
                        conversation_id=conversation_id,
                        template_name="robot_saludo_automatico",
                        seller_name=seller_name,
                        codigo_crm=osc.get('osc_conversation_codigo_crm'),
                        from_number=telefono_infobip,
                        agent_id=agente_external_id,
                        language="es_PE",
                    )
                    print(f"Resultado envío plantilla con fallback: {resp_template}")
                except Exception as e:
                    print(f"Error enviando plantilla con fallback: {e}")

        if not conversation_id:
            # No se pudo crear u obtener la conversación en Infobip; no continuar
            # con vinculación/etiquetado para no usar un conversation_id inválido.
            print("No se obtuvo conversation_id (creación/obtención en Infobip falló); se omite vinculación y etiquetado.")
            return {
                "success": False,
                "error": "No se pudo crear u obtener la conversación en Infobip",
                "person_id": person_id,
                "telefono_final": telefono_final,
                "osc_conversation_lead_id": lead_id,
            }

        self._vincular_lead_conversation_id(lead_id,conversation_id)
        self._notificar_relacion_lead_conversacion(
            lead_id,
            conversation_id,
            sender=telefono_infobip,
            telefono_contacto=telefono_final,
        )
        # Registrar el último RDV por (telefono_contacto, sender) en la reportería externa
        self._registrar_ultimo_rdv_por_sender(
            telefono_contacto=telefono_final,
            sender=telefono_infobip,
            ultimo_rdv_number=rdv_party_number,
            lead_id=lead_id,
        )
        self._agregar_etiqueta_conversacion(conversation_id,"CRM")
        result=self._buscar_cartera_jp(codigo_crm)
        self.asegurar_existe_etiqueta(result["CTRCartera_c"])
        self.asegurar_existe_etiqueta(result["CTRJefeDeProducto_c"])
        self._agregar_etiqueta_conversacion(conversation_id,result["CTRCartera_c"])
        self._agregar_etiqueta_conversacion(conversation_id,result["CTRJefeDeProducto_c"])
        subdireccion = self._calcular_subdireccion(
            result.get("CTRCartera_c", ""),
            result.get("CTRModalidad_cMeaning", "")
        )
        self.asegurar_existe_etiqueta(subdireccion)
        self._agregar_etiqueta_conversacion(conversation_id, subdireccion)
        tipo_programa = result.get("CTRTipoPrograma_cMeaning", "")
        if tipo_programa:
            self.asegurar_existe_etiqueta(tipo_programa)
            self._agregar_etiqueta_conversacion(conversation_id, tipo_programa)
        self._asignar_pepople_agentPartyId(person_id, rdv.party_id if rdv else None)
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
    
    def _obtener_conversacion_activa_infobip(
        self,
        id_people_local: int,
        telefono_creado_compuesto: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene la conversación activa más reciente para el par
        (telefono_usuario;telefono_infobip).

        Matching estricto: solo se considera una conversación del mismo par
        (telefono_usuario;telefono_infobip). Si el número Infobip es distinto,
        no se reutiliza ninguna conversación previa → se creará una nueva.

        Flujo:
        1. Buscar en conversation_ext por la cadena compuesta `telefono_creado`
           (telefono_usuario;telefono_infobip) el registro más reciente.
        2. Tomar el id_conversation de ese registro.
        3. Consultar el estado de esa conversación en la API de Infobip.
        4. Si el estado es OPEN/WAITING/SOLVED, devolverlo.

        Args:
            id_people_local: ID del People en la BD local (conversation_ext.id_people)
            telefono_creado_compuesto: Cadena "telefono_usuario;telefono_infobip"

        Returns:
            Diccionario con la conversación activa o None si no hay o no está activa
        """
        try:
            from app.models.conversation_ext import ConversationExt

            conversacion_local = None

            # Buscar SOLO por la cadena compuesta (telefono_usuario;telefono_infobip).
            if telefono_creado_compuesto:
                conversacion_local = (
                    self.db.query(ConversationExt)
                    .filter(ConversationExt.telefono_creado == telefono_creado_compuesto)
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
                "queueId": "6e87a3c8-fc95-4ff2-bf65-41021b4789f5",

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

    def _agregar_etiqueta_conversacion(self, conversation_id: str,tag: str) -> bool:
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
            payload = {"tagName": f"{tag}"}

            response = requests.post(url, headers=headers, json=payload, timeout=15)

            # Logs de depuración (similar al snippet de ejemplo)
            try:
                print(payload)
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

    def _enviar_template_con_fallback(
        self,
        to_number: str,
        conversation_id: str,
        template_name: str = "robot_saludo_automatico",
        seller_name: Optional[str] = None,
        codigo_crm: Optional[str] = None,
        agent_id: Optional[str] = None,
        from_number: Optional[str] = None,
        language: str = "es_PE",
    ) -> Dict[str, Any]:
        """
        Envía una plantilla y si falla con error 7032 (mensaje no entregado),
        reintenea con 'crm_plantilla_utility' como fallback.
        
        Args:
            to_number: Número de teléfono destino
            conversation_id: ID de la conversación en Infobip
            template_name: Nombre de la plantilla principal
            seller_name: Nombre del vendedor
            codigo_crm: Código CRM del programa
            agent_id: ID del agente
            from_number: Número origen
            language: Idioma
            
        Returns:
            Diccionario con el resultado (status_code, body)
        """
        # Intentar con la plantilla principal
        resultado_principal = self.enviar_template_conversacion(
            to_number=to_number,
            conversation_id=conversation_id,
            template_name=template_name,
            seller_name=seller_name,
            codigo_crm=codigo_crm,
            agent_id=agent_id,
            from_number=from_number,
            language=language,
        )

        # Si es exitoso (HTTP 200 o 201), retornar
        if resultado_principal.get("status_code") in (200, 201):
            print(f"Plantilla '{template_name}' enviada exitosamente (status {resultado_principal.get('status_code')})")
            return resultado_principal
        
        # Falló el envío → intentar con plantilla de fallback
        body_text = resultado_principal.get("body", "")
        print(f"Error enviando plantilla '{template_name}' (status {resultado_principal.get('status_code')}): {body_text}")
        print(f"Intentando con plantilla fallback 'crm_plantilla_utility'...")
        
        resultado_fallback = self.enviar_template_conversacion(
            to_number=to_number,
            conversation_id=conversation_id,
            template_name="crm_plantilla_utility",
            seller_name=seller_name,
            codigo_crm=codigo_crm,
            agent_id=agent_id,
            from_number=from_number,
            language=language,
        )
        
        if resultado_fallback.get("status_code") in (200, 201):
            print(f"Plantilla fallback 'crm_plantilla_utility' enviada exitosamente (status {resultado_fallback.get('status_code')})")
        else:
            print(f"Plantilla fallback también falló (status {resultado_fallback.get('status_code')}): {resultado_fallback.get('body', 'Error desconocido')}")

        return resultado_fallback

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

        Retorna un diccionario con `status_code` y `body` (o `error`). Status 200 = éxito.
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
                "status_code": resp.status_code,
                "body": resp.text,
            }
        except Exception as e:
            return {"status_code": 0, "error": str(e)}

    def _vincular_lead_conversation_id(self, lead_id: str, conversation_id: str) -> bool:
        """
        Vincula un lead con un conversation_id actualizando el campo CTRIdConversacionInfobip_c en Oracle.
        
        Args:
            lead_id: LeadId del lead en Oracle
            conversation_id: ID de la conversación en Infobip
            
        Returns:
            True si se vinculó correctamente, False si falló
        """
        try:
            url_patch = f"{settings.ORACLE_CRM_URL}/leads/{lead_id}"
            headers = {
                "Authorization": settings.ORACLE_CRM_AUTH,
                "Content-Type": "application/json"
            }
            params = {
                "onlyData": "true"
            }
            payload = {
                "CTRIdConversacionInfobip_c": conversation_id
            }
            
            response_patch = requests.patch(url_patch, params=params, headers=headers, json=payload, timeout=15)
            
            if response_patch.status_code in [200, 204]:
                print(f"Lead {lead_id} vinculado exitosamente con conversación {conversation_id}")
                return True
            else:
                print(f"Error actualizando lead {lead_id}: {response_patch.status_code} - {response_patch.text}")
                return False
                
        except Exception as e:
            print(f"Excepción vinculando lead con conversación: {str(e)}")
            return False

    def _notificar_relacion_lead_conversacion(
        self,
        lead_id: str,
        conversation_id: str,
        sender: Optional[str] = None,
        telefono_contacto: Optional[str] = None,
    ) -> bool:
        """
        Envía la relación lead_id ↔ conversation_id al servicio de reportería externa.

        POST https://reporteria-comparativa.vercel.app/api/infobip-ext/conversation-lead-relation
        Body: {
            "infobip_conversation_id": "<conversation_id>",
            "lead_id": "<lead_id>",
            "sender": "<numero_infobip>",        # opcional
            "telefono_contacto": "<telefono_usuario>"  # opcional
        }

        Es best-effort: cualquier fallo se loguea pero no interrumpe el flujo principal.
        """
        if not lead_id or not conversation_id:
            print(f"_notificar_relacion_lead_conversacion: parámetros incompletos - lead_id={lead_id}, conversation_id={conversation_id}")
            return False

        try:
            response = requests.post(
                settings.REPORTERIA_URL,
                headers={
                    "Authorization": f"Bearer {settings.REPORTERIA_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={
                    "infobip_conversation_id": conversation_id,
                    "lead_id": lead_id,
                    "sender": sender,
                    "telefono_contacto": telefono_contacto,
                },
                timeout=10,
                allow_redirects=False,
            )
            print(f"_notificar_relacion_lead_conversacion: status={response.status_code} lead={lead_id} conv={conversation_id}")
            return response.status_code in (200, 201, 204)
        except Exception as e:
            print(f"_notificar_relacion_lead_conversacion: excepción - {e}")
            return False

    def _registrar_ultimo_rdv_por_sender(
        self,
        telefono_contacto: Optional[str],
        sender: Optional[str],
        ultimo_rdv_number: Optional[int],
        lead_id: Optional[str],
        actualizado_masivo: bool = False,
    ) -> bool:
        """
        Registra/actualiza el último RDV asociado al par (telefono_contacto, sender)
        en la reportería externa.

        POST https://reporteria-comparativa.vercel.app/api/infobip-ext/sender-last-rdv
        Body: {
            "telefono_contacto": "<telefono_usuario>",
            "sender": "<numero_infobip>",
            "ultimo_rdv_number": <party_number_del_rdv>,
            "lead_id": "<lead_id>",
            "actualizado_masivo": <bool>
        }
        El servidor hace UPSERT sobre (telefono_contacto, sender) y sella la fecha.

        `actualizado_masivo` distingue el origen del último escritor del par:
        True cuando lo escribe el sincronizador masivo (sincronizar_ultimo_rdv_por_sender,
        un estimado desde Oracle), False cuando lo escribe cualquier flujo orgánico
        (conversación real / reasignación) y por lo tanto es dato confirmado.

        Es best-effort: cualquier fallo se loguea pero no interrumpe el flujo principal.
        """
        if not telefono_contacto or not sender:
            print(f"_registrar_ultimo_rdv_por_sender: parámetros incompletos - telefono_contacto={telefono_contacto}, sender={sender}")
            return False

        try:
            response = requests.post(
                settings.REPORTERIA_SENDER_LAST_RDV_URL,
                headers={
                    "Authorization": f"Bearer {settings.REPORTERIA_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={
                    "telefono_contacto": telefono_contacto,
                    "sender": sender,
                    "ultimo_rdv_number": ultimo_rdv_number,
                    "lead_id": lead_id,
                    "actualizado_masivo": actualizado_masivo,
                },
                timeout=10,
                allow_redirects=False,
            )
            if response.status_code in (200, 201):
                print(f"_registrar_ultimo_rdv_por_sender: OK status={response.status_code} contacto={telefono_contacto} sender={sender} rdv={ultimo_rdv_number}")
                return True
            # Según el contrato, los errores vienen como {"error": "<texto>"}
            error_text = ""
            try:
                error_text = response.json().get("error", "")
            except Exception:
                error_text = response.text
            print(f"_registrar_ultimo_rdv_por_sender: error status={response.status_code} - {error_text}")
            return False
        except Exception as e:
            print(f"_registrar_ultimo_rdv_por_sender: excepción - {e}")
            return False

    def _registrar_ultimo_rdv_por_sender_desde_conversacion(
        self,
        conversation_id: str,
        party_number: Optional[int],
    ) -> bool:
        """
        Registra el último RDV por sender a partir de una conversación existente
        (caso reasignación de vendedor).

        Toma el registro más reciente de `conversation_ext` por `id_conversation`,
        parsea `telefono_creado` ("telefono_contacto;sender") y registra el nuevo
        `party_number` como último RDV de ese par.

        Best-effort: si la conversación no existe o `telefono_creado` no trae sender
        (formato antiguo sin ';'), se omite sin interrumpir.
        """
        try:
            conv = ConversationService.get_latest_by_external_id(self.db, conversation_id)
            if not conv or not conv.telefono_creado:
                print(f"_registrar_ultimo_rdv_por_sender_desde_conversacion: sin conversación/telefono_creado para conv={conversation_id}")
                return False

            partes = conv.telefono_creado.split(";")
            if len(partes) < 2 or not partes[1]:
                print(f"_registrar_ultimo_rdv_por_sender_desde_conversacion: telefono_creado sin sender (formato antiguo) conv={conversation_id} valor='{conv.telefono_creado}'")
                return False

            telefono_contacto = partes[0]
            sender = partes[1]
            return self._registrar_ultimo_rdv_por_sender(
                telefono_contacto=telefono_contacto,
                sender=sender,
                ultimo_rdv_number=party_number,
                lead_id=conv.lead_id,
            )
        except Exception as e:
            print(f"_registrar_ultimo_rdv_por_sender_desde_conversacion: excepción - {e}")
            return False

    def _obtener_cartera_lead(self, lead_number) -> Optional[str]:
        """
        Obtiene la cartera de un lead consultando Oracle por LeadNumber
        (campo CTRTipoDeCarteraLead_c). Devuelve None si no se encuentra.
        """
        try:
            url = f"{settings.ORACLE_CRM_URL}/leads"
            headers = {
                "Authorization": settings.ORACLE_CRM_AUTH,
                "Content-Type": "application/json",
            }
            params = {
                "q": f"LeadNumber={lead_number}",
                "fields": "CTRTipoDeCarteraLead_c",
                "onlyData": "true",
                "limit": 1,
            }
            r = requests.get(url, params=params, headers=headers, timeout=15)
            if r.status_code != 200:
                return None
            items = r.json().get("items", [])
            if not items:
                return None
            return items[0].get("CTRTipoDeCarteraLead_c") or None
        except Exception as e:
            print(f"_obtener_cartera_lead: excepción lead={lead_number} - {e}")
            return None

    def sincronizar_reporteria(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """
        Segunda etapa del flujo general.

        Sincroniza la reportería externa (conversation-lead-relation): rellena
        `telefono_contacto` y `sender` en las filas incompletas, usando datos
        locales y la cartera del lead (Oracle).

        - telefono_contacto: de conversation_ext local (por infobip_conversation_id).
        - sender: del telefono_creado compuesto local si existe; si no, de la
          cartera del lead (CTRTipoDeCarteraLead_c) -> NUMEROS_INFOBIP_POR_CARTERA.
          Carteras no mapeadas se omiten (no se escribe sender) y se reportan.

        Solo escribe los campos que pudo resolver (PATCH; el externo respeta
        anti-null). Best-effort por fila.

        Args:
            limit: máximo de filas incompletas a procesar en esta corrida.
        """
        from app.models.conversation_ext import ConversationExt

        # 1. Mapa local: id_conversation -> telefono_creado (más reciente)
        local: Dict[str, str] = {}
        for idc, tel in (
            self.db.query(ConversationExt.id_conversation, ConversationExt.telefono_creado)
            .filter(ConversationExt.telefono_creado.isnot(None))
            .order_by(ConversationExt.created_at.asc())
        ):
            if idc and tel:
                local[idc] = tel

        base = settings.REPORTERIA_URL  # conversation-lead-relation
        headers = {
            "Authorization": f"Bearer {settings.REPORTERIA_TOKEN}",
            "Content-Type": "application/json",
        }

        resumen: Dict[str, Any] = {
            "procesados": 0,
            "actualizados": 0,
            "sin_datos": 0,
            "errores": 0,
            "carteras_no_mapeadas": {},
        }
        cache_cartera: Dict[Any, Optional[str]] = {}
        page = 1
        total = 0
        print("sincronizar_reporteria: inicio")
        while True:
            try:
                r = requests.get(
                    base,
                    params={"page": page, "pageSize": 500, "incompletos": "true"},
                    headers=headers,
                    timeout=30,
                    allow_redirects=False,
                )
            except Exception as e:
                print(f"sincronizar_reporteria: GET excepción page={page} - {e}")
                break
            if r.status_code != 200:
                print(f"sincronizar_reporteria: GET error page={page} status={r.status_code} body={r.text[:200]}")
                break
            j = r.json()
            data = j.get("data", [])
            total = j.get("total", total)
            if not data:
                break

            for row in data:
                # Filtrado client-side por seguridad (si el filtro del externo no está activo)
                tiene_tel = bool(row.get("telefono_contacto"))
                tiene_sender = bool(row.get("sender"))
                if tiene_tel and tiene_sender:
                    continue

                resumen["procesados"] += 1
                cid = row.get("infobip_conversation_id")
                row_id = row.get("id")
                lead_id = row.get("lead_id")

                payload: Dict[str, Any] = {}
                sender_val = None

                tel_creado = local.get(cid)
                if tel_creado:
                    partes = tel_creado.split(";")
                    if not tiene_tel and partes[0]:
                        payload["telefono_contacto"] = partes[0]
                    if len(partes) > 1 and partes[1]:
                        sender_val = partes[1]  # sender ya viene en el compuesto local

                # sender por cartera del lead (si no lo sacamos del compuesto)
                if not tiene_sender and not sender_val and lead_id:
                    if lead_id in cache_cartera:
                        cartera = cache_cartera[lead_id]
                    else:
                        cartera = self._obtener_cartera_lead(lead_id)
                        cache_cartera[lead_id] = cartera
                    if cartera:
                        num = self._obtener_numero_infobip_por_cartera(cartera)
                        if num:
                            sender_val = num
                        else:
                            resumen["carteras_no_mapeadas"][cartera] = (
                                resumen["carteras_no_mapeadas"].get(cartera, 0) + 1
                            )

                if sender_val and not tiene_sender:
                    payload["sender"] = sender_val

                if not payload:
                    resumen["sin_datos"] += 1
                else:
                    try:
                        pr = requests.patch(
                            f"{base}/{row_id}",
                            json=payload,
                            headers=headers,
                            timeout=15,
                            allow_redirects=False,
                        )
                        if pr.status_code in (200, 201):
                            resumen["actualizados"] += 1
                        else:
                            resumen["errores"] += 1
                            print(f"sincronizar_reporteria: PATCH id={row_id} status={pr.status_code} body={pr.text[:150]}")
                    except Exception as e:
                        resumen["errores"] += 1
                        print(f"sincronizar_reporteria: PATCH excepción id={row_id} - {e}")

                if limit and resumen["procesados"] >= limit:
                    print(f"sincronizar_reporteria: alcanzado limit={limit}; resumen={resumen}")
                    return resumen

                if resumen["procesados"] % 100 == 0:
                    print(
                        "sincronizar_reporteria: progreso "
                        f"procesados={resumen['procesados']} actualizados={resumen['actualizados']} "
                        f"sin_datos={resumen['sin_datos']} errores={resumen['errores']}"
                    )

            if page * 500 >= total:
                break
            page += 1

        print(f"sincronizar_reporteria: completado; resumen={resumen}")
        return resumen

    def sincronizar_historico_conversaciones(
        self,
        cutoff_date: date = date(2026, 6, 7),
        batch_size: int = 500,
        limit: Optional[int] = None,
        exclude_lead_ids: Optional[list[str]] = None,
        exclude_telefonos: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        """
        Primera etapa del flujo general.

        Envía el histórico local a `conversation-lead-relation` por lotes,
        preservando `created_at` y `updated_at` originales.

        En esta etapa `sender` siempre se envía como `None`.
        """
        from app.models.conversation_ext import ConversationExt
        from sqlalchemy import func

        cutoff_dt = datetime.combine(cutoff_date, datetime_time.min)
        exclude_lead_set = {str(item).strip() for item in (exclude_lead_ids or []) if str(item).strip()}
        exclude_phone_set = {str(item).strip() for item in (exclude_telefonos or []) if str(item).strip()}
        batch_size = max(1, int(batch_size or 500))

        rows = (
            self.db.query(
                ConversationExt.id.label("id"),
                ConversationExt.id_conversation.label("id_conversation"),
                ConversationExt.lead_id.label("lead_id"),
                ConversationExt.telefono_creado.label("telefono_creado"),
                ConversationExt.created_at.label("created_at"),
                ConversationExt.updated_at.label("updated_at"),
                func.row_number().over(
                    partition_by=ConversationExt.id_conversation,
                    order_by=(ConversationExt.created_at.desc(), ConversationExt.id.desc()),
                ).label("rn"),
            )
            .filter(ConversationExt.lead_id.isnot(None))
            .filter(ConversationExt.telefono_creado.isnot(None))
            .filter(ConversationExt.telefono_creado != "")
            .filter(ConversationExt.created_at < cutoff_dt)
        )

        if exclude_lead_set:
            rows = rows.filter(~ConversationExt.lead_id.in_(exclude_lead_set))

        deduplicados = rows.subquery()
        candidatos = (
            self.db.query(
                deduplicados.c.id,
                deduplicados.c.id_conversation,
                deduplicados.c.lead_id,
                deduplicados.c.telefono_creado,
                deduplicados.c.created_at,
                deduplicados.c.updated_at,
            )
            .filter(deduplicados.c.rn == 1)
            .order_by(deduplicados.c.created_at.asc(), deduplicados.c.id.asc())
            .all()
        )

        base = settings.REPORTERIA_URL
        headers = {
            "Authorization": f"Bearer {settings.REPORTERIA_TOKEN}",
            "Content-Type": "application/json",
        }

        resumen: Dict[str, Any] = {
            "candidatos": 0,
            "enviados": 0,
            "lotes_enviados": 0,
            "lotes_error": 0,
            "excluidos_lead": 0,
            "excluidos_telefono": 0,
            "omitidos_sin_datos": 0,
        }
        batch: list[Dict[str, Any]] = []
        print("sincronizar_historico_conversaciones: inicio")

        def enviar_lote(lote: list[Dict[str, Any]]) -> None:
            if not lote:
                return
            try:
                resp = requests.post(
                    base,
                    headers=headers,
                    json=lote,
                    timeout=60,
                    allow_redirects=False,
                )
                if resp.status_code in (200, 201, 207):
                    resumen["lotes_enviados"] += 1
                    resumen["enviados"] += len(lote)
                    print(
                        "sincronizar_historico_conversaciones: lote enviado "
                        f"tamano={len(lote)} enviados={resumen['enviados']} "
                        f"lotes={resumen['lotes_enviados']} errores={resumen['lotes_error']}"
                    )
                else:
                    resumen["lotes_error"] += 1
                    print(f"sincronizar_historico_conversaciones: POST error status={resp.status_code} body={resp.text[:200]}")
            except Exception as e:
                resumen["lotes_error"] += 1
                print(f"sincronizar_historico_conversaciones: POST excepción - {e}")

        for row in candidatos:
            if limit is not None and resumen["candidatos"] >= limit:
                break

            resumen["candidatos"] += 1

            lead_id = str(row.lead_id).strip() if row.lead_id is not None else ""
            if lead_id in exclude_lead_set:
                resumen["excluidos_lead"] += 1
                continue

            telefono_principal = self._extraer_telefono_principal(row.telefono_creado)
            if telefono_principal and telefono_principal in exclude_phone_set:
                resumen["excluidos_telefono"] += 1
                continue

            if not telefono_principal:
                resumen["omitidos_sin_datos"] += 1
                continue

            batch.append(
                {
                    "infobip_conversation_id": row.id_conversation,
                    "lead_id": lead_id,
                    "telefono_contacto": telefono_principal,
                    "sender": None,
                    "created_at": row.created_at.isoformat(sep=" ") if row.created_at else None,
                    "updated_at": row.updated_at.isoformat(sep=" ") if row.updated_at else None,
                }
            )

            if len(batch) >= batch_size:
                enviar_lote(batch)
                batch = []

            if resumen["candidatos"] % 100 == 0:
                print(
                    "sincronizar_historico_conversaciones: progreso "
                    f"candidatos={resumen['candidatos']} enviados={resumen['enviados']} "
                    f"lotes={resumen['lotes_enviados']} errores={resumen['lotes_error']}"
                )

        if batch:
            enviar_lote(batch)

        print(f"sincronizar_historico_conversaciones: completado; resumen={resumen}")
        return resumen

    def _obtener_rdv_party_number_desde_lead(self, lead_id) -> Optional[int]:
        """
        Resuelve el party_number del RDV (vendedor) a partir del lead_id,
        consultando el campo OwnerPartyNumber del lead en Oracle.
        """
        try:
            url = f"{settings.ORACLE_CRM_URL}/leads"
            headers = {
                "Authorization": settings.ORACLE_CRM_AUTH,
                "Content-Type": "application/json",
            }
            params = {
                "q": f"LeadNumber={lead_id}",
                "fields": "OwnerPartyNumber",
                "onlyData": "true",
                "limit": 1,
            }
            r = requests.get(url, params=params, headers=headers, timeout=15)
            if r.status_code != 200:
                return None
            items = r.json().get("items", [])
            if not items:
                return None
            owner_party_number = items[0].get("OwnerPartyNumber")
            if not owner_party_number:
                return None
            return int(owner_party_number)
        except Exception as e:
            print(f"_obtener_rdv_party_number_desde_lead: excepción lead={lead_id} - {e}")
            return None

    def _obtener_pares_ya_sincronizados(self) -> set:
        """
        Lee sender-last-rdv y devuelve el set de pares (telefono_contacto, sender)
        con actualizado_masivo=True, es decir, ya puestos por el propio
        sincronizador masivo (no hace falta reprocesarlos).

        Cualquier par en False (confirmado por un evento orgánico) o que no
        exista todavía SÍ debe procesarse: el sincronizador manda y siempre
        lo fuerza a True.
        """
        ya_sincronizados = set()
        url = settings.REPORTERIA_SENDER_LAST_RDV_URL
        headers = {
            "Authorization": f"Bearer {settings.REPORTERIA_TOKEN}",
            "Content-Type": "application/json",
        }
        page = 1
        total = 0
        while True:
            try:
                r = requests.get(
                    url,
                    params={"page": page, "pageSize": 500},
                    headers=headers,
                    timeout=30,
                    allow_redirects=False,
                )
            except Exception as e:
                print(f"_obtener_pares_ya_sincronizados: GET excepción page={page} - {e}")
                break
            if r.status_code != 200:
                print(f"_obtener_pares_ya_sincronizados: GET error page={page} status={r.status_code} body={r.text[:200]}")
                break
            j = r.json()
            data = j.get("data", [])
            total = j.get("total", total)
            if not data:
                break

            for row in data:
                telefono_contacto = row.get("telefono_contacto")
                sender = row.get("sender")
                if not telefono_contacto or not sender:
                    continue
                if row.get("actualizado_masivo") is True:
                    ya_sincronizados.add((telefono_contacto, sender))

            if page * 500 >= total:
                break
            page += 1

        return ya_sincronizados

    def sincronizar_ultimo_rdv_por_sender(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """
        Tercera etapa del flujo general.

        Sincroniza la tabla externa "último RDV por sender" (sender-last-rdv)
        a partir de conversation-lead-relation: recorre las filas que ya tienen
        telefono_contacto + sender, agrupa por ese par (telefono_contacto, sender)
        y, usando el lead_id, resuelve el RDV (_obtener_rdv_party_number_desde_lead)
        para registrarlo vía _registrar_ultimo_rdv_por_sender (UPSERT externo, crea
        o actualiza según corresponda, marcando actualizado_masivo=True).

        El sincronizador manda: fuerza a True cualquier par que esté en False
        (confirmado orgánicamente) o que no exista todavía. Solo se saltan los
        pares que ya están en True (puestos por una corrida anterior del propio
        sincronizador), para no reprocesar todo en cada corrida.

        Si para un mismo par (telefono_contacto, sender) existen varias filas en
        conversation-lead-relation (varias conversaciones a lo largo del tiempo),
        se usa el lead_id de la fila más reciente (mayor id), por si el cliente
        pasó a un lead más nuevo.

        Los pares que conversation-lead-relation no tiene completos (sender o
        telefono_contacto en null, o ni siquiera registrados) se rellenan con
        mi BD local (conversation_ext, vía telefono_creado="telefono;sender" +
        lead_id), solo como fallback: si el par ya vino completo desde
        conversation-lead-relation, ese gana.

        Args:
            limit: máximo de pares (telefono_contacto, sender) a procesar en esta corrida.
        """
        from app.models.conversation_ext import ConversationExt

        base = settings.REPORTERIA_URL  # conversation-lead-relation
        headers = {
            "Authorization": f"Bearer {settings.REPORTERIA_TOKEN}",
            "Content-Type": "application/json",
        }

        resumen: Dict[str, Any] = {
            "pares_encontrados": 0,
            "ya_sincronizados": 0,
            "procesados": 0,
            "actualizados": 0,
            "sin_rdv": 0,
            "errores": 0,
        }
        cache_rdv: Dict[Any, Optional[int]] = {}
        # (telefono_contacto, sender) -> (lead_id, id_fila_mas_reciente)
        pares: Dict[tuple, tuple] = {}

        ya_sincronizados = self._obtener_pares_ya_sincronizados()
        print("sincronizar_ultimo_rdv_por_sender: inicio")

        page = 1
        total = 0
        while True:
            try:
                r = requests.get(
                    base,
                    params={"page": page, "pageSize": 500},
                    headers=headers,
                    timeout=30,
                    allow_redirects=False,
                )
            except Exception as e:
                print(f"sincronizar_ultimo_rdv_por_sender: GET excepción page={page} - {e}")
                break
            if r.status_code != 200:
                print(f"sincronizar_ultimo_rdv_por_sender: GET error page={page} status={r.status_code} body={r.text[:200]}")
                break
            j = r.json()
            data = j.get("data", [])
            total = j.get("total", total)
            if not data:
                break

            for row in data:
                telefono_contacto = row.get("telefono_contacto")
                sender = row.get("sender")
                if not telefono_contacto or not sender:
                    continue
                row_id = row.get("id") or 0
                key = (telefono_contacto, sender)
                actual = pares.get(key)
                if actual is None or row_id > actual[1]:
                    pares[key] = (row.get("lead_id"), row_id)

            if page * 500 >= total:
                break
            page += 1

        # Fallback: pares que conversation-lead-relation no tiene completos,
        # rellenados desde mi BD local (no pisa lo que ya vino completo arriba).
        for telefono_creado, lead_id_local in (
            self.db.query(ConversationExt.telefono_creado, ConversationExt.lead_id)
            .filter(ConversationExt.telefono_creado.isnot(None))
            .filter(ConversationExt.lead_id.isnot(None))
            .order_by(ConversationExt.created_at.asc())
        ):
            if not telefono_creado or not lead_id_local:
                continue
            partes = telefono_creado.split(";")
            if len(partes) < 2 or not partes[0] or not partes[1]:
                continue
            key = (partes[0], partes[1])
            if key not in pares:
                pares[key] = (lead_id_local, 0)

        resumen["pares_encontrados"] = len(pares)

        for (telefono_contacto, sender), (lead_id, _row_id) in pares.items():
            if (telefono_contacto, sender) in ya_sincronizados:
                resumen["ya_sincronizados"] += 1
                continue

            resumen["procesados"] += 1

            if lead_id in cache_rdv:
                rdv_party_number = cache_rdv[lead_id]
            else:
                rdv_party_number = self._obtener_rdv_party_number_desde_lead(lead_id)
                cache_rdv[lead_id] = rdv_party_number

            if not rdv_party_number:
                resumen["sin_rdv"] += 1
            else:
                ok = self._registrar_ultimo_rdv_por_sender(
                    telefono_contacto=telefono_contacto,
                    sender=sender,
                    ultimo_rdv_number=rdv_party_number,
                    lead_id=lead_id,
                    actualizado_masivo=True,
                )
                if ok:
                    resumen["actualizados"] += 1
                else:
                    resumen["errores"] += 1

            if resumen["procesados"] % 100 == 0:
                print(
                    "sincronizar_ultimo_rdv_por_sender: progreso "
                    f"procesados={resumen['procesados']} actualizados={resumen['actualizados']} "
                    f"sin_rdv={resumen['sin_rdv']} errores={resumen['errores']}"
                )

            if limit and resumen["procesados"] >= limit:
                print(f"sincronizar_ultimo_rdv_por_sender: alcanzado limit={limit}; resumen={resumen}")
                return resumen

        print(f"sincronizar_ultimo_rdv_por_sender: completado; resumen={resumen}")
        return resumen

    def sincronizar_general(
        self,
        cutoff_date: date = date(2026, 6, 7),
        batch_size: int = 500,
        historico_limit: Optional[int] = None,
        reporteria_limit: Optional[int] = None,
        ultimo_rdv_limit: Optional[int] = None,
        exclude_lead_ids: Optional[list[str]] = None,
        exclude_telefonos: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        """
        Orquesta los 3 sincronizadores en el orden lógico acordado:
        1. Histórico
        2. Reportería incompleta
        3. Último RDV por sender
        """
        historico = self.sincronizar_historico_conversaciones(
            cutoff_date=cutoff_date,
            batch_size=batch_size,
            limit=historico_limit,
            exclude_lead_ids=exclude_lead_ids,
            exclude_telefonos=exclude_telefonos,
        )
        reporteria = self.sincronizar_reporteria(limit=reporteria_limit)
        ultimo_rdv = self.sincronizar_ultimo_rdv_por_sender(limit=ultimo_rdv_limit)

        return {
            "historico": historico,
            "reporteria": reporteria,
            "ultimo_rdv": ultimo_rdv,
        }

    def _asignar_pepople_agentPartyId(self, person_id: Optional[str], rdv_party_id: Optional[int]) -> bool:
        """
        Asigna el agentPartyId al People en Infobip.
        
        Args:
            person_id: ID del People en Infobip (infobip_id)
            rdv_party_id: Party ID del agente/RDV en Oracle (rdv_ext.party_id)
        
        Returns:
            True si se procesó correctamente, False si falló
        """
        if not person_id or not rdv_party_id:
            print(f"_asignar_pepople_agentPartyId: Faltan parámetros - person_id: {person_id}, rdv_party_id: {rdv_party_id}")
            return False
        
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
                "customAttributes": {
                    "agente_id": str(rdv_party_id)
                }
            }
            
            response = requests.patch(url, headers=headers, params=params, json=payload, timeout=15)
            
            if response.status_code in [200, 204]:
                print(f"_asignar_pepople_agentPartyId: Exitoso - person_id: {person_id}, rdv_party_id: {rdv_party_id}")
                return True
            else:
                print(f"_asignar_pepople_agentPartyId: Error {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"Error en _asignar_pepople_agentPartyId: {str(e)}")
            return False