"""Builds providers from a configuration mapping and chooses a model per task.

The configuration is a plain mapping, so it can come from TOML, JSON or code.
Keys are never stored in it: each provider names the environment variable that
holds its key (load a ``.env`` file into the environment before building).

Example::

    {
        "providers": {
            "gemini": {"kind": "gemini", "model": "gemini-3.5-flash-lite"},
            "local": {"kind": "ollama", "model": "phi4-mini", "options": {"num_thread": 2}},
        },
        "tasks": {
            "default": {"provider": "gemini"},
            "summarize": {"provider": "local"},
            "narrate": {
                "provider": "gemini",
                "model": "gemini-3.5-flash",
                "fallback": ["gemini:gemini-3.5-flash-lite", "local"],
            },
        },
        "fallback": {"cooldown": 60},
    }

A fallback entry is ``provider`` or ``provider:model``; the model may itself
contain colons (only the first one separates).
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Mapping, Optional

from .base import Capabilities, LLMProvider
from .retry import RetryingProvider, RetryNotice, RetryPolicy
from .route import Candidate, Cooldown, FallbackNotice, Route

Builder = Callable[[Mapping[str, Any], Mapping[str, str]], LLMProvider]


class ConfigError(Exception):
    """The LLM configuration is missing or invalid."""


def _capabilities(spec: Mapping[str, Any]) -> Optional[dict[str, Capabilities]]:
    """Reads optional per-model capability overrides from a provider spec."""
    raw = spec.get("capabilities")
    return {model: Capabilities(**fields) for model, fields in raw.items()} if raw else None


def _build_ollama(spec: Mapping[str, Any], env: Mapping[str, str]) -> LLMProvider:
    from .providers.ollama import OllamaProvider

    return OllamaProvider(
        spec["model"],
        base_url=spec.get("base_url", "http://localhost:11434"),
        options=spec.get("options"),
        capabilities=_capabilities(spec),
    )


def _build_gemini(spec: Mapping[str, Any], env: Mapping[str, str]) -> LLMProvider:
    from .providers.gemini import GeminiProvider

    variable = spec.get("api_key_env", "GEMINI_API_KEY")
    if not env.get(variable):
        raise ConfigError(f"Gemini needs an API key: set {variable} in .env or the environment")
    return GeminiProvider(
        spec["model"], api_key=env[variable], config=spec.get("config"), capabilities=_capabilities(spec)
    )


class ProviderFactory:
    """Creates providers on first use and routes each task to a provider and model."""

    def __init__(
        self,
        config: Mapping[str, Any],
        env: Optional[Mapping[str, str]] = None,
        builders: Optional[Mapping[str, Builder]] = None,
        on_retry: Optional[Callable[[RetryNotice], None]] = None,
        on_fallback: Optional[Callable[[FallbackNotice], None]] = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        """Initialises the factory.

        Args:
            config: Mapping with ``providers`` (name to spec) and ``tasks`` (name to
                ``{"provider": ..., "model": ...}``; ``model`` is optional).
            env: Environment to read keys from; defaults to ``os.environ``.
            builders: Extra provider kinds, as ``kind -> builder(spec, env)``.
            on_retry: Called before each retry wait, so a client can tell the player.
            on_fallback: Called when a task moves on to its next candidate.
            clock: Monotonic time source for the fallback cool-down (replaceable in tests).

        Every provider is wrapped in :class:`RetryingProvider`. The optional ``retry``
        mapping (top level, or inside a provider spec to override it) sets the
        :class:`RetryPolicy` fields.
        """
        self._config = config
        self._env = os.environ if env is None else env
        self._builders: dict[str, Builder] = {"ollama": _build_ollama, "gemini": _build_gemini, **(builders or {})}
        self._on_retry = on_retry
        self._on_fallback = on_fallback
        self._cooldown = Cooldown(self._config.get("fallback", {}).get("cooldown", 60.0), clock)
        self._providers: dict[str, LLMProvider] = {}

    def route(self, task: str) -> Route:
        """Chooses the candidates for a task.

        Args:
            task: Task name, such as ``"narrate"``. Unknown tasks use ``"default"``.

        Returns:
            The route: the task's provider and model, then its fallbacks in order.

        Raises:
            ConfigError: If the task, a provider or a kind is not configured.
        """
        tasks = self._config.get("tasks", {})
        spec = tasks.get(task) or tasks.get("default")
        if spec is None:
            raise ConfigError(f"no model configured for task {task!r} and no default task")
        entries = [(spec["provider"], spec.get("model"))] + [self._parse(e) for e in spec.get("fallback", [])]
        return Route([self._candidate(*e) for e in entries], task, self._cooldown, self._on_fallback)

    def candidate(self, spec: str) -> Candidate:
        """Builds a candidate from ``provider`` or ``provider:model``, outside any task's route.

        Args:
            spec: For example ``"gemini:gemma-4-31b-it"``.

        Raises:
            ConfigError: If the provider is not configured.
        """
        return self._candidate(*self._parse(spec))

    @staticmethod
    def _parse(entry: str) -> tuple[str, Optional[str]]:
        """Splits a fallback entry ``provider`` or ``provider:model`` at its first colon."""
        name, _, model = entry.partition(":")
        return name, model or None

    def _candidate(self, name: str, model: Optional[str]) -> Candidate:
        """Builds a candidate, using the provider's default model if none is given."""
        provider = self._provider(name)
        return Candidate(name, provider, model or self._config["providers"][name]["model"])

    def _provider(self, name: str) -> LLMProvider:
        """Returns the provider with this name, building it the first time."""
        if name not in self._providers:
            spec = self._config.get("providers", {}).get(name)
            if spec is None:
                raise ConfigError(f"provider {name!r} is not defined")
            builder = self._builders.get(spec.get("kind"))
            if builder is None:
                raise ConfigError(f"provider {name!r} has unknown kind {spec.get('kind')!r}")
            policy = RetryPolicy(**{**self._config.get("retry", {}), **spec.get("retry", {})})
            self._providers[name] = RetryingProvider(builder(spec, self._env), policy, self._on_retry)
        return self._providers[name]
