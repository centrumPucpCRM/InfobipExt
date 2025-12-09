# InfobipExt API

API RESTful para gestión de RDV, People y Conversations con autenticación por token.

## 🔐 Autenticación

Todos los endpoints requieren un **Bearer Token** en el header:

```
Authorization: Bearer test-token
```

## 📋 Estructura del Proyecto

```
InfobipExt/
├── app/
│   ├── api/v1/endpoints/    # Endpoints (rdv, people, conversations)
│   ├── core/                # Config, database, dependencies
│   ├── models/              # Modelos SQLAlchemy
│   └── schemas/             # Schemas Pydantic
├── scripts/                 # Scripts de utilidad
├── requirements.txt
└── README.md
```

## 🚀 Instalación

```bash
# Crear entorno virtual
python -m venv venv
.\venv\Scripts\Activate.ps1

# Instalar dependencias
pip install -r requirements.txt

# Copiar variables de entorno
cp .env.example .env

# Crear base de datos
python scripts/init_db.py
```

## ▶️ Ejecutar la aplicación

```bash
uvicorn app.main:app --reload
```

Acceso:
- **API**: http://localhost:8000
- **Docs**: http://localhost:8000/docs
- **Health**: http://localhost:8000/health

## 📚 Endpoints

### RDV
- `GET /api/v1/rdv/` - Listar RDV 🔒

### People
- `GET /api/v1/people/` - Listar People 🔒

### Conversations
- `GET /api/v1/conversations/` - Listar Conversations 🔒

🔒 = Requiere autenticación

## 🧪 Probar en Swagger

1. Ir a http://localhost:8000/docs
2. Click en el botón **"Authorize"** 🔓
3. Ingresar: `test-token`
4. Click en "Authorize"
5. Ahora puedes probar los endpoints

## 🗄️ Modelos

### RdvExt
- id, party_id, party_number
- Relación: 1:N con People y Conversations

### PeopleExt
- id, party_id, party_number, telefono
- Relación: N:1 con RdvExt, 1:N con Conversations

### ConversationExt
- id, id_conversation, id_people, id_rdv
- estado_conversacion, proxima_sincronizacion, ultima_sincronizacion
- Relación: N:1 con RdvExt y PeopleExt

## 🔑 Cambiar Token

Edita el archivo `.env`:

```
API_TOKEN=tu-nuevo-token-secreto
```
