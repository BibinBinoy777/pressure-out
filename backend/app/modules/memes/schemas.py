"""Pydantic v2 request and response schemas for Phase 8 AI Meme Studio."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MemeTextRegionSchema(BaseModel):
    id: str
    label: str
    x: int
    y: int
    width: int
    height: int
    align: str = "center"
    max_chars: int = 160
    default_font_size: int = 36
    min_font_size: int = 18


class MemeTemplateResponse(BaseModel):
    id: str
    slug: str
    name: str
    description: str
    category: str
    width: int
    height: int
    aspect_ratio: str
    text_regions: List[MemeTextRegionSchema]
    default_typography: Dict[str, Any]
    default_alt_text: str
    category_tags: List[str]
    license_info: str
    preview_url: str


class MemeTemplateListResponse(BaseModel):
    items: List[MemeTemplateResponse]
    ai_caption_enabled: bool
    ai_image_enabled: bool
    is_mock_provider: bool


class CaptionRegionInputSchema(BaseModel):
    region_id: str = Field(..., description="Region identifier such as 'top' or 'bottom'")
    text: str = Field("", max_length=200)
    align: Optional[str] = Field(None, description="Optional alignment override: left, center, right")
    font_size_override: Optional[int] = Field(None, ge=14, le=72)
    text_color: Optional[str] = None
    stroke_color: Optional[str] = None


class RenderTemplateRequest(BaseModel):
    template_id_or_slug: str = Field(..., description="Template ID or slug")
    captions: List[CaptionRegionInputSchema] = Field(default_factory=list)
    language: str = Field("en", description="BCP 47 language tag (en, ml, hi, ta, mul)")
    alt_text: Optional[str] = Field(None, max_length=500)
    output_format: str = Field("PNG", description="PNG or WEBP")


class MemeAssetResponse(BaseModel):
    """Privacy-safe representation of a rendered or generated meme asset.

    NEVER exposes `owner_user_id` or internal filesystem paths.
    """

    id: str
    source_type: str
    template_id: Optional[str] = None
    mime_type: str
    file_size_bytes: int
    sha256_hash: str
    width: int
    height: int
    captions: List[Dict[str, Any]] = Field(default_factory=list)
    caption_language: str
    alt_text: str
    safety_status: str
    is_published: bool
    download_url: str
    created_at: str


class SuggestCaptionsRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=400)
    tone: str = Field("sarcastic", description="sarcastic | wholesome | dramatic | absurd | deadpan")
    language: str = Field("en", description="BCP 47 language tag")
    template_slug: Optional[str] = Field("friday-455pm-deploy")
    max_suggestions: int = Field(4, ge=1, le=5)


class CaptionSuggestionItem(BaseModel):
    top_text: str
    bottom_text: str
    tone: str
    language: str


class SuggestCaptionsResponse(BaseModel):
    suggestions: List[CaptionSuggestionItem]
    sanitized_prompt: str
    pii_redactions: List[str] = Field(default_factory=list)
    provider_name: str
    model_name: str
    is_mock_provider: bool
    quota_remaining: int
    daily_limit: int


class CreateMemeJobRequest(BaseModel):
    job_type: str = Field("ai_image", description="ai_image or template_render")
    prompt: str = Field(..., min_length=3, max_length=400)
    style_tone: str = Field("sarcastic", description="sarcastic | wholesome | dramatic | absurd | deadpan")
    language: str = Field("en", description="BCP 47 language tag")
    template_id: Optional[str] = None
    captions: List[CaptionRegionInputSchema] = Field(default_factory=list)
    alt_text: Optional[str] = Field(None, max_length=500)
    idempotency_key: Optional[str] = Field(None, max_length=64)


class MemeJobResponse(BaseModel):
    """Asynchronous meme generation job status response.

    Accessible only by the job owner (never exposes `user_id` publicly).
    """

    id: str
    job_type: str
    status: str
    prompt: str
    prompt_language: str
    style_tone: str
    attempt_count: int
    provider_name: Optional[str] = None
    model_version: Optional[str] = None
    is_mock_provider: bool = False
    result_asset: Optional[MemeAssetResponse] = None
    error_code: Optional[str] = None
    error_message_safe: Optional[str] = None
    quota_remaining: Optional[int] = None
    created_at: str
    updated_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
