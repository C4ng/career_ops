from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.models import LinkedInKeywordSearchSource, LinkedInSourceConfig


POSTED_WINDOW_TO_SECONDS = {
    "past_24_hours": "r86400",
    "past_3_days": "r259200",
    "past_week": "r604800",
    "past_month": "r2592000",
}

EXPERIENCE_LEVEL_TO_CODE = {
    "internship": "1",
    "entry": "2",
    "associate": "3",
    "mid_senior": "4",
    "director": "5",
    "executive": "6",
}


def build_search_url(config: LinkedInKeywordSearchSource) -> str:
    params: dict[str, str] = {
        "keywords": config.keywords,
        "location": config.location,
        "start": str(config.start),
    }
    posted = POSTED_WINDOW_TO_SECONDS.get(config.posted_window)
    if posted:
        params["f_TPR"] = posted
    experience_codes = [
        EXPERIENCE_LEVEL_TO_CODE[level]
        for level in config.experience_levels
        if level in EXPERIENCE_LEVEL_TO_CODE
    ]
    if experience_codes:
        params["f_E"] = ",".join(experience_codes)
    return f"https://www.linkedin.com/jobs/search/?{urlencode(params)}"


def build_source_url(source_config: LinkedInSourceConfig, source_type: str, start: int = 0) -> str:
    if source_type == "keyword_search":
        assert source_config.keyword_search is not None
        search_input = source_config.keyword_search.model_copy(update={"start": start})
        return build_search_url(search_input)
    if source_type == "recommended_feed":
        assert source_config.recommended_feed is not None
        parts = urlsplit(source_config.recommended_feed.recommended_url)
        query_params = dict(parse_qsl(parts.query, keep_blank_values=True))
        query_params["start"] = str(start)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query_params), parts.fragment))
    raise ValueError(f"Unsupported LinkedIn source_type: {source_type}")


def source_page_step(source_config: LinkedInSourceConfig, source_type: str) -> int | None:
    if source_type == "keyword_search":
        return source_config.keyword_search_page_step
    if source_type == "recommended_feed":
        return source_config.recommended_feed_page_step
    raise ValueError(f"Unsupported LinkedIn source_type: {source_type}")
