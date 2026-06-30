"""
Script de migración histórica de conversaciones a Reportería.

Paso 1 del flujo general: extrae del SQLite local las conversaciones
anteriores al corte (una por id_conversation, la más reciente) y las
envía en lotes al endpoint conversation-lead-relation de Reportería.

Solo envía las que aún no existen en Reportería (skip-set por
infobip_conversation_id). sender siempre va como null; el sincronizador
de reportería (paso 2) completa ese campo.

Uso:
  - En el servidor (dentro del contenedor):
        docker-compose exec api python migrar_historico.py
  - Local:
        python migrar_historico.py
  - Con opciones:
        python migrar_historico.py --limit 100
        python migrar_historico.py --cutoff-date 2026-06-07 --batch-size 200
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
    parser = argparse.ArgumentParser(description="Migración histórica de conversaciones a Reportería")
    parser.add_argument("--cutoff-date", type=_parse_date, default=date(2026, 6, 7),
                        help="Fecha de corte exclusiva (default: 2026-06-07)")
    parser.add_argument("--batch-size", type=int, default=500,
                        help="Tamaño de cada lote (máx 500, default: 500)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Límite de candidatos a procesar (default: todos)")
    parser.add_argument("--exclude-lead", action="append", default=[],
                        help="Lead ID a excluir (repetible)")
    parser.add_argument("--exclude-phone", action="append", default=[],
                        help="Teléfono a excluir (repetible)")
    args = parser.parse_args()

    exclude_lead_ids = args.exclude_lead or ["2033645"]
    exclude_telefonos = args.exclude_phone or ["51960300000"]

    db = SessionLocal()
    try:
        orch = SalesOrchestrator(db)
        resumen = orch.sincronizar_historico_conversaciones(
            cutoff_date=args.cutoff_date,
            batch_size=args.batch_size,
            limit=args.limit,
            exclude_lead_ids=exclude_lead_ids,
            exclude_telefonos=exclude_telefonos,
        )
        print(f"[migrar_historico] FIN. Resumen={resumen}", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
