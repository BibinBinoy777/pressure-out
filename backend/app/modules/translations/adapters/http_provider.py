"""Configurable TranslationProviderAdapter resolver and DisabledTranslationProvider."""
from __future__ import annotations

from app.config import Settings
from app.core.errors import AppError
from app.modules.translations.adapters.base import (
    TranslationProviderAdapter,
    TranslationRequest,
    TranslationResult,
)
from app.modules.translations.adapters.mock_provider import LocalMockTranslationProvider


class DisabledTranslationProvider:
    """Explicitly reports that on-demand translation is disabled without mutating or faking output."""

    provider_name: str = "disabled"
    model_name: str = "none"

    async def translate(self, req: TranslationRequest) -> TranslationResult:
        raise AppError(
            code="TRANSLATION_UNAVAILABLE",
            message="On-demand translation is currently disabled or unavailable. The original content remains displayed.",
            status_code=503,
        )


def resolve_translation_adapter(settings: Settings) -> TranslationProviderAdapter:
    mode = (settings.translation_provider or "disabled").strip().lower()
    if mode in {"local_mock", "mock"}:
        return LocalMockTranslationProvider()
    return DisabledTranslationProvider()
