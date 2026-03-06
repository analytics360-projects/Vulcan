"""Google Search OSINT router"""
from fastapi import APIRouter, Query
from typing import Optional, List
from modules.google_search.models import GoogleSearchResponse

router = APIRouter(prefix="/google", tags=["google-search"])


@router.get("/search", response_model=GoogleSearchResponse)
async def google_search(
    query: str = Query(..., description="Nombre o termino a buscar en Google"),
    max_results: int = Query(10, ge=1, le=50, description="Resultados maximos de Google"),
    max_captures: int = Query(5, ge=0, le=20, description="Sitios a capturar (screenshot + HTML + imagenes)"),
):
    """
    Busca en Google y captura screenshots, HTML e imagenes de los sitios encontrados.
    Ideal para buscar personas por nombre y recopilar evidencia digital.
    """
    from modules.google_search.service import search_and_capture
    return await search_and_capture(query=query, max_results=max_results, max_captures=max_captures)


@router.get("/dorks")
async def google_dork_search(
    nombre: str = Query(..., description="Nombre de la persona a buscar"),
    platforms: Optional[str] = Query(
        None,
        description="Plataformas separadas por coma (facebook,linkedin,youtube,github,pinterest,medium,quora). Si no se especifica, busca en todas.",
    ),
):
    """
    Busca una persona en multiples plataformas usando Google dorks:
    site:facebook.com, site:linkedin.com, site:youtube.com, etc.
    No requiere API keys — usa Google como intermediario.
    """
    from modules.google_search.service import dork_search_person
    platform_list = platforms.split(",") if platforms else None
    return await dork_search_person(nombre, platform_list)
