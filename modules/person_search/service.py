"""Person Search Engine — unified search across ALL platforms"""
import asyncio
from config import logger
from modules.person_search.models import PlatformResult, PersonSearchResponse


async def _search_twitter(query: str, username: str = None) -> PlatformResult:
    try:
        from modules.osint_social.twitter_service import search, get_health
        health = get_health()
        if not health.available:
            return PlatformResult(plataforma="twitter", disponible=False, error=health.reason)
        results = await search(query=query, user=username, max_results=10)
        return PlatformResult(plataforma="twitter", disponible=True, resultados=[r.model_dump() for r in results])
    except Exception as e:
        return PlatformResult(plataforma="twitter", disponible=False, error=str(e))


async def _search_instagram(username: str = None) -> PlatformResult:
    try:
        from modules.osint_social.instagram_service import search, get_health
        health = get_health()
        if not health.available:
            return PlatformResult(plataforma="instagram", disponible=False, error=health.reason)
        results = await search(username=username)
        resultados = [r.model_dump() for r in results]

        # Enrich with Toutatis (phone, email, extended data)
        if username:
            try:
                from modules.osint_tools.service import enrich_instagram
                enrichment = await enrich_instagram(username)
                if not enrichment.error:
                    resultados.append({"_toutatis_enrichment": enrichment.model_dump()})
            except Exception as e:
                logger.warning(f"Toutatis enrichment failed for {username}: {e}")

        return PlatformResult(plataforma="instagram", disponible=True, resultados=resultados)
    except Exception as e:
        return PlatformResult(plataforma="instagram", disponible=False, error=str(e))


async def _search_tiktok(username: str = None, query: str = None) -> PlatformResult:
    try:
        from modules.osint_social.tiktok_service import search, get_health
        health = get_health()
        if not health.available:
            return PlatformResult(plataforma="tiktok", disponible=False, error=health.reason)
        results = await search(username=username, query=query, max_results=10)
        return PlatformResult(plataforma="tiktok", disponible=True, resultados=[r.model_dump() for r in results])
    except Exception as e:
        return PlatformResult(plataforma="tiktok", disponible=False, error=str(e))


async def _search_telegram(query: str) -> PlatformResult:
    try:
        from modules.osint_social.telegram_service import search, get_health
        health = get_health()
        if not health.available:
            return PlatformResult(plataforma="telegram", disponible=False, error=health.reason)
        results = await search(query=query, max_results=10)
        return PlatformResult(plataforma="telegram", disponible=True, resultados=[r.model_dump() for r in results])
    except Exception as e:
        return PlatformResult(plataforma="telegram", disponible=False, error=str(e))


async def _search_forums(query: str) -> PlatformResult:
    try:
        from modules.osint_social.forums_service import search, get_health
        health = get_health()
        if not health.available:
            return PlatformResult(plataforma="reddit", disponible=False, error=health.reason)
        results = await search(query=query, max_results=10)
        return PlatformResult(plataforma="reddit", disponible=True, resultados=[r.model_dump() for r in results])
    except Exception as e:
        return PlatformResult(plataforma="reddit", disponible=False, error=str(e))


async def _search_email(email: str) -> PlatformResult:
    try:
        from modules.osint_specialized.email_service import search
        results = await search(email)
        return PlatformResult(plataforma="email_osint", disponible=True, resultados=results)
    except Exception as e:
        return PlatformResult(plataforma="email_osint", disponible=False, error=str(e))


async def _search_phone(phone: str) -> PlatformResult:
    try:
        from modules.osint_specialized.phone_service import search
        results = await search(phone)
        return PlatformResult(plataforma="phone_osint", disponible=True, resultados=results)
    except Exception as e:
        return PlatformResult(plataforma="phone_osint", disponible=False, error=str(e))


async def _search_google(query: str, max_captures: int) -> PlatformResult:
    try:
        from modules.google_search.service import search_and_capture
        results = await search_and_capture(query=query, max_results=10, max_captures=max_captures)
        return PlatformResult(plataforma="google", disponible=True, resultados=results.model_dump())
    except Exception as e:
        return PlatformResult(plataforma="google", disponible=False, error=str(e))


async def _search_google_dorks(name: str) -> PlatformResult:
    """Search person across Facebook, LinkedIn, YouTube, etc. via Google dorks."""
    try:
        from modules.google_search.service import dork_search_person
        results = await dork_search_person(name)
        return PlatformResult(plataforma="google_dorks", disponible=True, resultados=results)
    except Exception as e:
        return PlatformResult(plataforma="google_dorks", disponible=False, error=str(e))


