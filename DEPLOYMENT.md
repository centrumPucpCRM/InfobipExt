# Despliegue con Docker - InfobipExt API

## Requisitos del servidor
- Ubuntu/Linux
- Docker y Docker Compose
- Git
- Puerto 8000 disponible

## Instalación en el servidor

### 1. Instalar Docker
```bash
# Actualizar sistema
sudo apt update

# Instalar Docker
sudo apt install -y docker.io docker-compose

# Agregar usuario al grupo docker
sudo usermod -aG docker $USER
newgrp docker
```

### 2. Clonar y configurar
```bash
# Clonar repositorio
git clone https://github.com/tu-usuario/tu-repo.git infobip-api
cd infobip-api

# Configurar variables de entorno
cp .env.production.example .env
nano .env  # Editar con valores reales
```

### 3. Desplegar con Docker
```bash
# Construir y ejecutar (primera vez)
docker-compose up -d --build

# Para futuras actualizaciones
git pull
docker-compose up -d --build
```

## Comandos Docker esenciales

### Gestión básica
```bash
# Iniciar aplicación
docker-compose up -d

# Ver logs en tiempo real
docker-compose logs -f

# Ver estado
docker-compose ps

# Reiniciar
docker-compose restart

# Detener
docker-compose down
```

### Actualización desde GitHub
```bash
# Actualizar código
git pull

# Reconstruir y reiniciar
docker-compose up -d --build
```

### Monitoreo
```bash
# Verificar salud de la API
curl http://localhost:8000/health

# Ver logs específicos
docker-compose logs api

# Estadísticas de recursos
docker stats
```

## URLs de acceso (solo desde tu IP)
- **API**: http://TU-IP-PUBLICA:8000
- **Documentación**: http://TU-IP-PUBLICA:8000/docs
- **Health Check**: http://TU-IP-PUBLICA:8000/health

## Configuración de Security Group (AWS) - SEGURA
Reglas de entrada recomendadas:
- **SSH (22)**: Tu IP específica (ya configurado)
- **Custom TCP (8000)**: Tu IP específica (para FastAPI)

### Para agregar regla del puerto 8000:
1. Type: Custom TCP
2. Port: 8000
3. Source: Tu IP específica (igual que SSH)
4. Description: FastAPI Access

## Troubleshooting
```bash
# Si algo falla, ver logs
docker-compose logs

# Limpiar y reiniciar todo
docker-compose down
docker system prune -f
docker-compose up -d --build

# Verificar que Docker esté corriendo
sudo systemctl status docker
```