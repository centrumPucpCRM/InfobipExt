"""
Script de sincronización general.

Ejecuta, en este orden:
  1. Backfill histórico hacia reportería externa.
  2. Sincronización de filas incompletas en conversation-lead-relation.
  3. Sincronización de sender-last-rdv.

Uso:
  - En el servidor (dentro del contenedor):
        docker compose exec api python sincronizar_general.py
    (o  docker-compose exec api python sincronizar_general.py )
  - Local:
        python sincronizar_general.py

Opcionalmente acepta parámetros para ajustar corte, límites y exclusiones.
"""
import os
import sys
import argparse
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import SessionLocal  # noqa: E402
from app.orchestrators.sales_orchestrator import SalesOrchestrator  # noqa: E402


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sincronizador general de InfobipExt")
    parser.add_argument("--cutoff-date", type=_parse_date, default=date(2026, 6, 7))
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--historico-limit", type=int, default=None)
    parser.add_argument("--reporteria-limit", type=int, default=None)
    parser.add_argument("--ultimo-rdv-limit", type=int, default=None)
    parser.add_argument("--exclude-lead", action="append", default=[])
    parser.add_argument("--exclude-phone", action="append", default=[])
    args = parser.parse_args()

    exclude_lead_ids = args.exclude_lead or ["2033645"]
    exclude_telefonos = args.exclude_phone or ["51960300000"]

    db = SessionLocal()
    try:
        orch = SalesOrchestrator(db)
        resumen = orch.sincronizar_general(
            cutoff_date=args.cutoff_date,
            batch_size=args.batch_size,
            historico_limit=args.historico_limit,
            reporteria_limit=args.reporteria_limit,
            ultimo_rdv_limit=args.ultimo_rdv_limit,
            exclude_lead_ids=exclude_lead_ids,
            exclude_telefonos=exclude_telefonos,
        )
        print(f"[sincronizar_general] FIN. Resumen={resumen}", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
