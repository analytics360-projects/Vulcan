"""Public Records Service — Mexican government, legal, vehicle, and open data sources.

All scraping goes through Tor proxy for anonymity.
Sources: CURP, RFC, REPUVE, Buholegal, DENUE/INEGI, datos.gob.mx,
         WHOIS, crt.sh, Wayback Machine, Gravatar
"""
import asyncio
import hashlib
from datetime import datetime
from config import logger
from shared.rate_limiter import rate_limited
from modules.public_records.models import PublicRecordResult
import httpx


# ────────────────────────────────────────────
# 1. CURP — Registro Nacional de Poblacion
# ────────────────────────────────────────────
@rate_limited("default")
async def search_curp(nombre: str, curp: str = None) -> PublicRecordResult:
    """Validate/search CURP via RENAPO public endpoint."""
    try:
        if curp:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"https://www.gob.mx/curp/api/validate/{curp}",
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                if resp.status_code == 200:
                    return PublicRecordResult(
                        fuente="RENAPO/CURP", tipo="curp",
                        datos=resp.json(),
                        url_fuente="https://www.gob.mx/curp/"
                    )

        # Scrape CURP lookup page
        from shared.webdriver import get_driver, human_delay, is_blocked
        from selenium.webdriver.common.by import By

        with get_driver(stealth=True, use_proxy=True) as driver:
            driver.get("https://www.gob.mx/curp/")
            human_delay(2.0, 4.0)
            block = is_blocked(driver)
            if block:
                return PublicRecordResult(fuente="RENAPO/CURP", tipo="curp", disponible=False, error=f"Blocked: {block}")

            page_text = driver.page_source
            return PublicRecordResult(
                fuente="RENAPO/CURP", tipo="curp",
                datos={"nombre_buscado": nombre, "curp": curp, "pagina_disponible": True},
                url_fuente="https://www.gob.mx/curp/"
            )
    except Exception as e:
        return PublicRecordResult(fuente="RENAPO/CURP", tipo="curp", disponible=False, error=str(e))


