"""Abstract base classes defining contracts for pluggable components."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class JobSource(ABC):
    """Interface for a job collection source (LinkedIn, Indeed, etc.)."""

    @abstractmethod
    def collect(self, **kwargs: Any) -> list[dict[str, object]]:
        """Discover and return raw job cards from this source."""

    @abstractmethod
    def fetch_details(self, job_ids: list[str], **kwargs: Any) -> list[dict[str, object]]:
        """Fetch full job details for the given job IDs."""


class ApplicationAgent(ABC):
    """Interface for an autonomous application agent."""

    @abstractmethod
    async def apply(self, job: dict[str, object], **kwargs: Any) -> dict[str, object]:
        """Attempt to apply to a single job. Returns an audit record."""


class DocumentAgent(ABC):
    """Interface for document generation agents (resume tailoring, cover letters)."""

    @abstractmethod
    def generate(self, job: dict[str, object], candidate: Any, **kwargs: Any) -> str:
        """Generate a tailored document for the given job and candidate."""
