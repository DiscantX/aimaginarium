"""Reads the LLM configuration from a TOML file.

The file holds the same mapping :class:`ProviderFactory` takes, so the factory
stays independent of the file format. Keys never go in the file: each provider
names the environment variable that holds its key.

Example ``aimaginarium.toml``::

    [providers.gemini]
    kind = "gemini"
    model = "gemini-3.5-flash-lite"

    [providers.local]
    kind = "ollama"
    model = "phi4-mini"
    options = { num_thread = 2 }

    [tasks.default]
    provider = "gemini"

    [tasks.check]
    provider = "local"
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Union

from .factory import ConfigError, ProviderFactory
from .retry import RetryNotice

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10 only
    import tomli as tomllib

DEFAULT_FILE = "aimaginarium.toml"
ENV_VAR = "AIMAGINARIUM_CONFIG"


def find_config(path: Union[str, Path, None] = None) -> Path:
    """Locates the configuration file.

    Args:
        path: An explicit path. If omitted, the ``AIMAGINARIUM_CONFIG``
            environment variable is used, then ``aimaginarium.toml`` in the
            current directory.

    Returns:
        The path of an existing file.

    Raises:
        ConfigError: If no file exists at the chosen location.
    """
    chosen = Path(path or os.environ.get(ENV_VAR) or DEFAULT_FILE)
    if not chosen.is_file():
        raise ConfigError(f"configuration file not found: {chosen} (copy aimaginarium.example.toml to {DEFAULT_FILE})")
    return chosen


def load_config(path: Union[str, Path, None] = None) -> dict[str, Any]:
    """Reads a configuration file into the mapping the factory takes.

    Args:
        path: See :func:`find_config`.

    Returns:
        The parsed configuration.

    Raises:
        ConfigError: If the file is missing or is not valid TOML.
    """
    file = find_config(path)
    try:
        with file.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{file} is not valid TOML: {exc}") from exc


def factory_from_file(
    path: Union[str, Path, None] = None,
    env: Optional[Mapping[str, str]] = None,
    on_retry: Optional[Callable[[RetryNotice], None]] = None,
) -> ProviderFactory:
    """Builds a :class:`ProviderFactory` from a configuration file.

    Args:
        path: See :func:`find_config`.
        env: Environment to read keys from; defaults to ``os.environ``.
        on_retry: Called before each retry wait.

    Returns:
        The factory.
    """
    return ProviderFactory(load_config(path), env=env, on_retry=on_retry)
