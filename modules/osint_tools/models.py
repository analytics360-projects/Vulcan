"""OSINT tools enrichment models."""
from pydantic import BaseModel
from typing import Optional, Any


class ProfileExtraction(BaseModel):
    """Result from socid-extractor profile analysis."""
    url: str
    platform: str = ""
    fields: dict = {}
    error: Optional[str] = None


class InstagramEnrichment(BaseModel):
    """Extended Instagram data from Toutatis."""
    username: str
    user_id: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    biography: Optional[str] = None
    is_private: Optional[bool] = None
    is_verified: Optional[bool] = None
    follower_count: Optional[int] = None
    following_count: Optional[int] = None
    media_count: Optional[int] = None
    external_url: Optional[str] = None
    profile_pic_url: Optional[str] = None
    raw: Optional[dict] = None
    error: Optional[str] = None


class IpLookupResult(BaseModel):
    """IP geolocation and ASN data."""
    ip: str
    country: Optional[str] = None
    country_code: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    isp: Optional[str] = None
    org: Optional[str] = None
    asn: Optional[str] = None
    is_proxy: Optional[bool] = None
    is_vpn: Optional[bool] = None
    timezone: Optional[str] = None
    error: Optional[str] = None


class ExifResult(BaseModel):
    """EXIF metadata extracted from an image."""
    filename: str
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    software: Optional[str] = None
    datetime_original: Optional[str] = None
    datetime_digitized: Optional[str] = None
    orientation: Optional[str] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    all_tags: dict = {}
    error: Optional[str] = None


class GitHubRepo(BaseModel):
    """GitHub repository summary."""
    name: str
    full_name: str = ""
    description: Optional[str] = None
    language: Optional[str] = None
    stars: int = 0
    forks: int = 0
    url: str = ""
    is_fork: bool = False
    updated_at: Optional[str] = None


class GitHubOsintResult(BaseModel):
    """Deep GitHub intelligence — emails from commits/GPG, SSH keys, profile data."""
    username: str
    user_id: Optional[int] = None
    full_name: Optional[str] = None
    bio: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    blog: Optional[str] = None
    twitter: Optional[str] = None
    email_public: Optional[str] = None
    emails_from_commits: list[str] = []
    emails_from_gpg: list[str] = []
    all_emails: list[str] = []
    ssh_keys: list[str] = []
    gpg_keys: list[str] = []
    avatar_url: Optional[str] = None
    profile_url: Optional[str] = None
    followers: int = 0
    following: int = 0
    public_repos: int = 0
    public_gists: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    repos: list[GitHubRepo] = []
    error: Optional[str] = None


class TwitchResult(BaseModel):
    """Twitch profile data."""
    username: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    profile_image_url: Optional[str] = None
    view_count: Optional[int] = None
    created_at: Optional[str] = None
    broadcaster_type: Optional[str] = None
    is_live: bool = False
    stream_title: Optional[str] = None
    stream_game: Optional[str] = None
    error: Optional[str] = None


class OsintToolsResponse(BaseModel):
    """Combined response from multiple OSINT enrichment tools."""
    profile_extractions: list[ProfileExtraction] = []
    instagram_enrichment: Optional[InstagramEnrichment] = None
    github_osint: Optional[GitHubOsintResult] = None
    twitch: Optional[TwitchResult] = None
    ip_lookups: list[IpLookupResult] = []
    exif_results: list[ExifResult] = []
