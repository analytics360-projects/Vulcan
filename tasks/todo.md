# Vulcan - Tareas Actuales

## Motor de Busqueda de Personas + Infraestructura

### Fase 1: Infraestructura Docker
- [x] Crear docker-compose.yml con todos los servicios (Neo4j, Qdrant, Redis, MinIO, PostgreSQL, Tor)
- [x] Configurar .env.example actualizado

### Fase 2: Google Person Search (nuevo modulo)
- [x] Crear modules/google_search/ con servicio de scraping por nombre
- [x] Screenshots de sitios encontrados
- [x] Guardar HTML, imagenes y recursos
- [x] Router con endpoints

### Fase 3: Person Search Engine (modulo unificado)
- [x] Crear modules/person_search/ que agregue resultados de TODAS las plataformas
- [x] Router con endpoint unificado /person/search
- [x] Integrar Google, Twitter, Instagram, TikTok, Telegram, Reddit, Email, Phone

### Fase 4: Integracion
- [x] Registrar nuevos routers en main.py
- [x] Actualizar config.py con nuevas settings
- [x] Actualizar requirements.txt
