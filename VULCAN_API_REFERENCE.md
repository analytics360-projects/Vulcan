# Vulcan API Reference — Endpoints Completos

**Base URL:** `http://localhost:8000`
**Docs interactivos:** `http://localhost:8000/docs`

---

## 1. Sistema

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/` | Info del sistema |
| GET | `/health` | Estado de todos los modulos |
| GET | `/proxy/status` | Estado del pool de proxies y Tor |
| POST | `/proxy/rotate` | Rotar circuito Tor (nueva IP) |

---

## 2. Busqueda de Personas (Person Search)

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/person/search` | Busqueda unificada en redes sociales, Google, news, etc. |

**Parametros:**
- `nombre` (required) — Nombre completo
- `email` — Email
- `telefono` — Telefono
- `username` — Username redes sociales / gaming
- `domicilio` — Domicilio conocido
- `alias` — Alias o apodo
- `zona_geografica` — Ciudad/estado/zona
- `group_ids` — IDs de grupos Facebook (separados por coma)
- `max_google_captures` (default: 5) — Sitios a capturar de Google
- `include_dorks` (default: true) — Google dorks para Facebook, LinkedIn, YouTube, GitHub
- `include_marketplace` (default: true) — Facebook Marketplace
- `include_news` (default: true) — Google News
- `include_dark_web` (default: false) — Dark web (.onion)
- `include_gaming` (default: false) — Steam, Xbox

---

## 3. Expediente Completo / Dossier (ENDPOINT PRINCIPAL)

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/records/dossier` | **EXPEDIENTE COMPLETO** — Busca en TODAS las fuentes |

**Parametros:**
- `nombre` (required) — Nombre completo
- `curp` — CURP
- `rfc` — RFC
- `email` — Email
- `telefono` — Telefono
- `username` — Username redes sociales
- `domicilio` — Domicilio conocido
- `alias` — Alias o apodo
- `zona_geografica` — Ciudad/estado/zona
- `placa` — Placa vehicular
- `niv` — NIV del vehiculo
- `group_ids` — IDs de grupos Facebook (coma-separados)
- `include_social` (default: true) — Redes sociales
- `include_legal` (default: true) — Legal/judicial
- `include_vehiculos` (default: true) — REPUVE
- `include_gobierno` (default: true) — CURP/RFC/DENUE
- `include_dark_web` (default: false) — Dark web
- `include_gaming` (default: false) — Gaming

**Response:**
```json
{
  "nombre": "Juan Perez",
  "curp": "PEGJ900101...",
  "rfc": "PEGJ900101...",
  "email": "juan@example.com",
  "telefono": "+5215512345678",
  "username": "juanp",
  "domicilio": "Calle Reforma 100, CDMX",
  "alias": "El Juancho",
  "zona_geografica": "CDMX",
  "registros": [
    {
      "fuente": "RENAPO/CURP",
      "tipo": "curp",
      "disponible": true,
      "datos": { ... },
      "error": null,
      "url_fuente": "https://www.gob.mx/curp/"
    },
    {
      "fuente": "SAT/RFC",
      "tipo": "rfc",
      "disponible": true,
      "datos": { "efos_page_text": "...", "lista_69_disponible": true },
      "error": null,
      "url_fuente": "https://efos.sat.gob.mx/"
    },
    {
      "fuente": "Buholegal",
      "tipo": "legal",
      "disponible": true,
      "datos": {
        "resultados": [
          {"titulo": "...", "url": "...", "descripcion": "..."}
        ],
        "texto_pagina": "..."
      }
    },
    {
      "fuente": "Poder Judicial/CJF",
      "tipo": "expediente_judicial",
      "disponible": true,
      "datos": { "sise_resultado": "..." }
    },
    {
      "fuente": "FGR/Fiscalia",
      "tipo": "denuncia",
      "disponible": true,
      "datos": { "resultados": [...] }
    },
    {
      "fuente": "SFP/PDN",
      "tipo": "servidor_sancionado",
      "datos": { "pdn_resultado": "...", "sfp_resultado": "..." }
    },
    {
      "fuente": "DOF",
      "tipo": "diario_oficial",
      "datos": { "resultados": [...] }
    },
    {
      "fuente": "Compranet",
      "tipo": "contrato_publico",
      "datos": { ... }
    },
    {
      "fuente": "DENUE/INEGI",
      "tipo": "empresa",
      "datos": [{ "Nombre": "...", "Razon_social": "...", "Clase_actividad": "..." }]
    },
    {
      "fuente": "datos.gob.mx",
      "tipo": "datos_abiertos",
      "datos": [{ "titulo": "...", "organizacion": "...", "url": "..." }]
    },
    {
      "fuente": "REPUVE",
      "tipo": "vehiculo",
      "datos": { "resultado_placa": "..." }
    },
    {
      "fuente": "WHOIS",
      "tipo": "dominio",
      "datos": { "registrar": "...", "creation_date": "..." }
    },
    {
      "fuente": "crt.sh",
      "tipo": "certificado",
      "datos": [{ "nombre": "...", "issuer": "...", "fecha": "..." }]
    },
    {
      "fuente": "Wayback Machine",
      "tipo": "historial_web",
      "datos": [{ "timestamp": "...", "wayback_url": "..." }]
    },
    {
      "fuente": "Gravatar",
      "tipo": "avatar",
      "datos": { "avatar_url": "...", "profile": { ... } }
    },
    {
      "fuente": "Google Dorks Legal",
      "tipo": "legal_google",
      "datos": [{ "titulo": "...", "url": "...", "snippet": "..." }]
    }
  ],
  "redes_sociales": [
    {
      "plataforma": "twitter",
      "disponible": true,
      "resultados": [...]
    },
    {
      "plataforma": "instagram",
      "disponible": true,
      "resultados": [...]
    },
    {
      "plataforma": "tiktok",
      "disponible": true,
      "resultados": [...]
    },
    {
      "plataforma": "google",
      "disponible": true,
      "resultados": { "resultados": [...], "capturas": [...] }
    },
    {
      "plataforma": "google_dorks",
      "disponible": true,
      "resultados": { "facebook": [...], "linkedin": [...], "youtube": [...] }
    },
    {
      "plataforma": "marketplace",
      "disponible": true,
      "resultados": [...]
    },
    {
      "plataforma": "news",
      "disponible": true,
      "resultados": [...]
    }
  ],
  "total_fuentes": 25,
  "total_resultados": 142
}
```

---

## 4. Registros Publicos (Individuales)

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/records/curp` | Validar/buscar CURP (RENAPO) |
| GET | `/records/rfc` | Buscar RFC en SAT (EFOS, Lista 69) |
| GET | `/records/repuve` | Buscar vehiculo en REPUVE (placa o NIV) |
| GET | `/records/buholegal` | Buscar denuncias/expedientes en Buholegal |
| GET | `/records/judicial` | Buscar expedientes en Poder Judicial (CJF/SISE) |
| GET | `/records/fiscalia` | Buscar en FGR/Fiscalia General |
| GET | `/records/sancionados` | Buscar servidores publicos sancionados (SFP/PDN) |
| GET | `/records/denue` | Buscar empresas en DENUE/INEGI |
| GET | `/records/datos-gob` | Buscar en datos.gob.mx (datos abiertos) |
| GET | `/records/dof` | Buscar en Diario Oficial de la Federacion |
| GET | `/records/compranet` | Buscar licitaciones/contratos en Compranet |
| GET | `/records/whois` | WHOIS de dominio |
| GET | `/records/crtsh` | Certificate Transparency (subdominios) |
| GET | `/records/wayback` | Historial en Wayback Machine |
| GET | `/records/gravatar` | Avatar y perfil por email |

