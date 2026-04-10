from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator


class LLMServiceConfig(BaseModel):
    provider: Literal["gemini", "openai"] = "gemini"
    api_base: str | None = None
    api_key_env: str | None = None
    model: str
    temperature: float = 0.0
    batch_size: int = 20
    prompt_version: str = "v1"
    timeout_seconds: float = 60.0

    @model_validator(mode="after")
    def apply_provider_defaults(self) -> "LLMServiceConfig":
        if self.provider == "gemini":
            if self.api_base is None:
                self.api_base = "https://generativelanguage.googleapis.com/v1beta/openai"
            if self.api_key_env is None:
                self.api_key_env = "GEMINI_API_KEY"
        elif self.provider == "openai":
            if self.api_base is None:
                self.api_base = "https://api.openai.com/v1"
            if self.api_key_env is None:
                self.api_key_env = "OPENAI_API_KEY"
        return self


class TitleTriageLLMConfig(LLMServiceConfig):
    pass


class JDEnrichmentLLMConfig(LLMServiceConfig):
    max_batches_per_run: int = 1


class RankingLLMConfig(LLMServiceConfig):
    max_batches_per_run: int = 1


class ApplicationQuestionMappingLLMConfig(LLMServiceConfig):
    pass
