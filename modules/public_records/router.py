"""Public Records router — Mexican government, legal, and open data sources"""
from fastapi import APIRouter, Query
from typing import Optional

router = APIRouter(prefix="/records", tags=["public-records"])


@router.get("/curp")
async def lookup_curp(
    nombre: str = Query(..., description="Nombre completo"),
    curp: Optional[str] = Query(None, description="CURP si se conoce"),
):
    from modules.public_records.service import search_curp
    result = await search_curp(nombre, curp)
    return result.model_dump()


@router.get("/rfc")
async def lookup_rfc(
    nombre: str = Query(..., description="Nombre completo o razon social"),
    rfc: Optional[str] = Query(None, description="RFC si se conoce"),
):
    from modules.public_records.service import search_rfc
    result = await search_rfc(nombre, rfc)
    return result.model_dump()


@router.get("/repuve")
async def lookup_repuve(
    placa: Optional[str] = Query(None, description="Placa vehicular"),
    niv: Optional[str] = Query(None, description="Numero de Identificacion Vehicular"),
):
    from modules.public_records.service import search_repuve
    result = await search_repuve(placa, niv)
    return result.model_dump()


@router.get("/buholegal")
async def lookup_buholegal(nombre: str = Query(..., description="Nombre a buscar")):
    from modules.public_records.service import search_buholegal
    result = await search_buholegal(nombre)
    return result.model_dump()


@router.get("/judicial")
async def lookup_judicial(nombre: str = Query(..., description="Nombre a buscar")):
    from modules.public_records.service import search_poder_judicial
    result = await search_poder_judicial(nombre)
    return result.model_dump()


@router.get("/fiscalia")
async def lookup_fiscalia(nombre: str = Query(..., description="Nombre a buscar")):
    from modules.public_records.service import search_fiscalia
    result = await search_fiscalia(nombre)
    return result.model_dump()


@router.get("/sancionados")
async def lookup_sancionados(nombre: str = Query(..., description="Nombre a buscar")):
    from modules.public_records.service import search_proveedores_sancionados
    result = await search_proveedores_sancionados(nombre)
    return result.model_dump()


@router.get("/denue")
async def lookup_denue(
    nombre: str = Query(..., description="Nombre o razon social"),
    zona: Optional[str] = Query(None, description="Entidad federativa"),
):
    from modules.public_records.service import search_denue
    result = await search_denue(nombre, zona)
    return result.model_dump()


@router.get("/datos-gob")
async def lookup_datos_gob(nombre: str = Query(..., description="Termino de busqueda")):
    from modules.public_records.service import search_datos_gob
    result = await search_datos_gob(nombre)
    return result.model_dump()


@router.get("/dof")
async def lookup_dof(nombre: str = Query(..., description="Nombre a buscar en DOF")):
    from modules.public_records.service import search_dof
    result = await search_dof(nombre)
    return result.model_dump()


@router.get("/compranet")
async def lookup_compranet(nombre: str = Query(..., description="Nombre o empresa a buscar")):
    from modules.public_records.service import search_compranet
    result = await search_compranet(nombre)
    return result.model_dump()


@router.get("/whois")
async def lookup_whois(domain: str = Query(..., description="Dominio a consultar")):
    from modules.public_records.service import search_whois
    result = await search_whois(domain)
    return result.model_dump()


@router.get("/crtsh")
async def lookup_crtsh(domain: str = Query(..., description="Dominio para buscar certificados")):
    from modules.public_records.service import search_crtsh
    result = await search_crtsh(domain)
    return result.model_dump()


@router.get("/wayback")
async def lookup_wayback(url: str = Query(..., description="URL o dominio a buscar")):
    from modules.public_records.service import search_wayback
    result = await search_wayback(url)
    return result.model_dump()


@router.get("/gravatar")
async def lookup_gravatar(email: str = Query(..., description="Email para buscar avatar")):
    from modules.public_records.service import search_gravatar
    result = await search_gravatar(email)
    return result.model_dump()


# ════════════════════════════════════════════
# ENDPOINT PRINCIPAL: Expediente completo (Dossier)
# ════════════════════════════════════════════
@router.get("/dossier")
async def build_person_dossier(
    nombre: str = Query(..., description="Nombre completo de la persona"),
    curp: Optional[str] = Query(None, description="CURP"),
    rfc: Optional[str] = Query(None, description="RFC"),
    email: Optional[str] = Query(None, description="Email"),
    telefono: Optional[str] = Query(None, description="Telefono"),
    username: Optional[str] = Query(None, description="Username redes sociales"),
    domicilio: Optional[str] = Query(None, description="Domicilio conocido"),
    alias: Optional[str] = Query(None, description="Alias o apodo"),
    zona_geografica: Optional[str] = Query(None, description="Ciudad/estado/zona"),
    placa: Optional[str] = Query(None, description="Placa vehicular"),
    niv: Optional[str] = Query(None, description="NIV del vehiculo"),
    group_ids: Optional[str] = Query(None, description="IDs de grupos Facebook (separados por coma)"),
    include_social: bool = Query(True, description="Incluir redes sociales"),
    include_legal: bool = Query(True, description="Incluir registros legales/judiciales"),
    include_vehiculos: bool = Query(True, description="Incluir REPUVE"),
    include_gobierno: bool = Query(True, description="Incluir CURP/RFC/DENUE/datos.gob"),
    include_dark_web: bool = Query(False, description="Incluir dark web"),
    include_gaming: bool = Query(False, description="Incluir gaming (Steam/Xbox)"),
):
    """
    EXPEDIENTE COMPLETO — Ancestry-style person dossier.

    Busca en TODAS las fuentes disponibles simultaneamente:
    - Gobierno: CURP, RFC/SAT (EFOS), DENUE/INEGI, datos.gob.mx, DOF, Compranet
    - Legal: Buholegal, Poder Judicial/CJF, FGR/Fiscalia, servidores sancionados (SFP/PDN)
    - Vehiculos: REPUVE (por placa o NIV)
    - Digital: WHOIS, crt.sh, Wayback Machine, Gravatar
    - Redes sociales: Twitter, Instagram, TikTok, Telegram, Reddit, Facebook (Groups/Marketplace)
    - Google: Busqueda directa + Dorks (LinkedIn, YouTube, GitHub, etc.)
    - Noticias: Google News
    - Opcional: Dark web, Gaming (Steam/Xbox)
    """
    from modules.public_records.service import build_dossier

    gids = group_ids.split(",") if group_ids else None

    return await build_dossier(
        nombre=nombre, curp=curp, rfc=rfc, email=email,
        telefono=telefono, username=username, domicilio=domicilio,
        alias=alias, zona_geografica=zona_geografica,
        placa=placa, niv=niv, group_ids=gids,
        include_social=include_social, include_legal=include_legal,
        include_vehiculos=include_vehiculos, include_gobierno=include_gobierno,
        include_dark_web=include_dark_web, include_gaming=include_gaming,
    )
