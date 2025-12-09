"""
Mensaje Service - Business logic for Mensaje operations and Infobip sync
"""
import json
import http.client
from typing import List, Optional, Tuple
from datetime import datetime
from dateutil import parser as dateutil_parser
from sqlalchemy.orm import Session

from app.models.mensaje_ext import MensajeExt
from app.schemas.mensaje_ext import MensajeExtCreate
from app.core.config import settings


class MensajeService:
    """Service for Mensaje business logic and Infobip sync"""
    
    # Infobip API config
    HOST = settings.INFOBIP_API_HOST
    API_KEY = settings.INFOBIP_API_KEY
    
    @staticmethod
    def _get_headers() -> dict:
        """Headers para Infobip API"""
        return {
            "Authorization": f"App {MensajeService.API_KEY}",
            "Accept": "application/json"
        }
    
    @staticmethod
    def _fetch_json(path: str) -> dict:
        """Fetch JSON desde Infobip API"""
        conn = http.client.HTTPSConnection(MensajeService.HOST)
        conn.request("GET", path, headers=MensajeService._get_headers())
        res = conn.getresponse()
        raw_body = res.read().decode("utf-8")
        conn.close()
        
        if res.status != 200:
            raise Exception(
                f"Error {res.status} {res.reason} al llamar {path}. Body: {raw_body}"
            )
        
        try:
            return json.loads(raw_body)
        except json.JSONDecodeError:
            raise Exception(f"No se pudo parsear JSON para {path}: {raw_body}")
    
    @staticmethod
    def fetch_messages_from_infobip(conversation_id: str,
                                        page_size: int = 200,
                                        max_pages: int = 100) -> List[dict]:
        """
        Obtiene TODOS los mensajes de una conversación desde Infobip,
        paginando hasta agotar los resultados.

        Args:
            conversation_id: ID de la conversación en Infobip.
            page_size: Cantidad de mensajes por página (parámetro 'limit').
            max_pages: Límite de páginas a consultar como salvavidas.

        Returns:
            Lista con todos los mensajes de la conversación.
        """
        all_messages: List[dict] = []
        page = 0

        while page < max_pages:
            # La API de Infobip usa parámetros 'page' y 'limit' para paginación.
            # 'orderBy=id:ASC' para orden ascendente por id.
            path = (
                f"/ccaas/1/conversations/{conversation_id}/messages"
                f"?page={page}&limit={page_size}&orderBy=id:ASC"
            )

            data = MensajeService._fetch_json(path) or {}
            page_messages = data.get("messages", []) or []

            if not page_messages:
                # No hay más mensajes en esta página -> salir
                break

            all_messages.extend(page_messages)

            # Si vino menos que el límite, ya no hay más páginas
            if len(page_messages) < page_size:
                break

            page += 1

        return all_messages

    @staticmethod
    def fetch_messages_from_infobip(conversation_id: str,
                                    page_size: int = 200,
                                    max_pages: int = 100) -> list[dict]:
        """
        Obtiene TODOS los mensajes de una conversación desde Infobip,
        paginando hasta agotar los resultados.
        """
        all_messages: list[dict] = []
        page = 0

        while page < max_pages:
            path = (
                f"/ccaas/1/conversations/{conversation_id}/messages"
                f"?page={page}&limit={page_size}&orderBy=id:ASC"
            )

            data = MensajeService._fetch_json(path) or {}
            page_messages = data.get("messages", []) or []

            if not page_messages:
                break

            all_messages.extend(page_messages)

            if len(page_messages) < page_size:
                break

            page += 1

        return all_messages

    @staticmethod
    def fetch_notes_from_infobip(conversation_id: str,
                                 page_size: int = 200,
                                 max_pages: int = 100) -> List[dict]:
        """
        Obtiene TODAS las notas de una conversación desde Infobip,
        paginando hasta agotar los resultados.
        """
        all_notes: List[dict] = []
        page = 0

        while page < max_pages:
            path = (
                f"/ccaas/1/conversations/{conversation_id}/notes"
                f"?page={page}&limit={page_size}"
            )

            data = MensajeService._fetch_json(path) or {}
            page_notes = data.get("notes", []) or []

            if not page_notes:
                break

            all_notes.extend(page_notes)

            if len(page_notes) < page_size:
                break

            page += 1

        return all_notes

    
    @staticmethod
    def get_existing_infobip_ids(db: Session, id_conversation: str) -> set:
        """Obtiene set de infobip_message_id ya existentes para una conversación"""
        existing = db.query(MensajeExt.infobip_message_id).filter(
            MensajeExt.id_conversation == id_conversation,
            MensajeExt.infobip_message_id.isnot(None)
        ).all()
        return {row[0] for row in existing}
    
    @staticmethod
    def sync_mensajes_from_infobip(db: Session, id_conversation: str) -> Tuple[int, int]:
        """
        Sincroniza mensajes y notas de Infobip a mensaje_ext.
        
        1. Obtiene todos los mensajes y notas de Infobip
        2. Verifica cuáles ya existen en BD (por infobip_message_id)
        3. Inserta solo los nuevos
        
        Returns:
            Tuple[int, int]: (total_from_infobip, nuevos_insertados)
        """
        # 1. Obtener IDs ya existentes en BD
        existing_ids = MensajeService.get_existing_infobip_ids(db, id_conversation)
        
        # 2. Obtener mensajes y notas de Infobip
        try:
            messages = MensajeService.fetch_messages_from_infobip(id_conversation)
        except Exception as e:
            print(f"Error obteniendo mensajes de Infobip: {e}")
            messages = []
        
        try:
            notes = MensajeService.fetch_notes_from_infobip(id_conversation)
        except Exception as e:
            print(f"Error obteniendo notas de Infobip: {e}")
            notes = []
        
        total_from_infobip = len(messages) + len(notes)
        nuevos_insertados = 0
        
        # 3. Procesar mensajes
        for msg in messages:
            infobip_id = msg.get("id")
            if not infobip_id or infobip_id in existing_ids:
                continue  # Ya existe, saltar
            
            # Extraer contenido
            content = msg.get("content")
            if isinstance(content, dict):
                texto = content.get("text") or json.dumps(content, ensure_ascii=False)
            else:
                texto = content
            
            # Parsear fecha de Infobip
            created_at_infobip = None
            if msg.get("createdAt"):
                try:
                    created_at_infobip = dateutil_parser.parse(msg.get("createdAt"))
                except:
                    pass
            
            # Crear registro
            nuevo_mensaje = MensajeExt(
                id_conversation=id_conversation,
                tipo="MESSAGE",
                contenido=texto,
                direccion=msg.get("direction"),  # INBOUND, OUTBOUND
                remitente=msg.get("from") or msg.get("authorId"),
                infobip_message_id=infobip_id,
                created_at_infobip=created_at_infobip
            )
            db.add(nuevo_mensaje)
            nuevos_insertados += 1
        
        # 4. Procesar notas
        for note in notes:
            infobip_id = note.get("id")
            if not infobip_id or infobip_id in existing_ids:
                continue  # Ya existe, saltar
            
            # Parsear fecha de Infobip
            created_at_infobip = None
            if note.get("createdAt"):
                try:
                    created_at_infobip = dateutil_parser.parse(note.get("createdAt"))
                except:
                    pass
            
            # Crear registro
            nueva_nota = MensajeExt(
                id_conversation=id_conversation,
                tipo="NOTE",
                contenido=note.get("content"),
                direccion=note.get("type"),  # INTERNAL
                remitente=note.get("agentId"),
                infobip_message_id=infobip_id,
                created_at_infobip=created_at_infobip
            )
            db.add(nueva_nota)
            nuevos_insertados += 1
        
        # 5. Commit
        if nuevos_insertados > 0:
            db.commit()
        
        return total_from_infobip, nuevos_insertados
    
    # ==================== CRUD ====================
    
    @staticmethod
    def create(db: Session, mensaje_data: MensajeExtCreate) -> MensajeExt:
        """Create a new Mensaje"""
        db_mensaje = MensajeExt(**mensaje_data.model_dump())
        db.add(db_mensaje)
        db.commit()
        db.refresh(db_mensaje)
        return db_mensaje
    
    @staticmethod
    def get_by_id(db: Session, mensaje_id: int) -> Optional[MensajeExt]:
        """Get Mensaje by ID"""
        return db.query(MensajeExt).filter(MensajeExt.id == mensaje_id).first()
    
    @staticmethod
    def get_by_conversation(db: Session, id_conversation: str) -> List[MensajeExt]:
        """Get all Mensajes for a conversation ordered by Infobip timestamp"""
        return db.query(MensajeExt).filter(
            MensajeExt.id_conversation == id_conversation
        ).order_by(MensajeExt.created_at_infobip.asc()).all()
    
    @staticmethod
    def get_by_infobip_id(db: Session, infobip_message_id: str) -> Optional[MensajeExt]:
        """Get Mensaje by Infobip message ID"""
        return db.query(MensajeExt).filter(
            MensajeExt.infobip_message_id == infobip_message_id
        ).first()
    
    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100) -> List[MensajeExt]:
        """List Mensajes with pagination"""
        return db.query(MensajeExt).offset(skip).limit(limit).all()
    
    @staticmethod
    def delete(db: Session, mensaje_id: int) -> bool:
        """Delete a Mensaje"""
        db_mensaje = MensajeService.get_by_id(db, mensaje_id)
        if not db_mensaje:
            return False
        db.delete(db_mensaje)
        db.commit()
        return True
    
    @staticmethod
    def count_by_conversation(db: Session, id_conversation: str) -> int:
        """Count mensajes for a conversation"""
        return db.query(MensajeExt).filter(
            MensajeExt.id_conversation == id_conversation
        ).count()
