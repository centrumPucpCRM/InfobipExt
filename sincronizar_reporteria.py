"""
Script de sincronización / backfill de la reportería externa (conversation-lead-relation).

Barrido completo: recorre TODAS las filas incompletas (sin telefono_contacto y/o sin
sender) y las completa:
  - telefono_contacto: del telefono_creado local (por infobip_conversation_id).
  - sender: del compuesto local si existe, o de la cartera del lead
    (CTRTipoDeCarteraLead_c) mapeada a número Infobip.

Termina cuando una pasada no agrega ninguna fila nueva (control de ya-vistas).
Best-effort por fila; las carteras no mapeadas se omiten y se reportan al final.

Uso:
  - En el servidor (dentro del contenedor):
        docker compose exec api python sincronizar_reporteria.py
    (o  docker-compose exec api python sincronizar_reporteria.py )
  - Local:
        python sincronizar_reporteria.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.orchestrators.sales_orchestrator import SalesOrchestrator  # noqa: E402
from app.models.conversation_ext import ConversationExt  # noqa: E402


def main():
    db = SessionLocal()
    orch = SalesOrchestrator(db)

    # Mapa local: id_conversation -> telefono_creado (más reciente)
    local = {}
    for idc, tel in (
        db.query(ConversationExt.id_conversation, ConversationExt.telefono_creado)
        .filter(ConversationExt.telefono_creado.isnot(None))
        .order_by(ConversationExt.created_at.asc())
    ):
        if idc and tel:
            local[idc] = tel
    print(f"[sync] conversaciones locales con telefono: {len(local)}", flush=True)

    base = settings.REPORTERIA_URL
    headers = {
        "Authorization": f"Bearer {settings.REPORTERIA_TOKEN}",
        "Content-Type": "application/json",
    }

    seen = set()
    cache = {}
    tot = {"procesados": 0, "actualizados": 0, "sin_datos": 0, "errores": 0, "carteras_no_mapeadas": {}}
    sweep = 0

    try:
        while True:
            sweep += 1
            nuevos = 0
            page = 1
            total = 0
            while True:
                try:
                    r = requests.get(
                        base,
                        params={"incompletos": "true", "page": page, "pageSize": 500},
                        headers=headers,
                        timeout=30,
                        allow_redirects=False,
                    )
                except Exception as e:
                    print(f"[sync] GET excepcion page={page} - {e}", flush=True)
                    break
                if r.status_code != 200:
                    print(f"[sync] GET error page={page} status={r.status_code} {r.text[:150]}", flush=True)
                    break
                j = r.json()
                data = j.get("data", [])
                total = j.get("total", total)
                if not data:
                    break
                for row in data:
                    rid = row.get("id")
                    if rid in seen:
                        continue
                    if row.get("telefono_contacto") and row.get("sender"):
                        continue
                    seen.add(rid)
                    nuevos += 1
                    tot["procesados"] += 1
                    cid = row.get("infobip_conversation_id")
                    lead = row.get("lead_id")
                    payload = {}
                    sender_val = None

                    telc = local.get(cid)
                    if telc:
                        partes = telc.split(";")
                        if not row.get("telefono_contacto") and partes[0]:
                            payload["telefono_contacto"] = partes[0]
                        if len(partes) > 1 and partes[1]:
                            sender_val = partes[1]

                    if not row.get("sender") and not sender_val and lead:
                        if lead in cache:
                            cart = cache[lead]
                        else:
                            cart = orch._obtener_cartera_lead(lead)
                            cache[lead] = cart
                        if cart:
                            num = orch._obtener_numero_infobip_por_cartera(cart)
                            if num:
                                sender_val = num
                            else:
                                tot["carteras_no_mapeadas"][cart] = tot["carteras_no_mapeadas"].get(cart, 0) + 1

                    if sender_val and not row.get("sender"):
                        payload["sender"] = sender_val

                    if not payload:
                        tot["sin_datos"] += 1
                    else:
                        try:
                            pr = requests.patch(
                                f"{base}/{rid}",
                                json=payload,
                                headers=headers,
                                timeout=15,
                                allow_redirects=False,
                            )
                            if pr.status_code in (200, 201):
                                tot["actualizados"] += 1
                            else:
                                tot["errores"] += 1
                                print(f"[sync] PATCH error id={rid} status={pr.status_code} {pr.text[:120]}", flush=True)
                        except Exception as e:
                            tot["errores"] += 1
                            print(f"[sync] PATCH excepcion id={rid} - {e}", flush=True)

                    if tot["procesados"] % 250 == 0:
                        print(f"[sync] progreso: {tot}", flush=True)

                if page * 500 >= total:
                    break
                page += 1

            print(f"[sync] sweep #{sweep}: nuevos={nuevos} acumulado={tot}", flush=True)
            if nuevos == 0:
                break
    finally:
        db.close()

    print(f"[sync] FIN. Resumen={tot}", flush=True)


if __name__ == "__main__":
    main()
