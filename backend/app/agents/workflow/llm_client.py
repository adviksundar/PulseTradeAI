import asyncio
import json
import logging
from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.core.config import Settings

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)
STRUCTURED_MAX_OUTPUT_TOKENS = 2400


class StructuredOpenAIClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.enabled = bool(
            settings.openai_api_key and not settings.use_mock_ai)
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key) if self.enabled else None
        self.last_status: str = "fallback"
        self.last_error_message: str | None = None
        self.last_call_count: int = 0
        self.last_success_count: int = 0
        self.total_call_count: int = 0
        self.total_success_count: int = 0

    async def generate_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_payload: dict,
        output_model: type[T],
    ) -> T:
        if not self.client:
            self.last_status = "fallback"
            self.last_error_message = "OpenAI client is disabled"
            raise RuntimeError("OpenAI client is disabled")

        schema = output_model.model_json_schema()
        last_error: Exception | None = None
        self.last_call_count = 0
        self.last_success_count = 0
        compact_payload = json.dumps(
            user_payload, default=str, separators=(",", ":"))
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": compact_payload},
        ]
        for attempt in range(3):
            try:
                self.last_call_count += 1
                self.total_call_count += 1
                request_kwargs = {
                    "model": model,
                    "input": messages,
                    "max_output_tokens": STRUCTURED_MAX_OUTPUT_TOKENS,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": output_model.__name__,
                            "schema": schema,
                            "strict": True,
                        }
                    },
                }
                if model.startswith("gpt-5"):
                    request_kwargs["reasoning"] = {"effort": "minimal"}
                response = await self.client.responses.create(**request_kwargs)
                self.last_status = "ok"
                self.last_error_message = None
                output_text = response.output_text or ""
                if not output_text.strip():
                    logger.warning(
                        "empty_structured_output attempt=%d model=%s schema=%s summary=%s",
                        attempt + 1,
                        model,
                        output_model.__name__,
                        json.dumps(summarize_response(response), default=str),
                    )
                    messages = retry_messages(
                        system_prompt,
                        compact_payload,
                        empty_output=True,
                    )
                    await asyncio.sleep(0.8)
                    continue
                parsed = output_model.model_validate_json(output_text)
                self.last_success_count = 1
                self.total_success_count += 1
                return parsed
            except ValidationError as exc:
                last_error = exc
                self.last_status = "error"
                self.last_error_message = str(exc)[:240]
                messages = retry_messages(system_prompt, compact_payload)
            except Exception as exc:
                last_error = exc
                self.last_status = "error"
                self.last_error_message = str(exc)[:240]
        logger.warning(
            "structured_openai_call_failed model=%s schema=%s error=%s",
            model,
            output_model.__name__,
            self.last_error_message,
        )
        raise RuntimeError(
            "Structured OpenAI generation failed") from last_error


def retry_messages(
    system_prompt: str,
    compact_payload: str,
    *,
    empty_output: bool = False,
) -> list[dict[str, str]]:
    instruction = (
        "The previous response did not produce complete schema-valid JSON. "
        if empty_output
        else "The previous response failed JSON schema validation. "
    )
    return [
        {
            "role": "system",
            "content": (
                f"{system_prompt} Do not include hidden reasoning or explanations. "
                "Return only the compact JSON object required by the schema."
            ),
        },
        {
            "role": "user",
            "content": (
                f"{instruction}"
                "Use very short strings, complete every required field, and do not repeat article text. "
                f"Payload: {compact_payload}"
            ),
        },
    ]


def summarize_response(response: object) -> dict[str, object]:
    status = getattr(response, "status", None)
    incomplete = getattr(response, "incomplete_details", None)
    reason = getattr(incomplete, "reason", None) if incomplete else None
    usage = getattr(response, "usage", None)
    output = getattr(response, "output", None) or []
    output_types: list[str] = []
    for item in output:
        output_types.append(str(getattr(item, "type", type(item).__name__)))
    return {
        "id": getattr(response, "id", None),
        "status": status,
        "incomplete_reason": reason,
        "output_types": output_types,
        "usage": usage.model_dump(mode="json") if hasattr(usage, "model_dump") else str(usage),
    }