# ────────────────────────────────────────────
# 2. RFC — SAT (Servicio de Administracion Tributaria)
# ────────────────────────────────────────────
@rate_limited("default")
async def search_rfc(nombre: str, rfc: str = None) -> PublicRecordResult:
    """Search RFC in SAT public lists (69, 69-B)."""
    try:
        results = {}
        async with httpx.AsyncClient(timeout=20) as client:
            # Lista 69 — contribuyentes incumplidos
            resp = await client.get(
                "https://www.sat.gob.mx/consultas/76674/consulta-la-relacion-de-contribuyentes-incumplidos",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            results["lista_69_disponible"] = resp.status_code == 200

            # Lista 69-B — operaciones simuladas (EFOS)
            resp2 = await client.get(
                "https://www.sat.gob.mx/consultas/76674/consulta-la-relacion-de-contribuyentes-incumplidos",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            results["lista_69b_disponible"] = resp2.status_code == 200

        if rfc:
            results["rfc_buscado"] = rfc

        # Scrape SAT for name/RFC match
        from shared.webdriver import get_driver, human_delay
        with get_driver(stealth=True, use_proxy=True) as driver:
            # Listado completo 69-B (EFOS)
            driver.get("https://efos.sat.gob.mx/")
            human_delay(2.0, 4.0)
            try:
                from selenium.webdriver.common.by import By
                search_box = driver.find_element(By.CSS_SELECTOR, "input[type='text'], input[type='search'], #rfc")
                search_term = rfc if rfc else nombre
                search_box.clear()
                search_box.send_keys(search_term)
                human_delay(1.0, 2.0)
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit'], .btn-buscar")
                    btn.click()
                    human_delay(3.0, 5.0)
                except Exception:
                    pass
                results["efos_page_title"] = driver.title
                results["efos_page_text"] = driver.find_element(By.TAG_NAME, "body").text[:2000]
            except Exception as e:
                results["efos_error"] = str(e)

        return PublicRecordResult(
            fuente="SAT/RFC", tipo="rfc",
            datos=results,
            url_fuente="https://efos.sat.gob.mx/"
        )
    except Exception as e:
        return PublicRecordResult(fuente="SAT/RFC", tipo="rfc", disponible=False, error=str(e))


# ────────────────────────────────────────────
# 3. REPUVE — Registro Publico Vehicular
# ────────────────────────────────────────────
@rate_limited("default")
async def search_repuve(placa: str = None, niv: str = None) -> PublicRecordResult:
    """Search REPUVE for stolen/registered vehicles."""
    try:
        from shared.webdriver import get_driver, human_delay
        from selenium.webdriver.common.by import By

        with get_driver(stealth=True, use_proxy=True) as driver:
            driver.get("https://www2.repuve.gob.mx:8443/ciudadania/")
            human_delay(2.0, 4.0)

            results = {"placa": placa, "niv": niv}

            if placa:
                try:
                    input_placa = driver.find_element(By.ID, "placa")
                    input_placa.clear()
                    input_placa.send_keys(placa)
                    human_delay(1.0, 2.0)
                    btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
                    btn.click()
                    human_delay(3.0, 5.0)
                    results["resultado_placa"] = driver.find_element(By.TAG_NAME, "body").text[:2000]
                except Exception as e:
                    results["placa_error"] = str(e)

            if niv:
                try:
                    driver.get("https://www2.repuve.gob.mx:8443/ciudadania/")
                    human_delay(2.0, 3.0)
                    input_niv = driver.find_element(By.ID, "niv")
                    input_niv.clear()
                    input_niv.send_keys(niv)
                    human_delay(1.0, 2.0)
                    btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
                    btn.click()
                    human_delay(3.0, 5.0)
                    results["resultado_niv"] = driver.find_element(By.TAG_NAME, "body").text[:2000]
                except Exception as e:
                    results["niv_error"] = str(e)

            return PublicRecordResult(
                fuente="REPUVE", tipo="vehiculo",
                datos=results,
                url_fuente="https://www2.repuve.gob.mx:8443/ciudadania/"
            )
    except Exception as e:
        return PublicRecordResult(fuente="REPUVE", tipo="vehiculo", disponible=False, error=str(e))


# ────────────────────────────────────────────
# 4. Buholegal — Denuncias publicas, expedientes judiciales
# ────────────────────────────────────────────
@rate_limited("default")
async def search_buholegal(nombre: str) -> PublicRecordResult:
    """Search Buholegal.com for public legal records, complaints, lawsuits."""
    try:
        from shared.webdriver import get_driver, human_delay
        from selenium.webdriver.common.by import By

        with get_driver(stealth=True, use_proxy=True) as driver:
            # Buholegal search
            search_url = f"https://www.buholegal.com/buscar/?q={nombre.replace(' ', '+')}"
            driver.get(search_url)
            human_delay(3.0, 5.0)

            results = []
            try:
                items = driver.find_elements(By.CSS_SELECTOR, ".resultado, .search-result, .item, article, .card")
                for item in items[:20]:
                    try:
                        titulo = item.find_element(By.CSS_SELECTOR, "h2, h3, h4, .title, a").text
                        try:
                            link = item.find_element(By.CSS_SELECTOR, "a").get_attribute("href")
                        except Exception:
                            link = None
                        try:
                            descripcion = item.find_element(By.CSS_SELECTOR, "p, .description, .snippet").text
                        except Exception:
                            descripcion = item.text[:300]

                        results.append({
                            "titulo": titulo,
                            "url": link,
                            "descripcion": descripcion,
                        })
                    except Exception:
                        results.append({"texto": item.text[:500]})
            except Exception:
                pass

            # Also get full page text as fallback
            page_text = driver.find_element(By.TAG_NAME, "body").text[:3000]

            return PublicRecordResult(
                fuente="Buholegal", tipo="legal",
                datos={"resultados": results, "texto_pagina": page_text, "url": search_url},
                url_fuente=search_url
            )
    except Exception as e:
        return PublicRecordResult(fuente="Buholegal", tipo="legal", disponible=False, error=str(e))


# ────────────────────────────────────────────
# 5. Poder Judicial — CJF (Consejo de la Judicatura Federal)
# ────────────────────────────────────────────
@rate_limited("default")
async def search_poder_judicial(nombre: str) -> PublicRecordResult:
    """Search expedientes judiciales in CJF / Poder Judicial."""
    try:
        from shared.webdriver import get_driver, human_delay
        from selenium.webdriver.common.by import By

        with get_driver(stealth=True, use_proxy=True) as driver:
            # Consulta de expedientes CJF
            driver.get("https://www.cjf.gob.mx/micrositios/DGEPJ/paginas/serviciosenlinea.htm")
            human_delay(2.0, 4.0)

            results = {"nombre_buscado": nombre}

            # Try SISE (Sistema Integral de Seguimiento de Expedientes)
            driver.get("https://sise.cjf.gob.mx/consultasvp/default.aspx")
            human_delay(2.0, 4.0)

            try:
                search_fields = driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
                if search_fields:
                    search_fields[0].clear()
                    search_fields[0].send_keys(nombre)
                    human_delay(1.0, 2.0)
                    try:
                        btn = driver.find_element(By.CSS_SELECTOR, "input[type='submit'], button[type='submit'], .btn")
                        btn.click()
                        human_delay(3.0, 5.0)
                    except Exception:
                        pass
                results["sise_resultado"] = driver.find_element(By.TAG_NAME, "body").text[:3000]
            except Exception as e:
                results["sise_error"] = str(e)

            results["page_title"] = driver.title

            return PublicRecordResult(
                fuente="Poder Judicial/CJF", tipo="expediente_judicial",
                datos=results,
                url_fuente="https://sise.cjf.gob.mx/"
            )
    except Exception as e:
        return PublicRecordResult(fuente="Poder Judicial/CJF", tipo="expediente_judicial", disponible=False, error=str(e))


# ────────────────────────────────────────────
# 6. DENUE/INEGI — Directorio Estadistico Nacional de Unidades Economicas
# ────────────────────────────────────────────
@rate_limited("default")
async def search_denue(nombre: str, zona: str = None) -> PublicRecordResult:
    """Search DENUE API for businesses associated with a person."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            # DENUE public API (no key needed)
            params = {"nombre": nombre}
            if zona:
                params["entidad"] = zona

            # INEGI API v2
            area = "0"  # Nacional
            resp = await client.get(
                f"https://www.inegi.org.mx/app/api/denue/v1/consulta/Buscar/{nombre}/{area}/1/50/0/0/0/true",
                headers={"User-Agent": "Mozilla/5.0"},
                follow_redirects=True,
            )

            results = []
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if isinstance(data, list):
                        for item in data[:30]:
                            results.append(item)
                except Exception:
                    results = [{"raw_text": resp.text[:3000]}]

            return PublicRecordResult(
                fuente="DENUE/INEGI", tipo="empresa",
                datos=results,
                url_fuente="https://www.inegi.org.mx/app/mapa/denue/default.aspx"
            )
    except Exception as e:
        return PublicRecordResult(fuente="DENUE/INEGI", tipo="empresa", disponible=False, error=str(e))


# ────────────────────────────────────────────
# 7. datos.gob.mx — Portal de datos abiertos
# ────────────────────────────────────────────
@rate_limited("default")
async def search_datos_gob(nombre: str) -> PublicRecordResult:
    """Search datos.gob.mx open data portal."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "https://datos.gob.mx/busca/api/3/action/package_search",
                params={"q": nombre, "rows": 20},
                headers={"User-Agent": "Mozilla/5.0"},
                follow_redirects=True,
            )
            results = []
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    for pkg in data.get("result", {}).get("results", []):
                        results.append({
                            "titulo": pkg.get("title"),
                            "descripcion": pkg.get("notes", "")[:300],
                            "organizacion": pkg.get("organization", {}).get("title"),
                            "url": f"https://datos.gob.mx/busca/dataset/{pkg.get('name')}",
                            "recursos": len(pkg.get("resources", [])),
                            "fecha": pkg.get("metadata_modified"),
                        })

            return PublicRecordResult(
                fuente="datos.gob.mx", tipo="datos_abiertos",
                datos=results,
                url_fuente="https://datos.gob.mx/"
            )
    except Exception as e:
        return PublicRecordResult(fuente="datos.gob.mx", tipo="datos_abiertos", disponible=False, error=str(e))


# ────────────────────────────────────────────
# 8. PGJ/FGJ — Fiscalia General de Justicia (denuncias publicas)
# ────────────────────────────────────────────
@rate_limited("default")
async def search_fiscalia(nombre: str) -> PublicRecordResult:
    """Search public records from Fiscalia/PGJ Mexico."""
    try:
        from shared.webdriver import get_driver, human_delay
        from selenium.webdriver.common.by import By

        results = []

        with get_driver(stealth=True, use_proxy=True) as driver:
            # FGR — Fiscalia General de la Republica (personas desaparecidas, ordenes de aprehension)
            driver.get("https://www.gob.mx/fgr")
            human_delay(2.0, 3.0)

            # Personas buscadas / ordenes de aprehension
            driver.get(f"https://www.gob.mx/busqueda?utf8=%E2%9C%93&site=fgr&q={nombre.replace(' ', '+')}")
            human_delay(3.0, 5.0)

            try:
                items = driver.find_elements(By.CSS_SELECTOR, ".list-group-item, .search-result, article, .result")
                for item in items[:15]:
                    try:
                        results.append({
                            "titulo": item.find_element(By.CSS_SELECTOR, "h3, h4, a, .title").text,
                            "texto": item.text[:500],
                            "url": item.find_element(By.CSS_SELECTOR, "a").get_attribute("href") if item.find_elements(By.CSS_SELECTOR, "a") else None,
                        })
                    except Exception:
                        results.append({"texto": item.text[:500]})
            except Exception:
                pass

            page_text = driver.find_element(By.TAG_NAME, "body").text[:3000]

        return PublicRecordResult(
            fuente="FGR/Fiscalia", tipo="denuncia",
            datos={"resultados": results, "texto_pagina": page_text},
            url_fuente=f"https://www.gob.mx/busqueda?site=fgr&q={nombre.replace(' ', '+')}"
        )
    except Exception as e:
        return PublicRecordResult(fuente="FGR/Fiscalia", tipo="denuncia", disponible=False, error=str(e))


# ────────────────────────────────────────────
# 9. Padron de proveedores sancionados (SFP)
# ────────────────────────────────────────────
@rate_limited("default")
async def search_proveedores_sancionados(nombre: str) -> PublicRecordResult:
    """Search SFP sanctioned suppliers/servants list."""
    try:
        from shared.webdriver import get_driver, human_delay
        from selenium.webdriver.common.by import By

        with get_driver(stealth=True, use_proxy=True) as driver:
            # Plataforma Digital Nacional — servidores sancionados
            driver.get("https://www.plataformadigitalnacional.org/servidores")
            human_delay(2.0, 4.0)

            results = {}
            try:
                search_box = driver.find_element(By.CSS_SELECTOR, "input[type='text'], input[type='search']")
                search_box.clear()
                search_box.send_keys(nombre)
                human_delay(2.0, 3.0)
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], .btn-search, button.search")
                    btn.click()
                    human_delay(3.0, 5.0)
                except Exception:
                    from selenium.webdriver.common.keys import Keys
                    search_box.send_keys(Keys.RETURN)
                    human_delay(3.0, 5.0)

                results["pdn_resultado"] = driver.find_element(By.TAG_NAME, "body").text[:3000]
            except Exception as e:
                results["pdn_error"] = str(e)

            # DirectorioSancionados SFP
            driver.get(f"https://directoriosancionados.funcionpublica.gob.mx/SanFicTec/jsp/Ficha_Tecnica/SancionadosN.htm")
            human_delay(2.0, 4.0)
            try:
                search_box = driver.find_element(By.CSS_SELECTOR, "input[type='text'], input[name='nombre']")
                search_box.clear()
                search_box.send_keys(nombre)
                human_delay(1.0, 2.0)
                btn = driver.find_element(By.CSS_SELECTOR, "input[type='submit'], button[type='submit']")
                btn.click()
                human_delay(3.0, 5.0)
                results["sfp_resultado"] = driver.find_element(By.TAG_NAME, "body").text[:3000]
            except Exception as e:
                results["sfp_error"] = str(e)

            return PublicRecordResult(
                fuente="SFP/PDN", tipo="servidor_sancionado",
                datos=results,
                url_fuente="https://www.plataformadigitalnacional.org/servidores"
            )
    except Exception as e:
        return PublicRecordResult(fuente="SFP/PDN", tipo="servidor_sancionado", disponible=False, error=str(e))


