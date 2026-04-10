from app.sources.linkedin.scraper.extract import (
    _extract_job_description_from_body_text,
    extract_applicant_count_text_from_body_text,
    extract_apply_link,
    extract_application_status_text_from_body_text,
    extract_detail_fields,
    extract_employment_type_from_body_text,
    extract_observed_posted_text_from_body_text,
    extract_work_mode_from_body_text,
)


def test_extract_job_description_from_body_text_uses_about_the_job_section() -> None:
    body_text = (
        "Home Jobs Example AI Researcher Toronto, ON About the job "
        "This role is part of the applied AI team. You will build and evaluate models, "
        "work with inference systems, and partner with product engineers to deploy results. "
        "The work includes experimentation, model iteration, and productionization. "
        "Seniority level Mid-Senior level Employment type Full-time"
    )

    description = _extract_job_description_from_body_text(body_text)

    assert description == (
        "This role is part of the applied AI team. You will build and evaluate models, "
        "work with inference systems, and partner with product engineers to deploy results. "
        "The work includes experimentation, model iteration, and productionization."
    )


BODY_TEXT = """
Liferaft
Junior Data Scientist
Canada · 4 days ago · Over 100 applicants
No response insights available yet
Remote
Temporary
Easy Apply
Save
Use AI to assess how you fit
About the job
This is the detailed job description.
Set alert for similar jobs
"""


def test_extract_top_card_detail_fields_from_body_text() -> None:
    assert extract_observed_posted_text_from_body_text(BODY_TEXT) == "4 days ago"
    assert extract_applicant_count_text_from_body_text(BODY_TEXT) == "Over 100 applicants"
    assert extract_work_mode_from_body_text(BODY_TEXT) == "remote"
    assert extract_employment_type_from_body_text(BODY_TEXT) == "Temporary"
    assert extract_application_status_text_from_body_text(BODY_TEXT) is None


def test_extract_detail_fields_from_page_like_body_text() -> None:
    class FakeBodyLocator:
        def count(self) -> int:
            return 1

        def inner_text(self) -> str:
            return BODY_TEXT

    class FakeEmptyLocator:
        def count(self) -> int:
            return 0

        def nth(self, index: int):
            raise AssertionError(f"unexpected locator access: {index}")

    class FakePage:
        def locator(self, selector: str):
            if selector == "body":
                return FakeBodyLocator()
            return FakeEmptyLocator()

    fields = extract_detail_fields(FakePage())

    assert fields["job_description"] == "This is the detailed job description."
    assert fields["observed_posted_text"] == "4 days ago"
    assert fields["applicant_count_text"] == "Over 100 applicants"
    assert fields["work_mode"] == "remote"
    assert fields["employment_type"] == "Temporary"
    assert fields["application_status_text"] is None
    assert fields["easy_apply"] is True


def test_extract_apply_link_prefers_external_target_over_linkedin_similar_jobs() -> None:
    class FakeAnchor:
        def __init__(self, href: str, text: str = "", aria_label: str | None = None) -> None:
            self._href = href
            self._text = text
            self._aria_label = aria_label

        def get_attribute(self, name: str) -> str | None:
            if name == "href":
                return self._href
            if name == "aria-label":
                return self._aria_label
            return None

        def inner_text(self) -> str:
            return self._text

    class FakeAnchorList:
        def __init__(self, anchors: list[FakeAnchor]) -> None:
            self._anchors = anchors

        def count(self) -> int:
            return len(self._anchors)

        def nth(self, index: int) -> FakeAnchor:
            return self._anchors[index]

    class FakePage:
        def locator(self, selector: str):
            assert selector == "a"
            return FakeAnchorList(
                [
                    FakeAnchor(
                        "https://www.linkedin.com/jobs/collections/similar-jobs/?referenceJobId=1",
                        text="Apply",
                    ),
                    FakeAnchor(
                        "https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fcompany.example%2Fapply",
                        text="Apply",
                    ),
                ]
            )

    assert extract_apply_link(FakePage()) == "https://company.example/apply"


def test_extract_apply_link_keeps_linkedin_easy_apply_url() -> None:
    class FakeAnchor:
        def get_attribute(self, name: str) -> str | None:
            if name == "href":
                return "https://www.linkedin.com/jobs/view/123/apply/?openSDUIApplyFlow=true"
            if name == "aria-label":
                return "Easy Apply"
            return None

        def inner_text(self) -> str:
            return "Easy Apply"

    class FakeAnchorList:
        def count(self) -> int:
            return 1

        def nth(self, index: int) -> FakeAnchor:
            assert index == 0
            return FakeAnchor()

    class FakePage:
        def locator(self, selector: str):
            assert selector == "a"
            return FakeAnchorList()

    assert (
        extract_apply_link(FakePage())
        == "https://www.linkedin.com/jobs/view/123/apply/?openSDUIApplyFlow=true"
    )
