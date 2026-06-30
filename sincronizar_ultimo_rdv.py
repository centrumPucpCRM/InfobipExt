"""
Script de sincronización de la tabla externa "último RDV por sender" (sender-last-rdv).

Recorre los pares (telefono_contacto, sender) presentes en conversation-lead-relation,
resuelve el RDV vigente a partir del lead_id (_obtener_rdv_party_number_desde_lead) y
hace UPSERT en sender-last-rdv vía _registrar_ultimo_rdv_por_sender (crea si no existe,
actualiza si ya existe).

Uso:
  - En el servidor (dentro del contenedor):
        docker compose exec api python sincronizar_ultimo_rdv.py
    (o  docker-compose exec api python sincronizar_ultimo_rdv.py )
  - Local:
        python sincronizar_ultimo_rdv.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import SessionLocal  # noqa: E402
from app.orchestrators.sales_orchestrator import SalesOrchestrator  # noqa: E402


def main():
    db = SessionLocal()
    try:
        orch = SalesOrchestrator(db)
        resumen = orch.sincronizar_ultimo_rdv_por_sender()
        print(f"[sincronizar_ultimo_rdv] FIN. Resumen={resumen}", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