# ────────────────────────────────────────────
# 10. WHOIS — Domain lookup (if email domain or website given)
# ────────────────────────────────────────────
@rate_limited("default")
async def search_whois(domain: str) -> PublicRecordResult:
    """WHOIS lookup for a domain."""
    try:
        import whois
        w = whois.whois(domain)
        data = {
            "domain": domain,
            "registrar": w.registrar,
            "creation_date": str(w.creation_date),
            "expiration_date": str(w.expiration_date),
            "name_servers": w.name_servers,
            "registrant": w.get("registrant_name") or w.get("name"),
            "org": w.get("org"),
            "country": w.get("country"),
            "state": w.get("state"),
            "emails": w.emails if hasattr(w, "emails") else None,
        }
        return PublicRecordResult(fuente="WHOIS", tipo="dominio", datos=data)
    except Exception as e:
        return PublicRecordResult(fuente="WHOIS", tipo="dominio", disponible=False, error=str(e))


# ────────────────────────────────────────────
# 11. crt.sh — Certificate Transparency
# ────────────────────────────────────────────
@rate_limited("default")
async def search_crtsh(domain: str) -> PublicRecordResult:
    """Search Certificate Transparency logs for subdomains."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"https://crt.sh/?q=%25.{domain}&output=json",
                follow_redirects=True,
            )
            results = []
            if resp.status_code == 200:
                data = resp.json()
                seen = set()
                for cert in data:
                    name = cert.get("name_value", "")
                    if name not in seen:
                        seen.add(name)
                        results.append({
                            "nombre": name,
                            "issuer": cert.get("issuer_name"),
                            "fecha": cert.get("not_before"),
                            "id": cert.get("id"),
                        })
            return PublicRecordResult(
                fuente="crt.sh", tipo="certificado",
                datos=results[:50],
                url_fuente=f"https://crt.sh/?q=%25.{domain}"
            )
    except Exception as e:
        return PublicRecordResult(fuente="crt.sh", tipo="certificado", disponible=False, error=str(e))


# ────────────────────────────────────────────
# 12. Wayback Machine — historical snapshots
# ────────────────────────────────────────────
@rate_limited("default")
async def search_wayback(url_or_domain: str) -> PublicRecordResult:
    """Search Internet Archive Wayback Machine for historical snapshots."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            # CDX API for all captures
            resp = await client.get(
                f"https://web.archive.org/cdx/search/cdx?url={url_or_domain}&output=json&limit=30&fl=timestamp,original,statuscode,mimetype",
                follow_redirects=True,
            )
            results = []
            if resp.status_code == 200:
                data = resp.json()
                headers = data[0] if data else []
                for row in data[1:]:
                    entry = dict(zip(headers, row))
                    entry["wayback_url"] = f"https://web.archive.org/web/{entry.get('timestamp')}/{entry.get('original')}"
                    results.append(entry)

            return PublicRecordResult(
                fuente="Wayback Machine", tipo="historial_web",
                datos=results,
                url_fuente=f"https://web.archive.org/web/*/{url_or_domain}"
            )
    except Exception as e:
        return PublicRecordResult(fuente="Wayback Machine", tipo="historial_web", disponible=False, error=str(e))


