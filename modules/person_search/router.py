"""Person Search Engine router — unified person OSINT"""
from fastapi import APIRouter, Query
from typing import Optional
from modules.person_search.models import PersonSearchResponse

router = APIRouter(prefix="/person", tags=["person-search"])


@router.get("/search", response_model=PersonSearchResponse)
async def search_person(
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
):
    """
    Motor de busqueda unificado de personas.
    Todo el trafico de scraping pasa por proxy Tor para anonimato.

    Busca en paralelo en todas las fuentes configuradas y devuelve
    resultados crudos para que Balder los procese.
    """
    from modules.person_search.service import search_person as do_search

    gids = group_ids.split(",") if group_ids else None

    return await do_search(
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
    )
