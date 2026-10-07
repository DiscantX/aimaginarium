"""LLM gateway: one interface over many model providers."""

from .base import (
    Capabilities, Chunk, LLMProvider, Message, ProviderError, Request, Response,
    RetryableError, StreamEvent, Usage,
)
from .factory import ConfigError, ProviderFactory, Route
from .narration import NarrationExtractor, narration_events
from .retry import retry
from .structured import StructuredCaller, StructuredOutputError

__all__ = [
    "Capabilities", "Chunk", "ConfigError", "LLMProvider", "Message", "NarrationExtractor", "ProviderError", "ProviderFactory", "Request", "Response",
    "RetryableError", "Route", "StreamEvent", "StructuredCaller", "StructuredOutputError", "Usage", "narration_events", "retry",
]
