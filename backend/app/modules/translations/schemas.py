"""Pydantic request and response schemas for Phase 10 On-Demand Content Translation."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class TranslateContentRequest(BaseModel):
    target_locale: str = Field(
        "en",
        description="Requested target locale (en, ml, hi, ta, es)",
    )


class DerivedTranslationResponse(BaseModel):
    """Non-destructive derived translation response.

    Never overwrites original post/comment fields and never exposes private author,
    moderator, or session identifiers.
    """

    id: str
    source_type: str
    source_id: str
    source_version_hash: str
    source_language: str
    source_language_label: str
    detected_source_language: Optional[str] = None
    is_source_language_uncertain: bool = False
    target_locale: str
    target_locale_label: str
    translated_title: Optional[str] = None
    translated_body: str
    direction: str = "ltr"
    provenance_label: str
    provider_name: str
    model_name: str
    is_mock_provider: bool
    cache_hit: bool
    created_at: str


class LanguageCapabilityItemSchema(BaseModel):
    code: str
    native_name: str
    english_name: str
    direction: str
    ui_locale_supported: bool
    content_posting_supported: bool
    on_demand_translation_target: bool
    meme_studio_font_shaping: str


class LanguageCapabilitiesResponse(BaseModel):
    supported_ui_locales: List[str]
    supported_translation_targets: List[str]
    capabilities: List[LanguageCapabilityItemSchema]
