"""Person Search Engine router — unified person OSINT"""
import json
from fastapi import APIRouter, Query, Request
from typing import Optional
from config import logger
from modules.person_search.models import PersonSearchResponse

router = APIRouter(prefix="/person", tags=["person-search"])


def _log_response_json(tag: str, result):
    """Log full JSON response for debugging what gets sent to Balder."""
    try:
        data = result.model_dump() if hasattr(result, "model_dump") else result
        json_str = json.dumps(data, default=str, ensure_ascii=False, indent=2)
        logger.info(f"[{tag}] RESPONSE JSON:\n{json_str}")
    except Exception as e:
        logger.warning(f"[{tag}] Could not serialize response: {e}")


@router.get("/search", response_model=PersonSearchResponse)
async def search_person(
    request: Request,
    nombre: str = Query(..., description="Nombre completo de la persona a buscar"),
    email: Optional[str] = Query(None, description="Email de la persona"),
    telefono: Optional[str] = Query(None, description="Telefono de la persona"),
    username: Optional[str] = Query(None, description="Username en redes sociales / gaming"),
    domicilio: Optional[str] = Query(None, description="Domicilio o direccion conocida"),
    alias: Optional[str] = Query(None, description="Alias, apodo o nombre alternativo"),
    zona_geografica: Optional[str] = Query(None, description="Ciudad, estado o zona geografica"),
    group_ids: Optional[str] = Query(None, description="IDs de grupos de Facebook separados por coma"),
    max_google_captures: int = Query(5, ge=0, le=20, description="Sitios a capturar de Google"),
    include_dorks: bool = Query(True, description="Google dorks: Facebook, LinkedIn, YouTube, GitHub, etc."),
    include_marketplace: bool = Query(True, description="Buscar en Facebook Marketplace"),
    include_news: bool = Query(True, description="Buscar en Google News"),
    include_dark_web: bool = Query(False, description="Buscar en dark web (.onion)"),
    include_gaming: bool = Query(False, description="Buscar en plataformas de gaming (Steam, Xbox)"),
    include_username_enum: bool = Query(True, description="Enumerar username en 400+ plataformas (findme)"),
    include_github: bool = Query(True, description="GitHub deep OSINT (emails de commits/GPG, SSH keys)"),
    include_twitch: bool = Query(True, description="Buscar perfil en Twitch"),
):
    """
    Motor de busqueda unificado de personas.
    Todo el trafico de scraping pasa por proxy Tor para anonimato.

    Busca en paralelo en todas las fuentes configuradas y devuelve
    resultados crudos para que Balder los procese.
    """
    client = request.client.host if request.client else "?"
    logger.info(f"[PERSON-ROUTER] Search request from {client}: nombre={nombre}, username={username}, email={email}")

    from modules.person_search.service import search_person as do_search

    gids = group_ids.split(",") if group_ids else None

    result = await do_search(
        nombre=nombre,
        email=email,
        telefono=telefono,
        username=username,
        domicilio=domicilio,
        alias=alias,
        zona_geografica=zona_geografica,
        group_ids=gids,
        max_google_captures=max_google_captures,
        include_dorks=include_dorks,
        include_marketplace=include_marketplace,
        include_news=include_news,
        include_dark_web=include_dark_web,
        include_gaming=include_gaming,
        include_username_enum=include_username_enum,
        include_github=include_github,
        include_twitch=include_twitch,
    )

    _log_response_json("PERSON-SEARCH", result)
    logger.info(f"[PERSON-ROUTER] Search done for {client}: {result.total_resultados} total results across {len(result.plataformas)} platforms")
    return result
