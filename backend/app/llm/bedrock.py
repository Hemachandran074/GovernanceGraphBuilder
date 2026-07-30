"""AWS Bedrock LLM provider (primary real provider).

Uses the Bedrock Runtime ``converse`` API with a Claude model to extract
structured policies. Credentials are resolved from the standard AWS chain
(environment, shared config, or — in production — the ECS task role), so no
secrets live in code.
"""

from __future__ import annotations

import json
import logging

from app.config import Settings
from app.llm.provider import LLMProvider, PolicyExtraction, _build_prompt

logger = logging.getLogger(__name__)


class BedrockProvider(LLMProvider):
    name = "bedrock"

    def __init__(self, settings: Settings) -> None:
        self._region = settings.aws_region
        self._model_id = settings.bedrock_model_id
        self._max_tokens = settings.llm_max_tokens
        self._temperature = settings.llm_temperature

    def is_available(self) -> bool:
        try:
            import boto3  # noqa: F401
            from botocore.session import Session
        except ImportError:
            return False
        try:
            # Available only when AWS credentials can actually be resolved.
            return Session().get_credentials() is not None
        except Exception:  # noqa: BLE001 - availability probe must not raise
            return False

    def extract_policies(
        self,
        document_text: str,
        *,
        known_agents: list[str] | None = None,
        known_entities: list[str] | None = None,
    ) -> PolicyExtraction:
        import boto3

        system, user = _build_prompt(document_text, known_agents, known_entities)
        client = boto3.client("bedrock-runtime", region_name=self._region)

        response = client.converse(
            modelId=self._model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"maxTokens": self._max_tokens, "temperature": self._temperature},
        )
        text = response["output"]["message"]["content"][0]["text"]
        data = _extract_json(text)
        return PolicyExtraction(**data)


def _extract_json(text: str) -> dict:
    """Extract the first JSON object from a model response (tolerant of fences)."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Strip a leading ```json / ``` fence and the trailing fence.
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[: -3]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in model response.")
    return json.loads(cleaned[start : end + 1])
