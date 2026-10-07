"""Schema-valid output from any provider: validate, and retry with the error fed back."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .base import LLMProvider, Message, ProviderError, Request, Response

T = TypeVar("T", bound=BaseModel)

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


class StructuredOutputError(ProviderError):
    """The model never produced output matching the schema."""


class StructuredCaller:
    """Gets Pydantic-validated output from a provider.

    This is the common floor for providers that cannot enforce a schema: the
    reply is validated, and on failure the model sees its own reply plus the
    errors and tries again.

    Attributes:
        provider: The provider to call.
        max_attempts: Total tries, including the first.
    """

    def __init__(self, provider: LLMProvider, max_attempts: int = 3):
        self.provider = provider
        self.max_attempts = max_attempts

    async def call(self, request: Request, schema: type[T]) -> tuple[T, Response]:
        """Calls the provider until the reply validates against ``schema``.

        Args:
            request: The call to make. Its ``schema`` field is set for you.
            schema: Pydantic model the reply must match.

        Returns:
            The validated object and the final response.

        Raises:
            StructuredOutputError: If no attempt validates.
        """
        request = self._prepare(request, schema)
        errors = ""
        for _ in range(self.max_attempts):
            response = await self.provider.generate(request)
            try:
                return schema.model_validate_json(strip_fences(response.text)), response
            except ValidationError as exc:
                errors = _summarise(exc)
                request = replace(
                    request,
                    messages=request.messages
                    + (Message("assistant", response.text), Message("user", _repair_prompt(errors))),
                )
        raise StructuredOutputError(f"no valid reply after {self.max_attempts} attempts: {errors}")

    def _prepare(self, request: Request, schema: type[BaseModel]) -> Request:
        """Attaches the schema, and describes it in the prompt if it cannot be enforced."""
        request = replace(request, schema=schema)
        if self.provider.capabilities(request.model).schema_enforcement:
            return request
        hint = "Reply with only a JSON object matching this JSON schema:\n" + json.dumps(schema.model_json_schema())
        return replace(request, system=f"{request.system}\n\n{hint}".strip())


def strip_fences(text: str) -> str:
    """Removes a Markdown code fence some models wrap around JSON."""
    match = _FENCE.match(text)
    return match.group(1) if match else text


def _summarise(exc: ValidationError, limit: int = 5) -> str:
    """Condenses a validation error into one line per problem."""
    problems = [f"{'.'.join(map(str, e['loc'])) or 'reply'}: {e['msg']}" for e in exc.errors()[:limit]]
    return "; ".join(problems)


def _repair_prompt(errors: str) -> str:
    """The follow-up message asking the model to fix its reply."""
    return f"That reply was not valid ({errors}). Reply again with only the corrected JSON."
