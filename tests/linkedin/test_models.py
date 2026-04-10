from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import (
    LinkedInKeywordSearchSource,
    LinkedInRecommendedFeedSource,
    LinkedInSourceConfig,
)


def test_linkedin_source_config_dedupes_source_type_order() -> None:
    config = LinkedInSourceConfig(
        source_type=["keyword_search", "recommended_feed", "keyword_search"],
        keyword_search=LinkedInKeywordSearchSource(
            keywords="AI Engineer",
            location="Toronto",
        ),
        recommended_feed=LinkedInRecommendedFeedSource(
            recommended_url="https://www.linkedin.com/jobs/collections/recommended/?currentJobId=123"
        ),
    )

    assert config.source_type == ["keyword_search", "recommended_feed"]


def test_linkedin_source_config_requires_keyword_search_block_when_selected() -> None:
    with pytest.raises(ValidationError):
        LinkedInSourceConfig(
            source_type=["keyword_search"],
        )


def test_linkedin_source_config_requires_recommended_feed_block_when_selected() -> None:
    with pytest.raises(ValidationError):
        LinkedInSourceConfig(
            source_type=["recommended_feed"],
        )