# ────────────────────────────────────────────
# 13. Gravatar — avatar by email
# ────────────────────────────────────────────
@rate_limited("default")
async def search_gravatar(email: str) -> PublicRecordResult:
    """Get Gravatar profile by email hash."""
    try:
        email_hash = hashlib.md5(email.strip().lower().encode()).hexdigest()
        async with httpx.AsyncClient(timeout=10) as client:
            # Profile JSON
            resp = await client.get(
                f"https://en.gravatar.com/{email_hash}.json",
                follow_redirects=True,
            )
            profile = None
            if resp.status_code == 200:
                profile = resp.json()

            return PublicRecordResult(
                fuente="Gravatar", tipo="avatar",
                datos={
                    "email_hash": email_hash,
                    "avatar_url": f"https://www.gravatar.com/avatar/{email_hash}?s=400&d=404",
                    "profile": profile,
                }
            )
    except Exception as e:
        return PublicRecordResult(fuente="Gravatar", tipo="avatar", disponible=False, error=str(e))


# ────────────────────────────────────────────
# 14. Google Dorks — legal/government records
# ────────────────────────────────────────────
@rate_limited("google")
async def search_google_legal(nombre: str) -> PublicRecordResult:
    """Google dorks for legal/government records about a person."""
    try:
        from modules.google_search.service import search_google
        dorks = [
            f'"{nombre}" site:gob.mx',
            f'"{nombre}" site:buholegal.com',
            f'"{nombre}" denuncia OR demanda OR sentencia OR expediente',
            f'"{nombre}" site:poderjudicialfederacion.gob.mx',
            f'"{nombre}" antecedentes OR investigacion OR proceso penal',
            f'"{nombre}" site:dof.gob.mx',  # Diario Oficial de la Federacion
        ]

        all_results = []
        for dork in dorks:
            try:
                results = await search_google(query=dork, max_results=5)
                for r in results:
                    all_results.append(r.model_dump() if hasattr(r, "model_dump") else r)
            except Exception as e:
                all_results.append({"dork": dork, "error": str(e)})

        return PublicRecordResult(
            fuente="Google Dorks Legal", tipo="legal_google",
            datos=all_results
        )
    except Exception as e:
        return PublicRecordResult(fuente="Google Dorks Legal", tipo="legal_google", disponible=False, error=str(e))


