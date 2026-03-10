"""
PDL (People Data Labs) — Service
Person Search API: https://docs.peopledatalabs.com/docs/person-search-api
Person Enrichment API: https://docs.peopledatalabs.com/docs/person-enrichment-api

Base URL: https://api.peopledatalabs.com/v5
Auth: X-Api-Key header
"""
import json
from typing import Optional, List

import httpx

from config import settings, logger
from modules.pdl.models import (
    PDLPersonResult, PDLSearchResponse, PDLEnrichResponse,
    PDLExperience, PDLEducation, PDLProfile, PDLPhone, PDLEmail,
)

PDL_BASE = "https://api.peopledatalabs.com/v5"
PDL_TIMEOUT = 30


def _headers() -> dict:
    return {
        "X-Api-Key": settings.pdl_api_key,
        "Content-Type": "application/json",
    }


def _parse_person(raw: dict) -> PDLPersonResult:
    """Parse a raw PDL person record into our model."""
    return PDLPersonResult(
        id=raw.get("id"),
        full_name=raw.get("full_name"),
        first_name=raw.get("first_name"),
        last_name=raw.get("last_name"),
        sex=raw.get("sex"),
        birth_year=raw.get("birth_year"),
        birth_date=raw.get("birth_date"),

        # Contact
        emails=[PDLEmail(**e) for e in (raw.get("emails") or [])],
        personal_emails=raw.get("personal_emails"),
        work_email=raw.get("work_email"),
        recommended_personal_email=raw.get("recommended_personal_email"),
        phones=[PDLPhone(**p) for p in (raw.get("phones") or [])],
        phone_numbers=raw.get("phone_numbers"),
        mobile_phone=raw.get("mobile_phone"),

        # Location
        location_name=raw.get("location_name"),
        location_locality=raw.get("location_locality"),
        location_region=raw.get("location_region"),
        location_country=raw.get("location_country"),
        location_continent=raw.get("location_continent"),
        location_geo=raw.get("location_geo"),
        location_street_address=raw.get("location_street_address"),
        location_postal_code=raw.get("location_postal_code"),
        countries=raw.get("countries"),

        # Current job
        job_title=raw.get("job_title"),
        job_title_role=raw.get("job_title_role"),
        job_title_levels=raw.get("job_title_levels"),
        job_company_name=raw.get("job_company_name"),
        job_company_website=raw.get("job_company_website"),
        job_company_industry=raw.get("job_company_industry"),
        job_company_size=raw.get("job_company_size"),
        job_company_linkedin_url=raw.get("job_company_linkedin_url"),
        job_start_date=raw.get("job_start_date"),
        inferred_salary=raw.get("inferred_salary"),

        # Social
        linkedin_url=raw.get("linkedin_url"),
        linkedin_username=raw.get("linkedin_username"),
        facebook_url=raw.get("facebook_url"),
        facebook_username=raw.get("facebook_username"),
        twitter_url=raw.get("twitter_url"),
        twitter_username=raw.get("twitter_username"),
        github_url=raw.get("github_url"),
        github_username=raw.get("github_username"),
        profiles=[PDLProfile(**p) for p in (raw.get("profiles") or [])],

        # History
        experience=[
            PDLExperience(
                company_name=(exp.get("company") or {}).get("name"),
                company_size=(exp.get("company") or {}).get("size"),
                company_industry=(exp.get("company") or {}).get("industry"),
                company_website=(exp.get("company") or {}).get("website"),
                company_linkedin_url=(exp.get("company") or {}).get("linkedin_url"),
                title=(exp.get("title") or {}).get("name") if isinstance(exp.get("title"), dict) else exp.get("title"),
                title_role=(exp.get("title") or {}).get("role") if isinstance(exp.get("title"), dict) else None,
                title_levels=(exp.get("title") or {}).get("levels") if isinstance(exp.get("title"), dict) else None,
                start_date=exp.get("start_date"),
                end_date=exp.get("end_date"),
                is_primary=exp.get("is_primary"),
                location=", ".join(exp.get("location_names") or []) or None,
                summary=exp.get("summary"),
            )
            for exp in (raw.get("experience") or [])
        ],
        education=[
            PDLEducation(
                school_name=(edu.get("school") or {}).get("name"),
                school_type=(edu.get("school") or {}).get("type"),
                school_domain=(edu.get("school") or {}).get("domain"),
                degrees=edu.get("degrees"),
                majors=edu.get("majors"),
                start_date=edu.get("start_date"),
                end_date=edu.get("end_date"),
                gpa=edu.get("gpa"),
            )
            for edu in (raw.get("education") or [])
        ],

        # Skills
        skills=raw.get("skills"),
        interests=raw.get("interests"),
        languages=raw.get("languages"),
        certifications=raw.get("certifications"),
        name_aliases=raw.get("name_aliases"),
    )


