"""
PDL (People Data Labs) — Router
Exposes Person Search + Enrichment endpoints.
"""
from typing import Optional

from fastapi import APIRouter, Query, Request

from config import logger
from modules.pdl.models import PDLSearchResponse, PDLEnrichResponse

router = APIRouter(prefix="/pdl", tags=["people-data-labs"])


@router.get("/search/name", response_model=PDLSearchResponse)
async def search_by_name(
    request: Request,
    name: str = Query(..., description="Nombre completo"),
    country: Optional[str] = Query(None, description="Pais (ej: mexico, united states)"),
    size: int = Query(10, ge=1, le=100, description="Max resultados"),
):
    """Buscar personas por nombre completo."""
    logger.info(f"[PDL-ROUTER] search/name: {name} country={country}")
    from modules.pdl.service import search_by_name as do_search
    return await do_search(name=name, location_country=country, size=size)


@router.get("/search/email", response_model=PDLSearchResponse)
async def search_by_email(
    request: Request,
    email: str = Query(..., description="Email address"),
    size: int = Query(5, ge=1, le=100),
):
    """Buscar personas por email."""
    logger.info(f"[PDL-ROUTER] search/email: {email}")
    from modules.pdl.service import search_by_email as do_search
    return await do_search(email=email, size=size)


@router.get("/search/phone", response_model=PDLSearchResponse)
async def search_by_phone(
    request: Request,
    phone: str = Query(..., description="Numero de telefono (E.164 format: +521234567890)"),
    size: int = Query(5, ge=1, le=100),
):
    """Buscar personas por telefono."""
    logger.info(f"[PDL-ROUTER] search/phone: {phone}")
    from modules.pdl.service import search_by_phone as do_search
    return await do_search(phone=phone, size=size)


@router.get("/search/linkedin", response_model=PDLSearchResponse)
async def search_by_linkedin(
    request: Request,
    url: str = Query(..., description="LinkedIn profile URL"),
    size: int = Query(5, ge=1, le=100),
):
    """Buscar personas por perfil de LinkedIn."""
    logger.info(f"[PDL-ROUTER] search/linkedin: {url}")
    from modules.pdl.service import search_by_linkedin as do_search
    return await do_search(linkedin_url=url, size=size)


@router.get("/search/company", response_model=PDLSearchResponse)
async def search_by_company(
    request: Request,
    company: str = Query(..., description="Nombre de la empresa"),
    title: Optional[str] = Query(None, description="Puesto / Job title"),
    country: Optional[str] = Query(None, description="Pais"),
    size: int = Query(10, ge=1, le=100),
):
    """Buscar empleados de una empresa, opcionalmente filtrado por puesto y pais."""
    logger.info(f"[PDL-ROUTER] search/company: {company} title={title}")
    from modules.pdl.service import search_by_company as do_search
    return await do_search(company=company, job_title=title, location_country=country, size=size)


@router.get("/search/location", response_model=PDLSearchResponse)
async def search_by_location(
    request: Request,
    country: str = Query(..., description="Pais"),
    region: Optional[str] = Query(None, description="Estado / Region"),
    locality: Optional[str] = Query(None, description="Ciudad"),
    title: Optional[str] = Query(None, description="Puesto / Job title"),
    size: int = Query(10, ge=1, le=100),
):
    """Buscar personas por ubicacion."""
    logger.info(f"[PDL-ROUTER] search/location: {country}/{region}/{locality}")
    from modules.pdl.service import search_by_location as do_search
    return await do_search(
        country=country, region=region, locality=locality,
        job_title=title, size=size,
    )


@router.post("/search/sql", response_model=PDLSearchResponse)
async def search_sql(
    request: Request,
    sql: str = Query(..., description="SQL query (ej: SELECT * FROM person WHERE full_name='John Doe')"),
    size: int = Query(10, ge=1, le=100),
    scroll_token: Optional[str] = Query(None, description="Token de paginacion"),
):
    """Busqueda avanzada con SQL syntax directo."""
    logger.info(f"[PDL-ROUTER] search/sql: {sql[:100]}")
    from modules.pdl.service import search_person
    return await search_person(sql=sql, size=size, scroll_token=scroll_token)


@router.get("/enrich", response_model=PDLEnrichResponse)
async def enrich_person(
    request: Request,
    email: Optional[str] = Query(None, description="Email"),
    phone: Optional[str] = Query(None, description="Telefono"),
    name: Optional[str] = Query(None, description="Nombre completo"),
    profile: Optional[str] = Query(None, description="URL de perfil social (LinkedIn, etc)"),
    lid: Optional[str] = Query(None, description="LinkedIn ID"),
    company: Optional[str] = Query(None, description="Empresa actual (ayuda a desambiguar)"),
    country: Optional[str] = Query(None, description="Pais (ayuda a desambiguar)"),
):
    """
    Enriquecer un perfil de persona por uno o mas identificadores.
    Retorna el perfil completo con datos laborales, educacion, redes sociales, etc.
    """
    logger.info(f"[PDL-ROUTER] enrich: email={email} phone={phone} name={name} profile={profile}")
    from modules.pdl.service import enrich_person as do_enrich
    return await do_enrich(
        email=email, phone=phone, name=name, profile=profile,
        lid=lid, company=company, location_country=country,
    )
