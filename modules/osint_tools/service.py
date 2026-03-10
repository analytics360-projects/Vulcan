"""OSINT tools enrichment service.

Integrates: socid-extractor, toutatis, IP geolocation, EXIF extraction,
GitHub deep OSINT (osgint-style), Twitch lookup.
"""
import asyncio
import base64
import io
import re
import time

import httpx

from config import logger
from modules.osint_tools.models import (
    ProfileExtraction,
    InstagramEnrichment,
    IpLookupResult,
    ExifResult,
    GitHubOsintResult,
    GitHubRepo,
    TwitchResult,
)


# ═══════════════════════════════════════════
# 1. socid-extractor — Profile data extraction
# ═══════════════════════════════════════════

async def extract_profile(url: str) -> ProfileExtraction:
    """Fetch a profile URL and extract structured data using socid-extractor."""
    logger.info(f"[SOCID] Extracting profile data from: {url}")
    t0 = time.perf_counter()
    try:
        from socid_extractor import extract

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            html = resp.text

        fields = extract(html)
        if not fields:
            fields = {}

        # Guess platform from URL
        platform = ""
        for p in ["github", "twitter", "instagram", "facebook", "linkedin", "tiktok",
                   "youtube", "reddit", "steam", "deviantart", "patreon", "medium"]:
            if p in url.lower():
                platform = p
                break

        logger.info(f"[SOCID] Extracted {len(fields)} fields from {url} ({(time.perf_counter()-t0)*1000:.0f}ms)")
        return ProfileExtraction(url=url, platform=platform, fields=fields)
    except Exception as e:
        logger.warning(f"[SOCID] FAILED {url}: {e} ({(time.perf_counter()-t0)*1000:.0f}ms)")
        return ProfileExtraction(url=url, error=str(e))


async def extract_profiles_batch(urls: list[str]) -> list[ProfileExtraction]:
    """Extract profile data from multiple URLs in parallel."""
    tasks = [extract_profile(url) for url in urls]
    return await asyncio.gather(*tasks)


# ═══════════════════════════════════════════
# 2. Toutatis — Instagram enrichment
# ═══════════════════════════════════════════

async def enrich_instagram(username: str, session_id: str = None) -> InstagramEnrichment:
    """Get extended Instagram user data (phone, email, ID) via Toutatis."""
    logger.info(f"[TOUTATIS] Enriching Instagram user: {username}")
    t0 = time.perf_counter()
    try:
        from toutatis import api as toutatis_api

        if not session_id:
            from config import settings
            session_id = getattr(settings, "instagram_session_id", None)

        if not session_id:
            return InstagramEnrichment(
                username=username,
                error="No Instagram session_id configured (set INSTAGRAM_SESSION_ID env var)"
            )

        # Toutatis uses requests internally, run in executor to not block
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(
            None,
            lambda: toutatis_api.get_user_info(username, session_id)
        )

        if not info or isinstance(info, str):
            logger.warning(f"[TOUTATIS] No data for {username}: {info}")
            return InstagramEnrichment(username=username, error=str(info) if info else "No data returned")

        result = InstagramEnrichment(
            username=username,
            user_id=str(info.get("id", "")),
            full_name=info.get("full_name"),
            phone=info.get("contact_phone_number") or info.get("public_phone_number"),
            email=info.get("public_email") or info.get("contact_email"),
            biography=info.get("biography"),
            is_private=info.get("is_private"),
            is_verified=info.get("is_verified"),
            follower_count=info.get("follower_count"),
            following_count=info.get("following_count"),
            media_count=info.get("media_count"),
            external_url=info.get("external_url"),
            profile_pic_url=info.get("profile_pic_url_hd") or info.get("profile_pic_url"),
            raw=info,
        )
        logger.info(
            f"[TOUTATIS] OK {username}: name={result.full_name} "
            f"phone={'YES' if result.phone else 'no'} email={'YES' if result.email else 'no'} "
            f"({(time.perf_counter()-t0)*1000:.0f}ms)"
        )
        return result
    except ImportError:
        logger.warning("[TOUTATIS] toutatis package not installed")
        return InstagramEnrichment(username=username, error="toutatis not installed")
    except Exception as e:
        logger.warning(f"[TOUTATIS] FAILED {username}: {e} ({(time.perf_counter()-t0)*1000:.0f}ms)")
        return InstagramEnrichment(username=username, error=str(e))


# ═══════════════════════════════════════════
# 3. IP Geolocation / ASN lookup
# ═══════════════════════════════════════════