async def _search_marketplace(name: str) -> PlatformResult:
    """Search Facebook Marketplace for person-related listings."""
    try:
        from modules.marketplace.service import scrape_marketplace
        results = scrape_marketplace(
            city="mexico", product=name,
            min_price=0, max_price=999999,
            days_listed=30, max_results=10,
        )
        return PlatformResult(plataforma="marketplace", disponible=True, resultados=results)
    except Exception as e:
        return PlatformResult(plataforma="marketplace", disponible=False, error=str(e))


async def _search_groups(name: str, group_ids: list[str] = None) -> PlatformResult:
    """Search Facebook Groups for mentions of person."""
    try:
        from modules.groups.service import get_group_posts_by_keyword
        all_results = []
        groups_to_search = group_ids or []
        for gid in groups_to_search:
            try:
                posts = get_group_posts_by_keyword(
                    group_id=gid, keyword=name,
                    max_posts=20, case_sensitive=False,
                )
                for post in posts:
                    all_results.append(post.model_dump())
            except Exception as e:
                logger.warning(f"Group {gid} search error: {e}")
        return PlatformResult(plataforma="facebook_groups", disponible=True, resultados=all_results)
    except Exception as e:
        return PlatformResult(plataforma="facebook_groups", disponible=False, error=str(e))


async def _search_news(name: str) -> PlatformResult:
    """Search news articles mentioning person."""
    try:
        from modules.news.service import fetch_news_with_content
        results = fetch_news_with_content(
            query=name, language="es", country="MX",
            max_results=5, include_content=False,
        )
        return PlatformResult(plataforma="news", disponible=True, resultados=results)
    except Exception as e:
        return PlatformResult(plataforma="news", disponible=False, error=str(e))


async def _search_gaming(username: str) -> PlatformResult:
    """Search gaming platforms (Steam, Xbox)."""
    try:
        from modules.gaming.service import search_all
        results = await search_all(username)
        return PlatformResult(plataforma="gaming", disponible=True, resultados=[r.model_dump() for r in results])
    except Exception as e:
        return PlatformResult(plataforma="gaming", disponible=False, error=str(e))


async def _search_username_enum(username: str) -> PlatformResult:
    """Enumerate username across 400+ platforms (findme) + enrich top profiles with socid-extractor."""
    try:
        from modules.username_enum.service import enumerate_username
        result = await enumerate_username(username, max_concurrent=50)

        platforms_found = [h.model_dump() for h in result.platforms_found]

        # Enrich top 10 found profiles with socid-extractor
        profile_extractions = []
        try:
            from modules.osint_tools.service import extract_profiles_batch
            top_urls = [h.url for h in result.platforms_found[:10] if h.url]
            if top_urls:
                extractions = await extract_profiles_batch(top_urls)
                profile_extractions = [e.model_dump() for e in extractions if e.fields]
        except Exception as e:
            logger.warning(f"socid-extractor enrichment failed: {e}")

        return PlatformResult(
            plataforma="username_enum",
            disponible=True,
            resultados={
                "username": result.username,
                "total_found": result.total_found,
                "total_checked": result.total_checked,
                "platforms_found": platforms_found,
                "profile_extractions": profile_extractions,
                "errors_count": len(result.errors),
            },
        )
    except Exception as e:
        return PlatformResult(plataforma="username_enum", disponible=False, error=str(e))


async def _search_github(username: str) -> PlatformResult:
    """Deep GitHub OSINT — emails from commits/GPG, SSH keys, repos."""
    try:
        from modules.osint_tools.service import github_osint
        result = await github_osint(username)
        if result.error:
            return PlatformResult(plataforma="github", disponible=False, error=result.error)
        return PlatformResult(plataforma="github", disponible=True, resultados=result.model_dump())
    except Exception as e:
        return PlatformResult(plataforma="github", disponible=False, error=str(e))


async def _search_twitch(username: str) -> PlatformResult:
    """Twitch profile lookup."""
    try:
        from modules.osint_tools.service import twitch_lookup
        result = await twitch_lookup(username)
        if result.error:
            return PlatformResult(plataforma="twitch", disponible=False, error=result.error)
        return PlatformResult(plataforma="twitch", disponible=True, resultados=result.model_dump())
    except Exception as e:
        return PlatformResult(plataforma="twitch", disponible=False, error=str(e))


