"""Provider-neutral TranslationProviderAdapter interface for Phase 10."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class TranslationRequest:
    source_type: str
    source_language: str
    target_locale: str
    source_title: Optional[str]
    source_body: str


@dataclass(frozen=True)
class TranslationResult:
    translated_title: Optional[str]
    translated_body: str
    detected_source_language: str
    target_locale: str
    provider_name: str
    model_name: str
    is_mock: bool
    input_chars: int
    output_chars: int
    estimated_cost_micros: int


class TranslationProviderAdapter(Protocol):
    """Interface for on-demand non-destructive content translation providers."""

    async def translate(self, req: TranslationRequest) -> TranslationResult: ...