async def lookup_ip(ip: str) -> IpLookupResult:
    """Geolocate an IP address using ip-api.com (free, no key needed)."""
    logger.info(f"[IP-LOOKUP] Looking up: {ip}")
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"http://ip-api.com/json/{ip}",
                params={"fields": "status,message,country,countryCode,region,regionName,city,lat,lon,timezone,isp,org,as,proxy,hosting,query"},
            )
            data = resp.json()

        if data.get("status") == "fail":
            return IpLookupResult(ip=ip, error=data.get("message", "lookup failed"))

        result = IpLookupResult(
            ip=data.get("query", ip),
            country=data.get("country"),
            country_code=data.get("countryCode"),
            region=data.get("regionName"),
            city=data.get("city"),
            lat=data.get("lat"),
            lon=data.get("lon"),
            isp=data.get("isp"),
            org=data.get("org"),
            asn=data.get("as"),
            is_proxy=data.get("proxy"),
            is_vpn=data.get("hosting"),
            timezone=data.get("timezone"),
        )
        logger.info(f"[IP-LOOKUP] OK {ip}: {result.city}, {result.country} ({result.isp}) ({(time.perf_counter()-t0)*1000:.0f}ms)")
        return result
    except Exception as e:
        logger.warning(f"[IP-LOOKUP] FAILED {ip}: {e}")
        return IpLookupResult(ip=ip, error=str(e))


async def lookup_ips_batch(ips: list[str]) -> list[IpLookupResult]:
    """Look up multiple IPs in parallel."""
    tasks = [lookup_ip(ip) for ip in ips]
    return await asyncio.gather(*tasks)


# ═══════════════════════════════════════════
# 4. EXIF extraction from images
# ═══════════════════════════════════════════

def _dms_to_decimal(dms_values, ref: str) -> float | None:
    """Convert GPS DMS (degrees, minutes, seconds) to decimal."""
    try:
        d = float(dms_values[0].num) / float(dms_values[0].den)
        m = float(dms_values[1].num) / float(dms_values[1].den)
        s = float(dms_values[2].num) / float(dms_values[2].den)
        decimal = d + m / 60.0 + s / 3600.0
        if ref in ("S", "W"):
            decimal = -decimal
        return round(decimal, 6)
    except Exception:
        return None


async def extract_exif(file_path: str = None, file_bytes: bytes = None, filename: str = "unknown") -> ExifResult:
    """Extract EXIF metadata from an image file or bytes."""
    logger.info(f"[EXIF] Extracting metadata from: {filename}")
    t0 = time.perf_counter()
    try:
        import exifread

        if file_bytes:
            f = io.BytesIO(file_bytes)
        elif file_path:
            f = open(file_path, "rb")
        else:
            return ExifResult(filename=filename, error="No file provided")

        tags = exifread.process_file(f, details=False)
        if hasattr(f, "close"):
            f.close()

        all_tags = {str(k): str(v) for k, v in tags.items()}

        # Parse GPS
        gps_lat = None
        gps_lon = None
        if "GPS GPSLatitude" in tags and "GPS GPSLatitudeRef" in tags:
            gps_lat = _dms_to_decimal(tags["GPS GPSLatitude"].values, str(tags["GPS GPSLatitudeRef"]))
        if "GPS GPSLongitude" in tags and "GPS GPSLongitudeRef" in tags:
            gps_lon = _dms_to_decimal(tags["GPS GPSLongitude"].values, str(tags["GPS GPSLongitudeRef"]))

        result = ExifResult(
            filename=filename,
            gps_lat=gps_lat,
            gps_lon=gps_lon,
            camera_make=str(tags.get("Image Make", "")) or None,
            camera_model=str(tags.get("Image Model", "")) or None,
            software=str(tags.get("Image Software", "")) or None,
            datetime_original=str(tags.get("EXIF DateTimeOriginal", "")) or None,
            datetime_digitized=str(tags.get("EXIF DateTimeDigitized", "")) or None,
            orientation=str(tags.get("Image Orientation", "")) or None,
            image_width=int(str(tags["EXIF ExifImageWidth"])) if "EXIF ExifImageWidth" in tags else None,
            image_height=int(str(tags["EXIF ExifImageLength"])) if "EXIF ExifImageLength" in tags else None,
            all_tags=all_tags,
        )
        gps_str = f"GPS=({gps_lat},{gps_lon})" if gps_lat else "no GPS"
        logger.info(f"[EXIF] OK {filename}: {len(all_tags)} tags, {gps_str} ({(time.perf_counter()-t0)*1000:.0f}ms)")
        return result
    except ImportError:
        return ExifResult(filename=filename, error="exifread not installed")
    except Exception as e:
        logger.warning(f"[EXIF] FAILED {filename}: {e}")
        return ExifResult(filename=filename, error=str(e))


