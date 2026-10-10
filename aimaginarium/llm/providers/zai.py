"""Z.AI provider, using Z.AI's OpenAI-compatible interface.

Install the optional dependency with ``pip install "aimaginarium[zai]"``.
"""

from __future__ import annotations

from typing import Any, Optional

from ..base import Capabilities
from .openai import OpenAIProvider

DEFAULT_CAPABILITIES = Capabilities(schema_enforcement=True, json_mode=True, tool_calling=True)


class ZAIProvider(OpenAIProvider):
    """Runs requests against the Z.AI API using the OpenAI-compatible SDK.

    Attributes:
        default_model: Model used when a request names none (default: "glm-4.7-flash").
    """

    def __init__(
        self,
        default_model: str = "glm-4.7-flash",
        base_url: str = "https://api.z.ai/api/paas/v4/",
        api_key: Optional[str] = None,
        config: Optional[dict[str, Any]] = None,
        capabilities: Optional[dict[str, Capabilities]] = None,
        client: Optional[Any] = None,
    ):
        """Initialises the Z.AI provider.

        Args:
            default_model: Model used when a request names none (default: "glm-4.7-flash").
            base_url: API base URL (default: "https://api.z.ai/api/paas/v4/").
            api_key: API key; if omitted the SDK reads it from the environment.
            config: Extra configuration passed to every request (such as thinking mode).
            capabilities: Per-model overrides of :data:`DEFAULT_CAPABILITIES`.
            client: A ready OpenAI client (or test double); one is created if omitted.
        """
        super().__init__(
            default_model=default_model,
            base_url=base_url,
            api_key=api_key,
            config=config,
            capabilities=capabilities,
            client=client,
        )
