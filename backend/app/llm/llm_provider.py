"""Configurable LLM provider (OpenAI-compatible chat API).

Implements both capabilities:
  * ``extract_policies`` - structured policy extraction (shares the common prompt).
  * ``generate_cypher``  - natural-language -> read-only Cypher for graph queries.

The model and credentials come from settings (``llm_api_key`` / ``llm_model``),
keeping the provider vendor-neutral. Requests use JSON mode so responses are
strict JSON objects.
"""

from __future__ import annotations

import json
import logging

from app.config import Settings
from app.llm.cypher import build_cypher_messages
from app.llm.provider import CypherQuery, LLMProvider, PolicyExtraction, _build_prompt

logger = logging.getLogger(__name__)


class LLMChatProvider(LLMProvider):
    name = "llm"

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.llm_api_key
        self._model = settings.llm_model
        self._max_tokens = settings.llm_max_tokens
        self._temperature = settings.llm_temperature

    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import groq  # noqa: F401
        except ImportError:
            return False
        return True

    def _complete_json(self, system: str, user: str) -> dict:
        """Call the chat model in JSON mode and return the parsed object."""
        from groq import Groq

        client = Groq(api_key=self._api_key)
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
        return json.loads(response.choices[0].message.content)

    def extract_policies(
        self,
        document_text: str,
        *,
        known_agents: list[str] | None = None,
        known_entities: list[str] | None = None,
    ) -> PolicyExtraction:
        system, user = _build_prompt(document_text, known_agents, known_entities)
        return PolicyExtraction(**self._complete_json(system, user))

    def generate_cypher(self, question: str, *, schema: str) -> CypherQuery:
        system, user = build_cypher_messages(question)
        data = self._complete_json(system, user)
        return CypherQuery(
            cypher=str(data.get("cypher", "")),
            explanation=str(data.get("explanation", "")),
        )
