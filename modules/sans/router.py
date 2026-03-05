"""SANS router — ported from Hades app/main.py"""
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime
import jsonpickle

from config import logger
from modules.sans.models import (
    Item, ItemMultiUrl, Carpeta, Investigacion,
    CarpetaInvestigacion, CarpetaInvestigacionCollectionById,
    UbicacionRequest, GrupoInvestigacion,
)
from modules.sans.ravendb_client import open_session
from modules.sans.service import scrape_single_url, scrape_multi_urls, clean_html_from_responses

router = APIRouter(prefix="/sans", tags=["sans"])


@router.post("/singleurl")
def single_url(item: Item):
    try:
        return scrape_single_url(item.full_path, item.palabras)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/multiurls")
def multi_urls(item: ItemMultiUrl):
    try:
        return scrape_multi_urls(
            item.urls, item.user, item.nombre, item.carpeta_investigacion,
            item.investigacion, item.tipo_busqueda, item.status, item.palabras,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create/carpeta")
def create_carpeta(carpeta: Carpeta):
    try:
        with open_session() as session:
            session.store({
                "carpeta_investigacion": carpeta.carpeta_investigacion,
                "assigned": False,
                "date": str(datetime.now()),
                "user_creacion": carpeta.user,
            })
            session.save_changes()
        return {"message": "Campos guardados con exito"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create/investigación")
def create_investigacion(inv: Investigacion):
    try:
        with open_session() as session:
            session.store({
                "carpeta_investigacion": inv.carpeta_investigacion,
                "investigacion": inv.nombre,
                "assigned": False,
                "date": str(datetime.now()),
                "user_creacion": inv.user,
            })
            session.save_changes()
        return {"message": "Campos guardados con exito"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get_collections_by_investigacion/{investigacion}")
def get_by_investigacion(investigacion: str):
    try:
        with open_session() as session:
            results = session.query_collection("dicts").contains_all("investigacion", [investigacion])
            results_list = [dict(r) for r in results]
        return clean_html_from_responses(results_list)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get_collection_by_carpeta_investigacion/{carpeta}")
def get_by_carpeta(carpeta: int):
    try:
        with open_session() as session:
            results = session.query_collection("dicts").contains_all("carpeta_investigacion", [carpeta])
            results_list = [dict(r) for r in results]
        for item in results_list:
            for key in ("@metadata", "message", "ok", "status"):
                item.pop(key, None)
        return results_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get_collection_by_carpeta_investigacion_aprobbed/{carpeta}")
def get_by_carpeta_approved(carpeta: int):
    try:
        with open_session() as session:
            results = session.query_collection("dicts").contains_all("carpeta_investigacion", [carpeta])
            results_list = [dict(r) for r in results]
        for item in results_list:
            if "respuestas" in item:
                item["respuestas"] = [r for r in item["respuestas"] if r.get("aprobado") != 0]
            for key in ("@metadata", "message", "ok", "status"):
                item.pop(key, None)
        return results_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get_by_collection_and_date/{collection}/{date}")
def get_by_date(collection: str, date: str):
    try:
        with open_session() as session:
            results = session.query_collection("dicts").contains_all("date", [date])
            return [dict(r) for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get_by_collection_and_user_creacion/{collection}/{user_creacion}")
def get_by_user(collection: str, user_creacion: str):
    try:
        with open_session() as session:
            results = session.query_collection("dicts").contains_all("user_creacion", [user_creacion])
            return [dict(r) for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get_all")
def get_all():
    try:
        with open_session() as session:
            results = session.query_collection("dicts")
            return [dict(r) for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/get_by_id_collection")
def get_by_id(carpeta: CarpetaInvestigacionCollectionById):
    try:
        with open_session() as session:
            results = session.query_collection("dicts").contains_all("Id", [carpeta.carpetaId])
            return [dict(r) for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/asignar/informacion_relevante")
def assign_relevant(document_ids: list):
    try:
        with open_session() as session:
            for doc_id in document_ids:
                doc = session.load(doc_id)
                if doc is None:
                    raise HTTPException(status_code=404, detail=f"Doc {doc_id} not found")
                doc["assigned"] = True
            session.save_changes()
        return {"message": "Campos editados exitosamente"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/suspend_investigacion_by_id/")
def suspend_by_id(ci: CarpetaInvestigacion):
    try:
        with open_session() as session:
            results = session.query_collection("dicts").contains_all("investigacion", [ci.investigacion_id])
            results_list = [dict(r) for r in results]
            for item in results_list:
                for resp in item.get("respuestas", []):
                    if resp.get("id") == ci.resultado_id:
                        resp["aprobado"] = 0 if resp.get("aprobado") == 1 else 1
            session.save_changes()
        return "Campos guardados con exito"
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/suspend_collection_by_carpeta_investigacion/{carpeta}")
def suspend_by_carpeta(carpeta: int):
    try:
        with open_session() as session:
            results = session.query_collection("dicts").contains_all("carpeta_investigacion", [carpeta])
            results_list = [dict(r) for r in results]
            for item in results_list:
                item["status"] = 0
            session.save_changes()
        return results_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create_ubicacion_carpeta_investigacion")
def create_ubicacion(req: UbicacionRequest):
    try:
        with open_session() as session:
            results = (
                session.query_collection("dicts")
                .where_equals("carpeta_investigacion", req.carpeta_id)
                .where_equals("investigacion", req.investigacion_id)
            )
            results_list = [dict(r) for r in results]
            for item in results_list:
                for resp in item.get("respuestas", []):
                    if resp.get("id") == req.resultado_id:
                        resp["latitud"] = req.latitud
                        resp["longitud"] = req.longitud
            session.save_changes()
        return results_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/grupo/create")
def create_grupo(req: GrupoInvestigacion):
    try:
        with open_session() as session:
            results = (
                session.query_collection("dicts")
                .where_equals("carpeta_investigacion", req.carpeta_id)
                .where_equals("investigacion", req.investigacion_id)
            )
            results_list = [dict(r) for r in results]
            if not results_list:
                raise HTTPException(status_code=404, detail="Documento no encontrado")
            doc_id = results_list[0]["Id"]
            doc = session.load(doc_id)
            doc["grupo"] = req.grupo
            doc["palabra"] = req.palabra
            session.save_changes()
        return {"message": "Campos guardados con éxito", "ok": True, "status": 200}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get_collections_by_grupos/{grupo}")
def get_by_grupo(grupo: str):
    try:
        with open_session() as session:
            results = session.query_collection("dicts").contains_all("grupo", [grupo])
            results_list = [dict(r) for r in results]
        return clean_html_from_responses(results_list)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create/history/{subcenter}/{id_folio}")
async def create_history(subcenter: str, id_folio: int, request: Request):
    try:
        body = await request.body()
        data = jsonpickle.decode(body)
        with open_session() as session:
            session.store({
                "subcentro": subcenter,
                "folio": id_folio,
                "data": data,
                "created": str(datetime.now()),
                "status": 1,
            })
            session.save_changes()
        return {"message": "Campos guardados con exito"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get_historicals")
def get_historicals():
    try:
        with open_session() as session:
            results = session.query_collection("Historicals")
            return [dict(r) for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
