"""OSINT enrichment tools router — socid-extractor, toutatis, IP lookup, EXIF, GitHub OSINT, Twitch."""
import json
from fastapi import APIRouter, Query, UploadFile, File
from typing import Optional

from config import logger
from modules.osint_tools.models import (
    ProfileExtraction,
    InstagramEnrichment,
    IpLookupResult,
    ExifResult,
    GitHubOsintResult,
    TwitchResult,
)
from modules.osint_tools.service import (
    extract_profile,
    extract_profiles_batch,
    enrich_instagram,
    lookup_ip,
    lookup_ips_batch,
    extract_exif,
    extract_exif_from_url,
    github_osint,
    twitch_lookup,
)

router = APIRouter(prefix="/osint-tools", tags=["OSINT Enrichment Tools"])


@router.get("/profile-extract", response_model=ProfileExtraction)
async def profile_extract_endpoint(
    url: str = Query(..., description="Profile URL to extract data from (GitHub, Twitter, etc.)"),
):
    """Extract structured profile data from a URL using socid-extractor (100+ sites)."""
    result = await extract_profile(url)
    logger.info(f"[OSINT-TOOLS] profile-extract: {url} → {len(result.fields)} fields")
    return result


@router.post("/profile-extract-batch", response_model=list[ProfileExtraction])
async def profile_extract_batch_endpoint(urls: list[str]):
    """Extract profile data from multiple URLs in parallel."""
    results = await extract_profiles_batch(urls)
    logger.info(f"[OSINT-TOOLS] profile-extract-batch: {len(urls)} URLs processed")
    return results


@router.get("/instagram-enrich", response_model=InstagramEnrichment)
async def instagram_enrich_endpoint(
    username: str = Query(..., description="Instagram username"),
    session_id: Optional[str] = Query(None, description="Instagram session ID (or set INSTAGRAM_SESSION_ID env var)"),
):
    """Get extended Instagram data (phone, email, ID) via Toutatis."""
    result = await enrich_instagram(username, session_id)
    return result


@router.get("/ip-lookup", response_model=IpLookupResult)
async def ip_lookup_endpoint(
    ip: str = Query(..., description="IP address to geolocate"),
):
    """Geolocate an IP address — country, city, ISP, ASN, proxy detection."""
    result = await lookup_ip(ip)
    return result


@router.post("/ip-lookup-batch", response_model=list[IpLookupResult])
async def ip_lookup_batch_endpoint(ips: list[str]):
    """Geolocate multiple IP addresses in parallel."""
    results = await lookup_ips_batch(ips)
    return results


@router.post("/exif-extract", response_model=ExifResult)
async def exif_extract_endpoint(file: UploadFile = File(...)):
    """Extract EXIF metadata (GPS, camera, dates) from an uploaded image."""
    content = await file.read()
    result = await extract_exif(file_bytes=content, filename=file.filename or "upload")
    return result


@router.get("/exif-from-url", response_model=ExifResult)
async def exif_from_url_endpoint(
    url: str = Query(..., description="Image URL to download and extract EXIF from"),
):
    """Download an image from URL and extract EXIF metadata."""
    result = await extract_exif_from_url(url)
    return result


@router.get("/github-osint", response_model=GitHubOsintResult)
async def github_osint_endpoint(
    username: str = Query(..., description="GitHub username to investigate"),
):
    """Deep GitHub OSINT — emails from commits/GPG keys, SSH keys, repos, profile data."""
    result = await github_osint(username)
    logger.info(f"[OSINT-TOOLS] github-osint: {username} → {len(result.all_emails)} emails, {len(result.repos)} repos")
    return result


@router.get("/twitch-lookup", response_model=TwitchResult)
async def twitch_lookup_endpoint(
    username: str = Query(..., description="Twitch username to look up"),
):
    """Look up a Twitch profile — display name, description, live status."""
    result = await twitch_lookup(username)
    logger.info(f"[OSINT-TOOLS] twitch-lookup: {username} → {'LIVE' if result.is_live else 'offline'}")
    return result
