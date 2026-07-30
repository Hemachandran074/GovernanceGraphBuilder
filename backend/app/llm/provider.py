"""LLM provider interface, structured output schema, and selection factory."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# --- Structured output schema ------------------------------------------------

class ExtractedPolicy(BaseModel):
    """A single policy extracted from a natural-language document."""

    id: str | None = Field(default=None, description="Policy id if stated in the document.")
    name: str
    type: str | None = None  # access | data | usage | ...
    description: str | None = None
    rules: list[str] = Field(default_factory=list)
    governs: list[str] = Field(default_factory=list, description="Agent names this policy governs.")
    applies_to: list[str] = Field(
        default_factory=list, description="Tool / data source / model names this policy applies to."
    )


class PolicyExtraction(BaseModel):
    policies: list[ExtractedPolicy] = Field(default_factory=list)


# --- Provider interface ------------------------------------------------------

class LLMProvider(ABC):
    """Extracts structured policies from a natural-language policy document.

    Implementations receive the document text plus the known graph vocabulary
    (agent names and entity names) so extracted references can be grounded to
    real nodes.
    """

    name: str = "base"

    @abstractmethod
    def is_available(self) -> bool:
        """Whether this provider can run (SDK importable, credentials present)."""

    @abstractmethod
    def extract_policies(
        self,
        document_text: str,
        *,
        known_agents: list[str] | None = None,
        known_entities: list[str] | None = None,
    ) -> PolicyExtraction:
        """Parse ``document_text`` into structured policies."""


def _build_prompt(
    document_text: str,
    known_agents: list[str] | None,
    known_entities: list[str] | None,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) shared by real LLM providers."""
    system = (
        "You are a governance policy extraction engine. Extract every policy from "
        "the document and return ONLY a JSON object matching this schema: "
        '{"policies": [{"id": string|null, "name": string, "type": string|null, '
        '"description": string|null, "rules": [string], "governs": [string], '
        '"applies_to": [string]}]}. '
        "\"governs\" must contain agent names this policy governs. \"applies_to\" must "
        "contain tool, data source, or model names the policy applies to. Use the "
        "exact names from the provided known lists when they match. Output no prose."
    )
    agents = ", ".join(known_agents or []) or "(none provided)"
    entities = ", ".join(known_entities or []) or "(none provided)"
    user = (
        f"Known agents: {agents}\n"
        f"Known entities (tools/data sources/models): {entities}\n\n"
        f"Policy document:\n---\n{document_text}\n---"
    )
    return system, user


def get_llm_provider(settings=None) -> LLMProvider:
    """Select a provider based on settings, with graceful fallback.

    ``auto`` tries the real providers in order (Bedrock, OpenAI, Anthropic) and
    falls back to the deterministic heuristic when none are available. A forced
    provider that turns out to be unavailable also falls back to the heuristic
    (with a warning) so ingestion never hard-fails on missing credentials.
    """
    from app.config import get_settings
    from app.llm.anthropic_provider import AnthropicProvider
    from app.llm.bedrock import BedrockProvider
    from app.llm.heuristic import HeuristicPolicyExtractor
    from app.llm.openai_provider import OpenAIProvider

    settings = settings or get_settings()
    choice = (settings.llm_provider or "auto").lower()

    builders = {
        "bedrock": lambda: BedrockProvider(settings),
        "openai": lambda: OpenAIProvider(settings),
        "anthropic": lambda: AnthropicProvider(settings),
        "heuristic": lambda: HeuristicPolicyExtractor(),
    }

    if choice == "auto":
        for key in ("bedrock", "openai", "anthropic"):
            provider = builders[key]()
            if provider.is_available():
                logger.info("Selected LLM provider", extra={"provider": provider.name})
                return provider
        logger.info("No real LLM provider available; using heuristic fallback")
        return HeuristicPolicyExtractor()

    builder = builders.get(choice)
    if builder is None:
        logger.warning("Unknown LLM provider; using heuristic", extra={"requested": choice})
        return HeuristicPolicyExtractor()

    provider = builder()
    if not provider.is_available():
        logger.warning(
            "Requested LLM provider unavailable; using heuristic fallback",
            extra={"requested": provider.name},
        )
        return HeuristicPolicyExtractor()
    logger.info("Selected LLM provider", extra={"provider": provider.name})
    return provider
