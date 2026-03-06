"""Gaming platforms OSINT router"""
from fastapi import APIRouter, Query
from typing import Optional

router = APIRouter(prefix="/gaming", tags=["gaming"])


@router.get("/steam")
async def search_steam(username: str = Query(...)):
    from modules.gaming.service import search_steam as do_search
    results = await do_search(username)
    return {"plataforma": "steam", "username": username, "resultados": [r.model_dump() for r in results], "count": len(results)}


@router.get("/xbox")
async def search_xbox(username: str = Query(...)):
    from modules.gaming.service import search_xbox as do_search
    results = await do_search(username)
    return {"plataforma": "xbox", "username": username, "resultados": [r.model_dump() for r in results], "count": len(results)}


@router.get("/search")
async def search_all_gaming(username: str = Query(...)):
    """Busca un username en todas las plataformas de gaming (Steam, Xbox)."""
    from modules.gaming.service import search_all
    results = await search_all(username)
    return {"username": username, "resultados": [r.model_dump() for r in results], "count": len(results)}
