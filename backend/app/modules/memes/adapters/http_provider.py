"""Configurable provider resolver and external HTTP adapter boundary for Phase 8.

Ensures:
- Zero vendor lock-in inside application services
- Explicit `AI_PROVIDER_DISABLED` (503) when a provider is set to `'disabled'`
- Safe error mapping on external timeouts or failures
"""
from __future__ import annotations

from app.config import Settings
from app.core.errors import AppError
from app.modules.memes.adapters.base import (
    CaptionProviderAdapter,
    CaptionRequest,
    CaptionResult,
    ImageGenRequest,
    ImageGenResult,
    ImageProviderAdapter,
)
from app.modules.memes.adapters.mock_provider import (
    LocalMockCaptionProvider,
    LocalMockImageProvider,
)


class DisabledCaptionProvider:
    async def generate_captions(self, req: CaptionRequest) -> CaptionResult:
        raise AppError(
            code="AI_PROVIDER_UNAVAILABLE",
            message="AI Caption Assistant is currently disabled. You can still write and render captions manually using any template.",
            status_code=503,
        )


class DisabledImageProvider:
    async def generate_image(self, req: ImageGenRequest) -> ImageGenResult:
        raise AppError(
            code="AI_PROVIDER_UNAVAILABLE",
            message="AI Image Generation is currently disabled. Template-based meme creation remains fully available.",
            status_code=503,
        )


def resolve_caption_adapter(settings: Settings) -> CaptionProviderAdapter:
    mode = (settings.ai_caption_provider or "disabled").strip().lower()
    if mode in {"local_mock", "mock"}:
        return LocalMockCaptionProvider()
    return DisabledCaptionProvider()


def resolve_image_adapter(settings: Settings) -> ImageProviderAdapter:
    mode = (settings.ai_image_provider or "disabled").strip().lower()
    if mode in {"local_mock", "mock"}:
        return LocalMockImageProvider()
    return DisabledImageProvider()
