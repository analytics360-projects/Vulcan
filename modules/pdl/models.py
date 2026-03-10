"""
PDL (People Data Labs) — Response Models
https://docs.peopledatalabs.com/docs/person-search-api
"""
from pydantic import BaseModel
from typing import List, Optional, Any


# ── Person Search ──

class PDLExperience(BaseModel):
    company_name: Optional[str] = None
    company_size: Optional[str] = None
    company_industry: Optional[str] = None
    company_website: Optional[str] = None
    company_linkedin_url: Optional[str] = None
    title: Optional[str] = None
    title_role: Optional[str] = None
    title_levels: Optional[List[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_primary: Optional[bool] = None
    location: Optional[str] = None
    summary: Optional[str] = None


class PDLEducation(BaseModel):
    school_name: Optional[str] = None
    school_type: Optional[str] = None
    school_domain: Optional[str] = None
    degrees: Optional[List[str]] = None
    majors: Optional[List[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    gpa: Optional[float] = None


class PDLProfile(BaseModel):
    network: Optional[str] = None
    url: Optional[str] = None
    username: Optional[str] = None
    id: Optional[str] = None


class PDLPhone(BaseModel):
    number: Optional[str] = None
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    num_sources: Optional[int] = None


class PDLEmail(BaseModel):
    address: Optional[str] = None
    type: Optional[str] = None
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    num_sources: Optional[int] = None


class PDLPersonResult(BaseModel):
    """A single person record from PDL."""
    id: Optional[str] = None
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    sex: Optional[str] = None
    birth_year: Optional[int] = None
    birth_date: Optional[str] = None

    # Contact
    emails: Optional[List[PDLEmail]] = None
    personal_emails: Optional[List[str]] = None
    work_email: Optional[str] = None
    recommended_personal_email: Optional[str] = None
    phones: Optional[List[PDLPhone]] = None
    phone_numbers: Optional[List[str]] = None
    mobile_phone: Optional[str] = None

    # Location
    location_name: Optional[str] = None
    location_locality: Optional[str] = None
    location_region: Optional[str] = None
    location_country: Optional[str] = None
    location_continent: Optional[str] = None
    location_geo: Optional[str] = None
    location_street_address: Optional[str] = None
    location_postal_code: Optional[str] = None
    countries: Optional[List[str]] = None

    # Current job
    job_title: Optional[str] = None
    job_title_role: Optional[str] = None
    job_title_levels: Optional[List[str]] = None
    job_company_name: Optional[str] = None
    job_company_website: Optional[str] = None
    job_company_industry: Optional[str] = None
    job_company_size: Optional[str] = None
    job_company_linkedin_url: Optional[str] = None
    job_start_date: Optional[str] = None
    inferred_salary: Optional[str] = None

    # Social
    linkedin_url: Optional[str] = None
    linkedin_username: Optional[str] = None
    facebook_url: Optional[str] = None
    facebook_username: Optional[str] = None
    twitter_url: Optional[str] = None
    twitter_username: Optional[str] = None
    github_url: Optional[str] = None
    github_username: Optional[str] = None
    profiles: Optional[List[PDLProfile]] = None

    # History
    experience: Optional[List[PDLExperience]] = None
    education: Optional[List[PDLEducation]] = None

    # Skills
    skills: Optional[List[str]] = None
    interests: Optional[List[str]] = None
    languages: Optional[List[Any]] = None
    certifications: Optional[List[Any]] = None
    name_aliases: Optional[List[str]] = None


class PDLSearchResponse(BaseModel):
    """Response from PDL Person Search API."""
    query: str = ""
    total: int = 0
    personas: List[PDLPersonResult] = []
    scroll_token: Optional[str] = None
    error: Optional[str] = None
    credits_used: int = 0


class PDLEnrichResponse(BaseModel):
    """Response from PDL Person Enrichment API."""
    query: str = ""
    likelihood: Optional[int] = None
    persona: Optional[PDLPersonResult] = None
    error: Optional[str] = None
