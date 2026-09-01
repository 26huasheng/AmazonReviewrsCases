from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .discovery_rules import validate_arbitration_response, validate_llm_response
from .prompts import render_arbitration_prompt, render_prompt_pair


MARKET_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decision", "markets"],
    "properties": {
        "decision": {"enum": ["KEEP", "SPLIT", "REVIEW"]},
        "markets": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["market_label", "center_term", "equivalent_terms",
                             "support_terms", "confidence"],
                "properties": {
                    "market_label": {"type": "string"},
                    "center_term": {"type": "string"},
                    "equivalent_terms": {"type": "array", "maxItems": 20,
                                         "items": {"type": "string"}},
                    "support_terms": {"type": "array", "maxItems": 40,
                                      "items": {"type": "string"}},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
    },
}

ARBITRATION_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["selected_market"],
    "properties": {
        "selected_market": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
}


@dataclass(frozen=True)
class LLMResult:
    parsed_response: dict[str, Any]
    model: str
    provider: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


class MarketLLMClient:
    def __init__(self, api_key: str | None = None, model: str | None = None,
                 base_url: str | None = None, provider: str = "openai_compatible"):
        self.api_key = api_key or os.environ.get("LLM_API_KEY")
        self.model = model or os.environ.get("LLM_MODEL")
        self.base_url = base_url or os.environ.get("LLM_BASE_URL")
        self.provider = provider
        self.response_mode = os.environ.get("LLM_RESPONSE_MODE", "auto").strip().lower() or "auto"
        if self.response_mode not in {"auto", "json_schema", "json_object"}:
            raise RuntimeError(f"invalid LLM_RESPONSE_MODE: {self.response_mode}")
        if os.environ.get("SEMS_E2E_OFFLINE") == "1":
            raise RuntimeError("real market LLM provider forbidden in offline E2E")
        if not self.api_key or not self.model or not self.base_url:
            raise RuntimeError("market_discovery_llm_configuration_missing")

    def call(self, evidence: dict[str, Any], round_number: int) -> LLMResult:
        endpoint = self.base_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        system_prompt, user_prompt = render_prompt_pair(evidence, round_number)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "repetition_penalty": 1.0,
            "max_tokens": 4096,
        }
        mode = "json_schema" if self.response_mode == "auto" else self.response_mode
        last_error: Exception | None = None
        for attempt in range(3):
            payload["response_format"] = ({"type": "json_object"} if mode == "json_object" else
                {"type": "json_schema", "json_schema": {
                    "name": "path_market_discovery", "strict": True,
                    "schema": MARKET_RESPONSE_SCHEMA,
                }})
            try:
                response = requests.post(endpoint, headers={
                    "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                }, json=payload, timeout=180)
                if response.status_code in {401, 403}:
                    response.raise_for_status()
                if (self.response_mode == "auto" and mode == "json_schema" and
                        response.status_code in {400, 404, 422}):
                    message = response.text.lower()
                    if "response_format" in message or "json_schema" in message:
                        mode = "json_object"
                        continue
                response.raise_for_status()
                body = response.json()
                content = body["choices"][0]["message"]["content"]
                if isinstance(content, list):
                    content = "".join(part.get("text", "") for part in content
                                      if isinstance(part, dict))
                parsed = validate_llm_response(json.loads(content))
                usage = body.get("usage") or {}
                return LLMResult(
                    parsed_response=parsed,
                    model=str(body.get("model") or self.model), provider=self.provider,
                    input_tokens=usage.get("prompt_tokens"),
                    output_tokens=usage.get("completion_tokens"),
                    total_tokens=usage.get("total_tokens"),
                )
            except (requests.Timeout, requests.ConnectionError, json.JSONDecodeError,
                    KeyError, TypeError, ValueError) as exc:
                last_error = exc
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status not in {429, 500, 502, 503, 504}:
                    raise
                last_error = exc
            if attempt < 2:
                time.sleep((2, 5)[attempt])
        assert last_error is not None
        raise last_error

    def arbitrate(self, title: str, candidates: list[str],
                  product_id: str | None = None) -> str | None:
        """Resolve an AMBIGUOUS product among already-defined path-local markets.

        This LLM call is only for intra-path product assignment. Cross-path market
        merging never calls an LLM.
        """
        system_prompt, user_prompt = render_arbitration_prompt(title, candidates)
        endpoint = self.base_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "max_tokens": 1024,
        }
        mode = "json_schema" if self.response_mode == "auto" else self.response_mode
        last_error: Exception | None = None
        for attempt in range(3):
            payload["response_format"] = ({"type": "json_object"} if mode == "json_object" else
                {"type": "json_schema", "json_schema": {
                    "name": "ambiguous_market_arbitration", "strict": True,
                    "schema": ARBITRATION_RESPONSE_SCHEMA,
                }})
            try:
                response = requests.post(endpoint, headers={
                    "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                }, json=payload, timeout=180)
                if response.status_code in {401, 403}:
                    response.raise_for_status()
                if (self.response_mode == "auto" and mode == "json_schema" and
                        response.status_code in {400, 404, 422}):
                    message = response.text.lower()
                    if "response_format" in message or "json_schema" in message:
                        mode = "json_object"
                        continue
                response.raise_for_status()
                body = response.json()
                content = body["choices"][0]["message"]["content"]
                if isinstance(content, list):
                    content = "".join(part.get("text", "") for part in content
                                      if isinstance(part, dict))
                parsed = json.loads(content)
                return validate_arbitration_response(parsed, candidates)
            except (requests.Timeout, requests.ConnectionError, json.JSONDecodeError,
                    KeyError, TypeError, ValueError) as exc:
                last_error = exc
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status not in {429, 500, 502, 503, 504}:
                    raise
                last_error = exc
            if attempt < 2:
                time.sleep((2, 5)[attempt])
        assert last_error is not None
        raise last_error


class FixtureMarketLLMClient:
    """Deterministic replay through the same response validator as network responses."""

    provider = "fixture"
    model = "deterministic_fixture"

    def __init__(self, fixture: Path) -> None:
        self.fixture = fixture.expanduser().resolve()
        value = json.loads(self.fixture.read_text(encoding="utf-8"))
        self.responses = value["responses"] if "responses" in value else value
        self.arbitrations = value.get("arbitrations", {}) if isinstance(value, dict) else {}
        self.calls: list[tuple[str, int]] = []
        self.arbitration_calls: list[str] = []

    def call(self, evidence: dict[str, Any], round_number: int) -> LLMResult:
        path_id = str(evidence["path_id"])
        key = f"{path_id}:round{round_number}"
        if key not in self.responses:
            raise KeyError(f"market fixture response missing {key}")
        self.calls.append((path_id, round_number))
        parsed = validate_llm_response(self.responses[key])
        return LLMResult(parsed_response=parsed, model=self.model, provider=self.provider,
                         input_tokens=0, output_tokens=0, total_tokens=0)

    def arbitrate(self, title: str, candidates: list[str],
                  product_id: str | None = None) -> str | None:
        value = self.arbitrations.get(product_id) if product_id else None
        self.arbitration_calls.append(str(product_id or title))
        if value is None or value == "NONE":
            return None
        return validate_arbitration_response({"selected_market": value}, candidates)
