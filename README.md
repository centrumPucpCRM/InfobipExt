## Sincronizadores

Este proyecto tiene tres pasos de sincronización que se usan en orden lógico:

### 1. Migración histórica

Toma las conversaciones históricas locales y las envía a `conversation-lead-relation` por lotes.

Qué hace:
- Deduplica por `infobip_conversation_id`.
- Respeta la fecha histórica real (`created_at` / `updated_at`).
- Excluye datos de prueba conocidos.
- Usa corte por defecto `2026-06-07` para incluir todo el 6-jun y no dejar huecos.

Uso:
- Endpoint: `POST /api/v1/sales/sincronizar-general`
- Script: `python sincronizar_general.py`

### 2. Sincronizador de reportería

Completa filas incompletas de `conversation-lead-relation` con datos locales
y corrige las filas cuyo `sender` es el número genérico (`51992948046`).

Qué hace:
- Rellena `telefono_contacto` desde `conversation_ext`.
- Rellena `sender` desde el teléfono compuesto local (si trae un sender real)
  o desde la cartera del lead (`CTRTipoDeCarteraLead_c`).
- Corrige el `sender` genérico al número real de la cartera del lead.
- Solo escribe lo que pudo resolver.

Uso:
- Endpoint: `POST /api/v1/sales/sincronizar-reporteria`
- Script: `python sincronizar_reporteria.py`

### 3. Sincronizador de último RDV por sender

Construye y actualiza `sender-last-rdv` a partir de los pares `telefono_contacto + sender`.

Qué hace:
- Busca el RDV vigente desde Oracle.
- Corrige los pares con `sender` genérico usando la cartera del lead antes del UPSERT.
- Hace UPSERT en la tabla externa.
- Marca si el proceso fue masivo o surgió de un flujo orgánico.

Uso:
- Endpoint: `POST /api/v1/sales/sincronizar-ultimo-rdv`
- Script: `python sincronizar_ultimo_rdv.py`

## Sincronizador general

El flujo general ejecuta los 3 pasos en este orden:

1. Migración histórica.
2. Sincronizador de reportería.
3. Sincronizador de último RDV por sender.

Endpoint:
- `POST /api/v1/sales/sincronizar-general`

Script:
- `python sincronizar_general.py`

## Comandos rápidos

Dentro del contenedor:

```bash
docker compose exec api python sincronizar_general.py
docker compose exec api python sincronizar_reporteria.py
docker compose exec api python sincronizar_ultimo_rdv.py
```

En local:

```bash
python sincronizar_general.py
python sincronizar_reporteria.py
python sincronizar_ultimo_rdv.py
```