# ────────────────────────────────────────────
# 15. DOF — Diario Oficial de la Federacion
# ────────────────────────────────────────────
@rate_limited("default")
async def search_dof(nombre: str) -> PublicRecordResult:
    """Search Diario Oficial de la Federacion."""
    try:
        from shared.webdriver import get_driver, human_delay
        from selenium.webdriver.common.by import By

        with get_driver(stealth=True, use_proxy=True) as driver:
            driver.get(f"https://www.dof.gob.mx/busqueda_detalle.php?busqueda={nombre.replace(' ', '+')}&tipo=T")
            human_delay(3.0, 5.0)

            results = []
            try:
                items = driver.find_elements(By.CSS_SELECTOR, "tr, .resultado, article")
                for item in items[:20]:
                    text = item.text.strip()
                    if text and len(text) > 20:
                        try:
                            link = item.find_element(By.CSS_SELECTOR, "a").get_attribute("href")
                        except Exception:
                            link = None
                        results.append({"texto": text[:500], "url": link})
            except Exception:
                pass

            page_text = driver.find_element(By.TAG_NAME, "body").text[:3000]
            return PublicRecordResult(
                fuente="DOF", tipo="diario_oficial",
                datos={"resultados": results, "texto_pagina": page_text},
                url_fuente=f"https://www.dof.gob.mx/busqueda_detalle.php?busqueda={nombre.replace(' ', '+')}"
            )
    except Exception as e:
        return PublicRecordResult(fuente="DOF", tipo="diario_oficial", disponible=False, error=str(e))