# ══════════════════════════════════════════
# Person Search (SQL or Elasticsearch DSL)
# ══════════════════════════════════════════

async def search_person(
    sql: Optional[str] = None,
    query: Optional[dict] = None,
    size: int = 10,
    scroll_token: Optional[str] = None,
    dataset: str = "all",
) -> PDLSearchResponse:
    """
    Search PDL Person dataset.
    Use `sql` for SQL syntax or `query` for Elasticsearch DSL.
    """
    if not settings.pdl_api_key:
        return PDLSearchResponse(query=sql or str(query), error="PDL_API_KEY not configured")

    body = {"size": min(size, 100), "dataset": dataset}
    if sql:
        body["sql"] = sql
    elif query:
        body["query"] = query
    else:
        return PDLSearchResponse(error="Either 'sql' or 'query' parameter is required")

    if scroll_token:
        body["scroll_token"] = scroll_token

    label = sql or json.dumps(query)[:120]
    logger.info(f"[PDL] Search: {label} (size={size})")

    try:
        async with httpx.AsyncClient(timeout=PDL_TIMEOUT) as client:
            resp = await client.get(
                f"{PDL_BASE}/person/search",
                headers=_headers(),
                params={k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in body.items()},
            )

            if resp.status_code != 200:
                err = resp.text[:500]
                logger.warning(f"[PDL] Search failed: {resp.status_code} — {err}")
                return PDLSearchResponse(query=label, error=f"PDL {resp.status_code}: {err}")

            data = resp.json()
            personas = [_parse_person(p) for p in (data.get("data") or [])]
            total = data.get("total", len(personas))

            logger.info(f"[PDL] Search OK: {total} total, {len(personas)} returned")
            return PDLSearchResponse(
                query=label,
                total=total,
                personas=personas,
                scroll_token=data.get("scroll_token"),
                credits_used=len(personas),
            )

    except Exception as e:
        logger.error(f"[PDL] Search exception: {e}")
        return PDLSearchResponse(query=label, error=str(e))


# ══════════════════════════════════════════
# Convenience search builders (SQL shortcuts)
# ══════════════════════════════════════════

async def search_by_name(
    name: str,
    location_country: Optional[str] = None,
    size: int = 10,
) -> PDLSearchResponse:
    """Search by full name, optionally filtered by country."""
    conditions = [f"full_name='{_esc(name)}'"]
    if location_country:
        conditions.append(f"location_country='{_esc(location_country)}'")
    sql = f"SELECT * FROM person WHERE {' AND '.join(conditions)}"
    return await search_person(sql=sql, size=size)


async def search_by_email(email: str, size: int = 5) -> PDLSearchResponse:
    """Search by email address."""
    sql = f"SELECT * FROM person WHERE emails='{_esc(email)}'"
    return await search_person(sql=sql, size=size)


async def search_by_phone(phone: str, size: int = 5) -> PDLSearchResponse:
    """Search by phone number."""
    sql = f"SELECT * FROM person WHERE phone_numbers='{_esc(phone)}'"
    return await search_person(sql=sql, size=size)


