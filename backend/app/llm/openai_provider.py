"""Optional OpenAI provider (lazy import; requires the ``openai`` SDK)."""

from __future__ import annotations

import json
import logging

from app.config import Settings
from app.llm.provider import LLMProvider, PolicyExtraction, _build_prompt

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.openai_api_key
        self._model = settings.openai_model
        self._max_tokens = settings.llm_max_tokens
        self._temperature = settings.llm_temperature

    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import openai  # noqa: F401
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
        from openai import OpenAI

        system, user = _build_prompt(document_text, known_agents, known_entities)
        client = OpenAI(api_key=self._api_key)
        response = client.chat.completions.create(
            model=self._model,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        data = json.loads(response.choices[0].message.content)
        return PolicyExtraction(**data)
