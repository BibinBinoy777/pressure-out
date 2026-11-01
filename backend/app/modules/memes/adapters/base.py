"""Provider-neutral AI caption and image generation interfaces for Phase 8."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class CaptionRequest:
    sanitized_prompt: str
    tone: str          # sarcastic | wholesome | dramatic | absurd | deadpan
    language_tag: str  # BCP 47 tag e.g. "en", "ml", "hi", "ta"
    template_slug: str = "friday-455pm-deploy"
    max_suggestions: int = 4


@dataclass(frozen=True)
class CaptionCandidate:
    top_text: str
    bottom_text: str
    tone: str
    language_tag: str


@dataclass(frozen=True)
class CaptionResult:
    candidates: Sequence[CaptionCandidate]
    provider_name: str
    model_name: str
    is_mock: bool
    input_tokens: int
    output_tokens: int
    estimated_cost_micros: int


@dataclass(frozen=True)
class ImageGenRequest:
    job_id: str
    sanitized_prompt: str
    style_tone: str
    language_tag: str
    width: int = 800
    height: int = 800


@dataclass(frozen=True)
class ImageGenResult:
    image_bytes: bytes
    mime_type: str
    provider_name: str
    model_name: str
    is_mock: bool
    estimated_cost_micros: int


class CaptionProviderAdapter(Protocol):
    """Interface for workplace meme caption generation providers."""

    async def generate_captions(self, req: CaptionRequest) -> CaptionResult: ...


class ImageProviderAdapter(Protocol):
    """Interface for asynchronous workplace meme image generation providers."""

    async def generate_image(self, req: ImageGenRequest) -> ImageGenResult: ...