async def search_by_linkedin(linkedin_url: str, size: int = 5) -> PDLSearchResponse:
    """Search by LinkedIn URL or username."""
    sql = f"SELECT * FROM person WHERE linkedin_url='{_esc(linkedin_url)}'"
    return await search_person(sql=sql, size=size)


async def search_by_company(
    company: str,
    job_title: Optional[str] = None,
    location_country: Optional[str] = None,
    size: int = 10,
) -> PDLSearchResponse:
    """Search people at a specific company, optionally filtered by title/country."""
    conditions = [f"job_company_name='{_esc(company)}'"]
    if job_title:
        conditions.append(f"job_title='{_esc(job_title)}'")
    if location_country:
        conditions.append(f"location_country='{_esc(location_country)}'")
    sql = f"SELECT * FROM person WHERE {' AND '.join(conditions)}"
    return await search_person(sql=sql, size=size)


async def search_by_location(
    country: str,
    region: Optional[str] = None,
    locality: Optional[str] = None,
    job_title: Optional[str] = None,
    size: int = 10,
) -> PDLSearchResponse:
    """Search people by location."""
    conditions = [f"location_country='{_esc(country)}'"]
    if region:
        conditions.append(f"location_region='{_esc(region)}'")
    if locality:
        conditions.append(f"location_locality='{_esc(locality)}'")
    if job_title:
        conditions.append(f"job_title='{_esc(job_title)}'")
    sql = f"SELECT * FROM person WHERE {' AND '.join(conditions)}"
    return await search_person(sql=sql, size=size)


# ══════════════════════════════════════════
# Person Enrichment (single record lookup)
# ══════════════════════════════════════════

async def enrich_person(
    email: Optional[str] = None,
    phone: Optional[str] = None,
    name: Optional[str] = None,
    profile: Optional[str] = None,
    lid: Optional[str] = None,
    company: Optional[str] = None,
    location_country: Optional[str] = None,
) -> PDLEnrichResponse:
    """
    Enrich a single person by one or more identifiers.
    At least one identifier is required.
    """
    if not settings.pdl_api_key:
        return PDLEnrichResponse(query="enrich", error="PDL_API_KEY not configured")

    params = {}
    if email:
        params["email"] = email
    if phone:
        params["phone"] = phone
    if name:
        params["name"] = name
    if profile:
        params["profile"] = profile
    if lid:
        params["lid"] = lid
    if company:
        params["company"] = company
    if location_country:
        params["location_country"] = location_country

    if not params:
        return PDLEnrichResponse(query="enrich", error="At least one identifier required (email, phone, name, profile, lid)")

    label = " | ".join(f"{k}={v}" for k, v in params.items())
    logger.info(f"[PDL] Enrich: {label}")

    try:
        async with httpx.AsyncClient(timeout=PDL_TIMEOUT) as client:
            resp = await client.get(
                f"{PDL_BASE}/person/enrich",
                headers=_headers(),
                params=params,
            )

            if resp.status_code == 404:
                logger.info(f"[PDL] Enrich: no match for {label}")
                return PDLEnrichResponse(query=label, error="No match found")

            if resp.status_code != 200:
                err = resp.text[:500]
                logger.warning(f"[PDL] Enrich failed: {resp.status_code} — {err}")
                return PDLEnrichResponse(query=label, error=f"PDL {resp.status_code}: {err}")

            data = resp.json()
            persona = _parse_person(data.get("data") or {})
            likelihood = data.get("likelihood")

            logger.info(f"[PDL] Enrich OK: {persona.full_name} (likelihood={likelihood})")
            return PDLEnrichResponse(
                query=label,
                likelihood=likelihood,
                persona=persona,
            )

    except Exception as e:
        logger.error(f"[PDL] Enrich exception: {e}")
        return PDLEnrichResponse(query=label, error=str(e))


def _esc(s: str) -> str:
    """Escape single quotes for PDL SQL queries."""
    return s.replace("'", "''") if s else ""
