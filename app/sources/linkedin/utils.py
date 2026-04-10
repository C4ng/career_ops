from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urljoin, urlparse

LINKEDIN_BASE_URL = "https://www.linkedin.com"


def clean_text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def extract_job_id_from_href(href: str | None) -> str | None:
    if not href:
        return None
    match = re.search(r"/jobs/view/(\d+)", href)
    if match:
        return match.group(1)
    match = re.search(r"currentJobId=(\d+)", href)
    if match:
        return match.group(1)
    return None


def absolute_link(href: str | None) -> str | None:
    if not href:
        return None
    return urljoin(LINKEDIN_BASE_URL, href)


def canonical_linkedin_job_url(href: str | None) -> str | None:
    job_id = extract_job_id_from_href(href)
    if job_id:
        return f"{LINKEDIN_BASE_URL}/jobs/view/{job_id}/"
    return absolute_link(href)


def normalize_linkedin_apply_link(href: str | None) -> str | None:
    absolute_href = absolute_link(href)
    if not absolute_href:
        return None
    parsed = urlparse(absolute_href)
    if parsed.netloc == "www.linkedin.com" and parsed.path == "/safety/go/":
        raw_target = parse_qs(parsed.query).get("url", [None])[0]
        if raw_target:
            return unquote(raw_target)
    return absolute_href


def extract_work_mode(location_text: str | None) -> str | None:
    if not location_text:
        return None
    lowered = location_text.lower()
    if "(remote)" in lowered or " remote" in lowered:
        return "remote"
    if "(hybrid)" in lowered or " hybrid" in lowered:
        return "hybrid"
    if "(on-site)" in lowered or "(onsite)" in lowered or " on-site" in lowered or " onsite" in lowered:
        return "on_site"
    return None


def extract_easy_apply(badge_texts: list[str]) -> bool:
    return any("easy apply" in badge.lower() for badge in badge_texts)


def title_matches_exclusion(title: str | None, excluded_terms: list[str]) -> str | None:
    if not title or not excluded_terms:
        return None
    lowered_title = title.lower()
    for term in excluded_terms:
        normalized_term = clean_text(term)
        if not normalized_term:
            continue
        lowered_term = normalized_term.lower()
        if lowered_term == "staff" and "technical staff" in lowered_title:
            continue
        if lowered_term in lowered_title:
            return normalized_term
    return None