async def extract_exif_from_url(image_url: str) -> ExifResult:
    """Download an image and extract EXIF data."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(image_url)
            resp.raise_for_status()
        filename = image_url.split("/")[-1].split("?")[0] or "remote_image"
        return await extract_exif(file_bytes=resp.content, filename=filename)
    except Exception as e:
        return ExifResult(filename=image_url, error=str(e))


# ═══════════════════════════════════════════
# 5. GitHub Deep OSINT (osgint-style)
# ═══════════════════════════════════════════

_GH_HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "Vulcan-OSINT/1.0",
}


async def _gh_get(client: httpx.AsyncClient, url: str) -> dict | list | None:
    """GitHub API GET with error handling."""
    try:
        resp = await client.get(url, headers=_GH_HEADERS)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


async def _gh_find_emails_from_commits(client: httpx.AsyncClient, username: str, repos: list[dict]) -> list[str]:
    """Extract emails from commit patches (like osgint does)."""
    emails = set()
    # Check up to 5 most recently pushed non-fork repos
    candidate_repos = [r for r in repos if not r.get("fork")][:5]
    for repo in candidate_repos:
        repo_name = repo.get("full_name", "")
        try:
            # Get recent commits by this user
            commits_url = f"https://api.github.com/repos/{repo_name}/commits?author={username}&per_page=3"
            commits = await _gh_get(client, commits_url)
            if not commits or not isinstance(commits, list):
                continue
            for commit in commits[:2]:
                sha = commit.get("sha", "")
                if not sha:
                    continue
                # Fetch the .patch to extract committer email from headers
                patch_resp = await client.get(
                    f"https://github.com/{repo_name}/commit/{sha}.patch",
                    headers={"User-Agent": "Vulcan-OSINT/1.0"},
                    follow_redirects=True,
                )
                if patch_resp.status_code == 200:
                    patch_text = patch_resp.text[:2000]
                    # Extract "From: Name <email>" from patch header
                    for match in re.findall(r"From:.*?<([^>]+@[^>]+)>", patch_text):
                        if "noreply" not in match.lower():
                            emails.add(match.lower())
                    # Also check "Author:" line
                    for match in re.findall(r"Author:.*?<([^>]+@[^>]+)>", patch_text):
                        if "noreply" not in match.lower():
                            emails.add(match.lower())
        except Exception as e:
            logger.debug(f"[GITHUB-OSINT] commit email extraction error for {repo_name}: {e}")
    return list(emails)


async def _gh_find_emails_from_gpg(client: httpx.AsyncClient, username: str) -> tuple[list[str], list[str]]:
    """Extract emails from GPG public keys and return (emails, gpg_key_ids)."""
    emails = set()
    gpg_ids = []
    try:
        resp = await client.get(
            f"https://api.github.com/users/{username}/gpg_keys",
            headers=_GH_HEADERS,
        )
        if resp.status_code == 200:
            keys = resp.json()
            for key in keys:
                gpg_ids.append(key.get("key_id", ""))
                # Extract emails from GPG key packets
                raw_key = key.get("raw_key", "")
                if raw_key:
                    # Emails are often in the UID packet — try base64 decode
                    for line in raw_key.split("\n"):
                        line = line.strip()
                        if line and not line.startswith("-----"):
                            try:
                                decoded = base64.b64decode(line + "==", validate=False).decode("utf-8", errors="ignore")
                                for match in re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", decoded):
                                    if "noreply" not in match.lower():
                                        emails.add(match.lower())
                            except Exception:
                                pass
                # Also check emails array in the key object
                for email_obj in key.get("emails", []):
                    email_addr = email_obj.get("email", "")
                    if email_addr and "noreply" not in email_addr.lower():
                        emails.add(email_addr.lower())
    except Exception as e:
        logger.debug(f"[GITHUB-OSINT] GPG email extraction error: {e}")
    return list(emails), gpg_ids


async def _gh_get_ssh_keys(client: httpx.AsyncClient, username: str) -> list[str]:
    """Fetch SSH public keys."""
    try:
        resp = await client.get(f"https://github.com/{username}.keys", headers={"User-Agent": "Vulcan-OSINT/1.0"})
        if resp.status_code == 200 and resp.text.strip():
            return [k.strip() for k in resp.text.strip().split("\n") if k.strip()]
    except Exception:
        pass
    return []


async def github_osint(username: str) -> GitHubOsintResult:
    """Full GitHub OSINT — profile, repos, emails from commits/GPG, SSH keys."""
    logger.info(f"[GITHUB-OSINT] Starting deep scan for: {username}")
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            # 1. Profile info
            user_data = await _gh_get(client, f"https://api.github.com/users/{username}")
            if not user_data:
                return GitHubOsintResult(username=username, error="User not found or API rate limited")

            # 2. Repos (sorted by push date)
            repos_data = await _gh_get(client, f"https://api.github.com/users/{username}/repos?per_page=100&sort=pushed") or []

            # 3. Parallel: emails from commits, GPG emails, SSH keys
            commit_emails_task = _gh_find_emails_from_commits(client, username, repos_data)
            gpg_task = _gh_find_emails_from_gpg(client, username)
            ssh_task = _gh_get_ssh_keys(client, username)

            commit_emails, (gpg_emails, gpg_ids), ssh_keys = await asyncio.gather(
                commit_emails_task, gpg_task, ssh_task
            )

            # Merge all emails
            all_emails = set()
            public_email = user_data.get("email")
            if public_email:
                all_emails.add(public_email.lower())
            all_emails.update(commit_emails)
            all_emails.update(gpg_emails)

            # Build repos list
            repos = []
            for r in repos_data[:30]:
                repos.append(GitHubRepo(
                    name=r.get("name", ""),
                    full_name=r.get("full_name", ""),
                    description=r.get("description"),
                    language=r.get("language"),
                    stars=r.get("stargazers_count", 0),
                    forks=r.get("forks_count", 0),
                    url=r.get("html_url", ""),
                    is_fork=r.get("fork", False),
                    updated_at=r.get("pushed_at"),
                ))

            result = GitHubOsintResult(
                username=username,
                user_id=user_data.get("id"),
                full_name=user_data.get("name"),
                bio=user_data.get("bio"),
                company=user_data.get("company"),
                location=user_data.get("location"),
                blog=user_data.get("blog"),
                twitter=user_data.get("twitter_username"),
                email_public=public_email,
                emails_from_commits=commit_emails,
                emails_from_gpg=gpg_emails,
                all_emails=sorted(all_emails),
                ssh_keys=ssh_keys,
                gpg_keys=gpg_ids,
                avatar_url=user_data.get("avatar_url"),
                profile_url=user_data.get("html_url"),
                followers=user_data.get("followers", 0),
                following=user_data.get("following", 0),
                public_repos=user_data.get("public_repos", 0),
                public_gists=user_data.get("public_gists", 0),
                created_at=user_data.get("created_at"),
                updated_at=user_data.get("updated_at"),
                repos=repos,
            )
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info(
                f"[GITHUB-OSINT] OK {username}: {len(all_emails)} emails, "
                f"{len(ssh_keys)} SSH keys, {len(repos)} repos ({elapsed:.0f}ms)"
            )
            return result
    except Exception as e:
        logger.warning(f"[GITHUB-OSINT] FAILED {username}: {e} ({(time.perf_counter()-t0)*1000:.0f}ms)")
        return GitHubOsintResult(username=username, error=str(e))


# ═══════════════════════════════════════════
# 6. Twitch Lookup
# ═══════════════════════════════════════════

async def twitch_lookup(username: str) -> TwitchResult:
    """Lookup a Twitch profile using the public GraphQL API (no key needed)."""
    logger.info(f"[TWITCH] Looking up: {username}")
    t0 = time.perf_counter()
    try:
        # Twitch's public GQL endpoint — same one the website uses
        gql_query = [{
            "operationName": "ChannelShell",
            "variables": {"login": username.lower()},
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "580ab410bcd0c1ad194224957ae2c5a5f05b27db4f7a1e2d3d7e8da41b1395d1",
                }
            },
        }]

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://gql.twitch.tv/gql",
                json=gql_query,
                headers={
                    "Client-ID": "kimne78kx3ncx6brgo4mv6wki5h1ko",  # Twitch's public web client ID
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                },
            )
            data = resp.json()

        if not data or not isinstance(data, list):
            return TwitchResult(username=username, error="Invalid response from Twitch GQL")

        user_data = None
        for item in data:
            user_obj = item.get("data", {}).get("userOrError", {})
            if user_obj and "userDoesNotExist" not in str(user_obj.get("reason", "")):
                user_data = user_obj
                break

        if not user_data or user_data.get("reason"):
            return TwitchResult(username=username, error="User not found")

        # Check stream status
        stream = user_data.get("stream")
        is_live = stream is not None and stream != {}

        result = TwitchResult(
            username=username,
            display_name=user_data.get("displayName"),
            description=user_data.get("description"),
            profile_image_url=user_data.get("profileImageURL"),
            created_at=user_data.get("createdAt"),
            broadcaster_type=user_data.get("broadcasterType"),
            is_live=is_live,
            stream_title=stream.get("title") if isinstance(stream, dict) else None,
            stream_game=stream.get("game", {}).get("name") if isinstance(stream, dict) and stream.get("game") else None,
        )
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(f"[TWITCH] OK {username}: name={result.display_name} live={is_live} ({elapsed:.0f}ms)")
        return result
    except Exception as e:
        logger.warning(f"[TWITCH] FAILED {username}: {e} ({(time.perf_counter()-t0)*1000:.0f}ms)")
        return TwitchResult(username=username, error=str(e))
