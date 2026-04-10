"""Centralized models package — re-exports all domain models."""
from __future__ import annotations

from app.models.application import (
    LinkedInApplicationAnswerProposal,
    LinkedInApplicationElementConstraints,
    LinkedInApplicationFormAction,
    LinkedInApplicationFormElement,
    LinkedInApplicationFormStep,
    LinkedInApplicationQuestion,
    LinkedInApplicationRecordList,
)
from app.models.candidate import (
    LinkedInCandidateApplicationPreferences,
    LinkedInCandidateContact,
    LinkedInCandidateCoverLetterProfile,
    LinkedInCandidateDocuments,
    LinkedInCandidateDossier,
    LinkedInCandidateEducation,
    LinkedInCandidateExperience,
    LinkedInCandidateExperienceEntry,
    LinkedInCandidateLinks,
    LinkedInCandidateWorkAuthorization,
)
from app.models.email import (
    LinkedInApplicationConfirmation,
    LinkedInRawEmailMessage,
)
from app.models.job import (
    LinkedInJobCard,
    LinkedInJobRequirements,
    LinkedInRawCard,
)
from app.models.linkedin_config import (
    DEFAULT_CDP_URL,
    LinkedInConnectionConfig,
    LinkedInEmailConfig,
    LinkedInKeywordSearchSource,
    LinkedInRankingCandidateProfile,
    LinkedInRankingConfig,
    LinkedInRankingPreferenceBucket,
    LinkedInRankingPreferences,
    LinkedInRankingSeniorityPreference,
    LinkedInRankingTargetConfig,
    LinkedInRecommendedFeedSource,
    LinkedInSourceConfig,
    LinkedInTitleTriageConfig,
    LinkedInTitleTriageExamples,
    LinkedInTitleTriageRoleIntent,
)
from app.models.linkedin_result import (
    LinkedInApplicationConfirmationFetchResult,
    LinkedInCollectionResult,
    LinkedInConnectionResult,
    LinkedInEmailConnectionResult,
    LinkedInEmailFetchResult,
    LinkedInEmailResultBase,
)
from app.models.screening import (
    LinkedInJobRankingResult,
    LinkedInRankingLabeledReason,
    LinkedInTitleTriageCandidate,
    LinkedInTitleTriageDecision,
)

__all__ = [
    # application
    "LinkedInApplicationAnswerProposal",
    "LinkedInApplicationElementConstraints",
    "LinkedInApplicationFormAction",
    "LinkedInApplicationFormElement",
    "LinkedInApplicationFormStep",
    "LinkedInApplicationQuestion",
    "LinkedInApplicationRecordList",
    # candidate
    "LinkedInCandidateApplicationPreferences",
    "LinkedInCandidateContact",
    "LinkedInCandidateCoverLetterProfile",
    "LinkedInCandidateDocuments",
    "LinkedInCandidateDossier",
    "LinkedInCandidateEducation",
    "LinkedInCandidateExperience",
    "LinkedInCandidateExperienceEntry",
    "LinkedInCandidateLinks",
    "LinkedInCandidateWorkAuthorization",
    # email
    "LinkedInApplicationConfirmation",
    "LinkedInRawEmailMessage",
    # job
    "LinkedInJobCard",
    "LinkedInJobRequirements",
    "LinkedInRawCard",
    # linkedin configs
    "DEFAULT_CDP_URL",
    "LinkedInConnectionConfig",
    "LinkedInEmailConfig",
    "LinkedInKeywordSearchSource",
    "LinkedInRankingCandidateProfile",
    "LinkedInRankingConfig",
    "LinkedInRankingPreferenceBucket",
    "LinkedInRankingPreferences",
    "LinkedInRankingSeniorityPreference",
    "LinkedInRankingTargetConfig",
    "LinkedInRecommendedFeedSource",
    "LinkedInSourceConfig",
    "LinkedInTitleTriageConfig",
    "LinkedInTitleTriageExamples",
    "LinkedInTitleTriageRoleIntent",
    # linkedin results
    "LinkedInApplicationConfirmationFetchResult",
    "LinkedInCollectionResult",
    "LinkedInConnectionResult",
    "LinkedInEmailConnectionResult",
    "LinkedInEmailFetchResult",
    "LinkedInEmailResultBase",
    # screening
    "LinkedInJobRankingResult",
    "LinkedInRankingLabeledReason",
    "LinkedInTitleTriageCandidate",
    "LinkedInTitleTriageDecision",
]