async def _search_dark_web(query: str) -> PlatformResult:
    """Search dark web / .onion sites."""
    try:
        from modules.dark_web.service import get_searcher
        searcher = get_searcher()
        results = searcher.search(query)
        return PlatformResult(plataforma="dark_web", disponible=True, resultados=results[:10])
    except Exception as e:
        return PlatformResult(plataforma="dark_web", disponible=False, error=str(e))


async def search_person(
    nombre: str,
    email: str = None,
    telefono: str = None,
    username: str = None,
    domicilio: str = None,
    alias: str = None,
    zona_geografica: str = None,
    group_ids: list[str] = None,
    max_google_captures: int = 5,
    include_dorks: bool = True,
    include_marketplace: bool = True,
    include_news: bool = True,
    include_dark_web: bool = False,
    include_gaming: bool = False,
    include_username_enum: bool = True,
    include_github: bool = True,
    include_twitch: bool = True,
) -> PersonSearchResponse:
    """
    Busca una persona en TODAS las plataformas disponibles simultaneamente.

    Fuentes directas: Google, Twitter, Instagram, TikTok, Telegram, Reddit
    Google Dorks: Facebook, LinkedIn, YouTube, GitHub, Pinterest, Medium, Quora
    Facebook: Marketplace, Groups
    Noticias: Google News
    Especializadas: Email (Hunter.io + HIBP), Telefono (NumVerify)
    """
    response = PersonSearchResponse(
        nombre=nombre, email=email, telefono=telefono, username=username
    )

    # Build search query — combine name with alias if available
    search_query = nombre
    if alias:
        search_query = f"{nombre} OR {alias}"

    # Build tasks — all run in parallel
    tasks = {
        "google": _search_google(search_query, max_google_captures),
        "twitter": _search_twitter(search_query, username),
        "tiktok": _search_tiktok(username=username, query=search_query),
        "telegram": _search_telegram(search_query),
        "forums": _search_forums(search_query),
    }

    # Google dorks: busca en Facebook, LinkedIn, YouTube, GitHub, etc.
    if include_dorks:
        tasks["google_dorks"] = _search_google_dorks(nombre)

    if username:
        tasks["instagram"] = _search_instagram(username)

    if email:
        tasks["email"] = _search_email(email)

    if telefono:
        tasks["phone"] = _search_phone(telefono)

    # Facebook Marketplace — search by name/alias in nearby zone
    if include_marketplace:
        marketplace_query = nombre
        if zona_geografica:
            marketplace_query = f"{nombre} {zona_geografica}"
        tasks["marketplace"] = _search_marketplace(marketplace_query)

    # Facebook Groups
    if group_ids:
        tasks["facebook_groups"] = _search_groups(nombre, group_ids)

    # News
    if include_news:
        tasks["news"] = _search_news(nombre)

    # Gaming platforms (Steam, Xbox)
    if include_gaming and username:
        tasks["gaming"] = _search_gaming(username)

    # Username enumeration (findme — 400+ platforms)
    if include_username_enum and username:
        tasks["username_enum"] = _search_username_enum(username)

    # GitHub deep OSINT (emails from commits, GPG, SSH keys)
    if include_github and username:
        tasks["github"] = _search_github(username)

    # Twitch profile lookup
    if include_twitch and username:
        tasks["twitch"] = _search_twitch(username)

    # Dark web
    if include_dark_web:
        tasks["dark_web"] = _search_dark_web(nombre)

    # If domicilio provided, search that too via Google
    if domicilio:
        tasks["google_domicilio"] = _search_google(f'"{nombre}" "{domicilio}"', max_captures=2)

    # If zona_geografica, do a geo-focused Google search
    if zona_geografica and zona_geografica != domicilio:
        tasks["google_zona"] = _search_google(f'"{nombre}" "{zona_geografica}"', max_captures=2)

    # Execute all searches in parallel
    keys = list(tasks.keys())
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    for key, result in zip(keys, results):
        if isinstance(result, Exception):
            response.plataformas.append(
                PlatformResult(plataforma=key, disponible=False, error=str(result))
            )
        else:
            response.plataformas.append(result)

    # Extract google captures separately for convenience
    google_platform = next((p for p in response.plataformas if p.plataforma == "google"), None)
    if google_platform and google_platform.resultados:
        response.google_capturas = google_platform.resultados.get("capturas")

    # Count total results
    total = 0
    for p in response.plataformas:
        if p.resultados:
            if isinstance(p.resultados, list):
                total += len(p.resultados)
            elif isinstance(p.resultados, dict):
                for v in p.resultados.values():
                    if isinstance(v, list):
                        total += len(v)
                    else:
                        total += 1
            else:
                total += 1
    response.total_resultados = total

    return response