---

## 5. Google Search

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/google/search` | Busqueda Google + capturas de sitios |
| GET | `/google/dorks` | Google dorks para perfiles en plataformas |

---

## 6. Redes Sociales (Individuales)

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/social/twitter/search` | Buscar en Twitter/X |
| GET | `/social/instagram/search` | Buscar en Instagram |
| GET | `/social/tiktok/search` | Buscar en TikTok |
| GET | `/social/telegram/search` | Buscar en Telegram |
| GET | `/social/forums/search` | Buscar en Reddit/foros |

---

## 7. OSINT Especializado

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/search/email` | OSINT por email (Hunter.io + HIBP) |
| GET | `/search/phone` | OSINT por telefono (NumVerify) |

---

## 8. Facebook

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/marketplace/search` | Buscar en Facebook Marketplace |
| GET | `/groups/posts` | Obtener posts de grupos |
| GET | `/groups/posts/keyword` | Buscar por keyword en grupo |

---

## 9. Gaming

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/gaming/steam` | Buscar perfil en Steam |
| GET | `/gaming/xbox` | Buscar perfil en Xbox |
| GET | `/gaming/search` | Buscar en todas las plataformas gaming |

---

## 10. Noticias

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/news/search` | Buscar noticias |
| GET | `/news/content` | Buscar noticias con contenido completo |

---

## 11. Dark Web

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/darkweb/search` | Buscar en dark web (.onion) |

---

## 12. Intelligence (Analisis)

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| POST | `/intelligence/search` | Busqueda semantica inteligente |
| GET | `/intelligence/objects` | Objetos de inteligencia |
| GET | `/intelligence/list` | Listar registros de inteligencia |

---

## 13. SANS (RavenDB)

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/sans/...` | Consultas SANS/RavenDB |

---

## 14. Scheduler

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/scheduler/jobs` | Listar jobs programados |
| POST | `/scheduler/jobs` | Crear job programado |