# ────────────────────────────────────────────
# 16. Compranet — Licitaciones y contratos publicos
# ────────────────────────────────────────────
@rate_limited("default")
async def search_compranet(nombre: str) -> PublicRecordResult:
    """Search Compranet for public procurement contracts."""
    try:
        from shared.webdriver import get_driver, human_delay
        from selenium.webdriver.common.by import By

        with get_driver(stealth=True, use_proxy=True) as driver:
            driver.get("https://compranet.hacienda.gob.mx/esop/guest/go/public/opportunity/past")
            human_delay(3.0, 5.0)

            results = {}
            try:
                search_box = driver.find_element(By.CSS_SELECTOR, "input[type='text'], input[type='search']")
                search_box.clear()
                search_box.send_keys(nombre)
                human_delay(1.0, 2.0)
                from selenium.webdriver.common.keys import Keys
                search_box.send_keys(Keys.RETURN)
                human_delay(3.0, 5.0)
                results["texto"] = driver.find_element(By.TAG_NAME, "body").text[:3000]
            except Exception as e:
                results["error"] = str(e)

            return PublicRecordResult(
                fuente="Compranet", tipo="contrato_publico",
                datos=results,
                url_fuente="https://compranet.hacienda.gob.mx/"
            )
    except Exception as e:
        return PublicRecordResult(fuente="Compranet", tipo="contrato_publico", disponible=False, error=str(e))


