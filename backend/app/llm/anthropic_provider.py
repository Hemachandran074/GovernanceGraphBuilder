"""Optional Anthropic provider (lazy import; requires the ``anthropic`` SDK)."""

from __future__ import annotations

import logging

from app.config import Settings
from app.llm.bedrock import _extract_json
from app.llm.provider import LLMProvider, PolicyExtraction, _build_prompt

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.anthropic_api_key
        self._model = settings.anthropic_model
        self._max_tokens = settings.llm_max_tokens
        self._temperature = settings.llm_temperature

    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return True

    def extract_policies(
        self,
        document_text: str,
        *,
        known_agents: list[str] | None = None,
        known_entities: list[str] | None = None,
    ) -> PolicyExtraction:
        import anthropic

        system, user = _build_prompt(document_text, known_agents, known_entities)
        client = anthropic.Anthropic(api_key=self._api_key)
        message = client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        data = _extract_json(message.content[0].text)
        return PolicyExtraction(**data)
