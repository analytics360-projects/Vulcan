"""SANS URL scraping service — ported from Hades"""
import uuid
import re
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup

from config import logger
from modules.sans.ravendb_client import open_session


def scrape_single_url(full_path: str, palabras: list) -> dict:
    """Scrape a single URL and count keyword occurrences."""
    time_now = datetime.now()
    try:
        page = requests.get(full_path, timeout=30)
        soup = BeautifulSoup(page.content, "lxml")
        soupon = str(soup.prettify().encode("utf-8"))
        json_data = str(time_now) + str(json.dumps(soupon))

        conteo = {}
        json_lower = json_data.lower()
        for palabra in palabras:
            conteo[palabra] = json_lower.count(palabra.lower())

        resultados = [{"palabra": p, "coincidencias": c} for p, c in conteo.items()]

        return {
            "fecha": str(time_now),
            "url": full_path,
            "resultados": resultados,
            "json_data": json_data,
            "status": 1,
            "aprobado": False,
            "id": str(uuid.uuid4()),
        }
    except Exception as e:
        logger.error(f"Error scraping {full_path}: {e}")
        return {
            "fecha": str(time_now),
            "url": full_path,
            "resultados": [],
            "json_data": "",
            "status": -1,
            "aprobado": False,
            "id": str(uuid.uuid4()),
            "error": str(e),
        }


def scrape_multi_urls(urls, user, nombre, carpeta, investigacion, tipo_busqueda, status, palabras):
    """Scrape multiple URLs and store in RavenDB."""
    time_now = datetime.now()
    respuestas = []
    for url in urls:
        resp = scrape_single_url(url, palabras)
        respuestas.append(resp)

    try:
        with open_session() as session:
            session.store({
                "message": "Campos guardados con exito",
                "ok": True,
                "status": 200,
                "carpeta_investigacion": carpeta,
                "investigacion": investigacion,
                "tipo_busqueda": tipo_busqueda,
                "nombre": nombre,
                "date": str(time_now),
                "assigned": False,
                "status ": status,
                "user_creacion": user,
                "respuestas": respuestas,
            })
            session.save_changes()
    except Exception as e:
        logger.error(f"RavenDB store error: {e}")

    return respuestas


def clean_html_from_responses(results_list):
    """Clean HTML from json_data in responses."""
    for item in results_list:
        if "respuestas" not in item:
            continue
        for i, resp in enumerate(item["respuestas"]):
            if "json_data" not in resp:
                continue
            text = resp["json_data"]
            text = re.sub(r"<script\b[^<]*(?:(?!</script>)<[^<]*)*</script\s*>", "", text, flags=re.IGNORECASE)
            text = re.sub(r"<style\b[^<]*(?:(?!</style>)<[^<]*)*</style\s*>", "", text, flags=re.IGNORECASE)
            text = re.sub(r'style\s*=\s*"[^"]*?"', "", text, flags=re.IGNORECASE)
            text = text.replace("\\", "")
            text = re.sub(r">n", ">", text, flags=re.IGNORECASE)
            text = re.sub(r"-n", "", text, flags=re.IGNORECASE)
            if len(text) > 29:
                text = text[29:]
            item["respuestas"][i]["json_data"] = text
    return results_list