# ════════════════════════════════════════════
# UNIFIED: Full person dossier from all public sources
# ════════════════════════════════════════════
async def build_dossier(
    nombre: str,
    curp: str = None,
    rfc: str = None,
    email: str = None,
    telefono: str = None,
    username: str = None,
    domicilio: str = None,
    alias: str = None,
    zona_geografica: str = None,
    placa: str = None,
    niv: str = None,
    group_ids: list[str] = None,
    include_social: bool = True,
    include_legal: bool = True,
    include_vehiculos: bool = True,
    include_gobierno: bool = True,
    include_dark_web: bool = False,
    include_gaming: bool = False,
) -> dict:
    """
    Build a complete person dossier — ancestry-style.
    Runs ALL available sources in parallel and returns everything found.
    """
    from modules.public_records.models import PersonDossierResponse

    dossier = PersonDossierResponse(
        nombre=nombre, curp=curp, rfc=rfc, email=email,
        telefono=telefono, username=username, domicilio=domicilio,
        alias=alias, zona_geografica=zona_geografica,
    )

    tasks = {}

    # ── Public Records (government / legal) ──
    if include_legal:
        tasks["buholegal"] = search_buholegal(nombre)
        tasks["poder_judicial"] = search_poder_judicial(nombre)
        tasks["fiscalia"] = search_fiscalia(nombre)
        tasks["proveedores_sancionados"] = search_proveedores_sancionados(nombre)
        tasks["google_legal"] = search_google_legal(nombre)
        tasks["dof"] = search_dof(nombre)
        tasks["compranet"] = search_compranet(nombre)

    if include_gobierno:
        tasks["curp"] = search_curp(nombre, curp)
        tasks["rfc"] = search_rfc(nombre, rfc)
        tasks["denue"] = search_denue(nombre, zona_geografica)
        tasks["datos_gob"] = search_datos_gob(nombre)

    if include_vehiculos and (placa or niv):
        tasks["repuve"] = search_repuve(placa, niv)

    # ── Digital footprint ──
    if email:
        domain = email.split("@")[-1] if "@" in email else None
        tasks["gravatar"] = search_gravatar(email)
        if domain and domain not in ("gmail.com", "hotmail.com", "yahoo.com", "outlook.com"):
            tasks["whois"] = search_whois(domain)
            tasks["crtsh"] = search_crtsh(domain)
            tasks["wayback"] = search_wayback(domain)

    # ── Social media & other OSINT (reuse person_search) ──
    if include_social:
        from modules.person_search.service import search_person
        tasks["social_osint"] = search_person(
            nombre=nombre, email=email, telefono=telefono,
            username=username, domicilio=domicilio, alias=alias,
            zona_geografica=zona_geografica, group_ids=group_ids,
            include_dorks=True, include_marketplace=True,
            include_news=True, include_dark_web=include_dark_web,
            include_gaming=include_gaming,
        )

    # Execute all in parallel
    keys = list(tasks.keys())
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    for key, result in zip(keys, results):
        if key == "social_osint":
            # Merge social results into dossier
            if isinstance(result, Exception):
                dossier.registros.append(PublicRecordResult(
                    fuente="social_osint", tipo="redes_sociales", disponible=False, error=str(result)
                ))
            else:
                dossier.redes_sociales = [p.model_dump() for p in result.plataformas]
        elif isinstance(result, Exception):
            dossier.registros.append(PublicRecordResult(
                fuente=key, tipo="error", disponible=False, error=str(result)
            ))
        else:
            dossier.registros.append(result)

    # Count totals
    dossier.total_fuentes = len(dossier.registros) + len(dossier.redes_sociales)
    total = 0
    for r in dossier.registros:
        if r.datos:
            if isinstance(r.datos, list):
                total += len(r.datos)
            elif isinstance(r.datos, dict):
                total += sum(len(v) if isinstance(v, list) else 1 for v in r.datos.values())
            else:
                total += 1
    for s in dossier.redes_sociales:
        if s.get("resultados"):
            r = s["resultados"]
            if isinstance(r, list):
                total += len(r)
            elif isinstance(r, dict):
                total += sum(len(v) if isinstance(v, list) else 1 for v in r.values())
            else:
                total += 1
    dossier.total_resultados = total

    return dossier.model_dump()
