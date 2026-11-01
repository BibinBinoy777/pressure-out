"""Business logic for Phase 8 AI Meme Studio: templates, synchronous rendering,
AI caption suggestions, asynchronous image generation jobs, quotas, and spend caps.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config import Settings, get_settings
from app.core.errors import AppError
from app.core.unicode import normalize_unicode_nfc
from app.modules.identity.schemas import validate_bcp47_tag
from app.modules.memes.adapters.base import (
    CaptionProviderAdapter,
    CaptionRequest,
)
from app.modules.memes.adapters.http_provider import resolve_caption_adapter
from app.modules.memes.safety import (
    sanitize_and_validate_meme_prompt,
    validate_meme_tone,
)
from app.modules.memes.schemas import (
    CaptionSuggestionItem,
    CreateMemeJobRequest,
    MemeAssetResponse,
    MemeJobResponse,
    MemeTemplateListResponse,
    MemeTemplateResponse,
    MemeTextRegionSchema,
    RenderTemplateRequest,
    SuggestCaptionsRequest,
    SuggestCaptionsResponse,
)
from app.modules.memes.storage import LocalFilesystemStorageAdapter, StorageAdapter, create_storage_adapter
from app.modules.memes.template_renderer import (
    RenderCaptionInput,
    TemplateRenderer,
    TextRegionSpec,
)

TEMPLATE_COLUMNS = (
    "id",
    "slug",
    "name",
    "description",
    "category",
    "storage_key",
    "width",
    "height",
    "aspect_ratio",
    "text_regions",
    "default_typography",
    "default_alt_text",
    "category_tags",
    "license_info",
    "is_active",
    "created_at",
)

ASSET_COLUMNS = (
    "id",
    "owner_user_id",
    "source_type",
    "template_id",
    "storage_key",
    "mime_type",
    "file_size_bytes",
    "sha256_hash",
    "width",
    "height",
    "captions_json",
    "caption_language",
    "alt_text",
    "safety_status",
    "is_published",
    "expires_at",
    "created_at",
)

JOB_COLUMNS = (
    "id",
    "user_id",
    "idempotency_key",
    "job_type",
    "template_id",
    "user_prompt",
    "prompt_language",
    "style_tone",
    "options_json",
    "status",
    "attempt_count",
    "provider_name",
    "model_version",
    "is_mock_provider",
    "caption_suggestions",
    "result_asset_id",
    "error_code",
    "error_message_safe",
    "estimated_cost_micros",
    "created_at",
    "updated_at",
    "started_at",
    "completed_at",
)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now_utc().isoformat()


def _today_prefix_utc() -> str:
    return _now_utc().strftime("%Y-%m-%d")


def _row_to_dict(columns: tuple[str, ...], row: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip(columns, row))


class MemeStudioService:
    """Service coordinating template rendering, AI captions, async image jobs, and quotas."""

    def __init__(
        self,
        session: Any,
        settings: Optional[Settings] = None,
        storage: Optional[StorageAdapter] = None,
        renderer: Optional[TemplateRenderer] = None,
        caption_adapter: Optional[CaptionProviderAdapter] = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.storage: StorageAdapter = storage or create_storage_adapter(self.settings)
        self.renderer = renderer or TemplateRenderer()
        self.caption_adapter = caption_adapter or resolve_caption_adapter(self.settings)

    def _serialize_template(self, row_dict: dict[str, Any]) -> MemeTemplateResponse:
        raw_regions = json.loads(str(row_dict.get("text_regions") or "[]"))
        regions = [MemeTextRegionSchema(**r) for r in raw_regions]
        typography = json.loads(str(row_dict.get("default_typography") or "{}"))
        tags = json.loads(str(row_dict.get("category_tags") or "[]"))
        slug = str(row_dict["slug"])
        return MemeTemplateResponse(
            id=str(row_dict["id"]),
            slug=slug,
            name=str(row_dict["name"]),
            description=str(row_dict.get("description") or ""),
            category=str(row_dict.get("category") or "general"),
            width=int(row_dict["width"]),
            height=int(row_dict["height"]),
            aspect_ratio=str(row_dict.get("aspect_ratio") or "1:1"),
            text_regions=regions,
            default_typography=typography,
            default_alt_text=str(row_dict["default_alt_text"]),
            category_tags=tags,
            license_info=str(row_dict.get("license_info") or "CC0-1.0"),
            preview_url=f"/api/v1/memes/templates/{slug}/preview",
        )

    def _serialize_asset(self, row_dict: dict[str, Any]) -> MemeAssetResponse:
        asset_id = str(row_dict["id"])
        raw_captions = row_dict.get("captions_json") or "[]"
        try:
            captions_list = json.loads(str(raw_captions)) if isinstance(raw_captions, str) else list(raw_captions)
        except Exception:
            captions_list = []
        return MemeAssetResponse(
            id=asset_id,
            source_type=str(row_dict["source_type"]),
            template_id=row_dict.get("template_id"),
            mime_type=str(row_dict["mime_type"]),
            file_size_bytes=int(row_dict["file_size_bytes"]),
            sha256_hash=str(row_dict["sha256_hash"]),
            width=int(row_dict["width"]),
            height=int(row_dict["height"]),
            captions=captions_list,
            caption_language=str(row_dict.get("caption_language") or "en"),
            alt_text=str(row_dict["alt_text"]),
            safety_status=str(row_dict["safety_status"]),
            is_published=bool(row_dict.get("is_published")),
            download_url=f"/api/v1/memes/assets/{asset_id}/download",
            created_at=str(row_dict["created_at"]),
        )

    async def list_templates(
        self, *, category: Optional[str] = None
    ) -> MemeTemplateListResponse:
        clauses = ["is_active = 1"]
        params: List[Any] = []
        if category and category.strip():
            clauses.append("category = ?")
            params.append(category.strip().lower())

        where_sql = " AND ".join(clauses)
        rows = await self.session.execute(
            f"SELECT {', '.join(TEMPLATE_COLUMNS)} FROM meme_templates WHERE {where_sql} ORDER BY id ASC",
            tuple(params),
        )
        items = [self._serialize_template(_row_to_dict(TEMPLATE_COLUMNS, r)) for r in rows]
        cap_mode = (self.settings.ai_caption_provider or "disabled").strip().lower()
        img_mode = (self.settings.ai_image_provider or "disabled").strip().lower()
        return MemeTemplateListResponse(
            items=items,
            ai_caption_enabled=cap_mode != "disabled",
            ai_image_enabled=img_mode != "disabled",
            is_mock_provider=cap_mode in {"local_mock", "mock"} or img_mode in {"local_mock", "mock"},
        )

    async def get_template_by_id_or_slug(self, identifier: str) -> dict[str, Any]:
        cleaned = identifier.strip()
        rows = await self.session.execute(
            f"SELECT {', '.join(TEMPLATE_COLUMNS)} FROM meme_templates WHERE (id = ? OR slug = ?) AND is_active = 1",
            (cleaned, cleaned.lower()),
        )
        if not rows:
            raise AppError(
                code="TEMPLATE_NOT_FOUND",
                message=f"Meme template '{identifier}' was not found.",
                status_code=404,
            )
        return _row_to_dict(TEMPLATE_COLUMNS, rows[0])

    async def render_template_preview_bytes(self, slug: str) -> Tuple[bytes, str]:
        tmpl = await self.get_template_by_id_or_slug(slug)
        raw_regions = json.loads(str(tmpl.get("text_regions") or "[]"))
        specs = [
            TextRegionSpec(
                region_id=r["id"],
                label=r["label"],
                x=int(r["x"]),
                y=int(r["y"]),
                width=int(r["width"]),
                height=int(r["height"]),
                align=r.get("align", "center"),
                max_chars=int(r.get("max_chars", 160)),
                default_font_size=int(r.get("default_font_size", 36)),
                min_font_size=int(r.get("min_font_size", 18)),
            )
            for r in raw_regions
        ]
        sample_captions = [
            RenderCaptionInput(region_id=s.region_id, text=s.label.upper())
            for s in specs[:2]
        ]
        rendered = self.renderer.render_meme(
            template_slug=str(tmpl["slug"]),
            width=int(tmpl["width"]),
            height=int(tmpl["height"]),
            regions=specs,
            captions=sample_captions,
            language_tag="en",
            output_format="PNG",
        )
        return rendered.image_bytes, rendered.mime_type

    async def render_template_meme(
        self,
        *,
        user_id: str,
        payload: RenderTemplateRequest,
    ) -> MemeAssetResponse:
        """Render a template meme synchronously without requiring any external AI provider."""
        tmpl = await self.get_template_by_id_or_slug(payload.template_id_or_slug)
        lang = validate_bcp47_tag(payload.language)

        non_empty_captions = [
            c for c in payload.captions if normalize_unicode_nfc(c.text).strip()
        ]
        if not non_empty_captions:
            raise AppError(
                code="EMPTY_MEME_CAPTIONS",
                message="Please enter text in at least one caption region before rendering.",
                status_code=422,
            )

        raw_regions = json.loads(str(tmpl.get("text_regions") or "[]"))
        specs = [
            TextRegionSpec(
                region_id=r["id"],
                label=r["label"],
                x=int(r["x"]),
                y=int(r["y"]),
                width=int(r["width"]),
                height=int(r["height"]),
                align=r.get("align", "center"),
                max_chars=int(r.get("max_chars", 160)),
                default_font_size=int(r.get("default_font_size", 36)),
                min_font_size=int(r.get("min_font_size", 18)),
            )
            for r in raw_regions
        ]
        render_inputs = [
            RenderCaptionInput(
                region_id=c.region_id,
                text=c.text,
                align=c.align,
                font_size_override=c.font_size_override,
                text_color=c.text_color,
                stroke_color=c.stroke_color,
            )
            for c in non_empty_captions
        ]

        rendered = self.renderer.render_meme(
            template_slug=str(tmpl["slug"]),
            width=int(tmpl["width"]),
            height=int(tmpl["height"]),
            regions=specs,
            captions=render_inputs,
            language_tag=lang,
            output_format=payload.output_format,
        )

        asset_id = str(uuid.uuid4())
        stored = self.storage.validate_and_store(
            raw_bytes=rendered.image_bytes,
            expected_mime_type=rendered.mime_type,
            storage_prefix="memes",
            asset_id=asset_id,
        )

        # Auto-derive accessible alt_text if user did not supply one
        if payload.alt_text and payload.alt_text.strip():
            alt_text = normalize_unicode_nfc(payload.alt_text).strip()[:500]
        else:
            joined = " / ".join(normalize_unicode_nfc(c.text).strip() for c in non_empty_captions)
            alt_text = f"{tmpl['name']} meme: {joined}"[:500]

        now_str = _now_iso()
        expires_str = (_now_utc() + timedelta(days=7)).isoformat()
        captions_json = json.dumps(
            [{"region_id": c.region_id, "text": normalize_unicode_nfc(c.text).strip()} for c in non_empty_captions],
            ensure_ascii=False,
        )

        await self.session.execute(
            """
            INSERT INTO meme_assets (
                id, owner_user_id, source_type, template_id, storage_key,
                mime_type, file_size_bytes, sha256_hash, width, height,
                captions_json, caption_language, alt_text, safety_status,
                is_published, expires_at, created_at
            ) VALUES (?, ?, 'template_render', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'approved', 0, ?, ?)
            """,
            (
                asset_id,
                user_id,
                str(tmpl["id"]),
                stored.storage_key,
                stored.mime_type,
                stored.file_size_bytes,
                stored.sha256_hash,
                stored.width,
                stored.height,
                captions_json,
                lang,
                alt_text,
                expires_str,
                now_str,
            ),
        )

        rows = await self.session.execute(
            f"SELECT {', '.join(ASSET_COLUMNS)} FROM meme_assets WHERE id = ?",
            (asset_id,),
        )
        return self._serialize_asset(_row_to_dict(ASSET_COLUMNS, rows[0]))

    async def _check_global_daily_spend_cap(self) -> None:
        today_prefix = _today_prefix_utc()
        rows = await self.session.execute(
            """
            SELECT COALESCE(SUM(estimated_cost_micros), 0)
            FROM ai_provider_usage
            WHERE created_at LIKE ? AND succeeded = 1
            """,
            (f"{today_prefix}%",),
        )
        total_micros = int(rows[0][0]) if rows else 0
        cap_micros = int(self.settings.ai_daily_spend_cap_usd * 1_000_000)
        if total_micros >= cap_micros:
            raise AppError(
                code="AI_DAILY_SPEND_CAP_REACHED",
                message="The platform's daily AI generation budget has been reached. Template meme creation remains available.",
                status_code=503,
            )

    async def _count_user_daily_usage(self, user_id: str, job_type: str) -> int:
        today_prefix = _today_prefix_utc()
        rows = await self.session.execute(
            """
            SELECT COUNT(1)
            FROM meme_jobs
            WHERE user_id = ?
              AND job_type = ?
              AND status != 'cancelled'
              AND created_at LIKE ?
            """,
            (user_id, job_type, f"{today_prefix}%"),
        )
        return int(rows[0][0]) if rows else 0

    async def suggest_captions(
        self,
        *,
        user_id: str,
        payload: SuggestCaptionsRequest,
    ) -> SuggestCaptionsResponse:
        """Sanitize prompt, enforce daily caption quota & spend cap, and return suggestions."""
        sanitized_prompt, pii_redactions = sanitize_and_validate_meme_prompt(
            payload.prompt, max_chars=self.settings.meme_max_prompt_chars
        )
        tone = validate_meme_tone(payload.tone)
        lang = validate_bcp47_tag(payload.language)

        await self._check_global_daily_spend_cap()

        used_today = await self._count_user_daily_usage(user_id, "ai_caption")
        limit = self.settings.meme_caption_daily_limit
        if used_today >= limit:
            raise AppError(
                code="MEME_QUOTA_EXCEEDED",
                message=f"You have reached your daily limit of {limit} AI caption requests. You can still write captions manually.",
                status_code=429,
            )

        start_ts = time.perf_counter()
        result = await self.caption_adapter.generate_captions(
            CaptionRequest(
                sanitized_prompt=sanitized_prompt,
                tone=tone,
                language_tag=lang,
                template_slug=payload.template_slug or "friday-455pm-deploy",
                max_suggestions=payload.max_suggestions,
            )
        )
        latency_ms = max(1, int((time.perf_counter() - start_ts) * 1000))

        job_id = str(uuid.uuid4())
        now_str = _now_iso()
        suggestions_list = [
            CaptionSuggestionItem(
                top_text=c.top_text,
                bottom_text=c.bottom_text,
                tone=c.tone,
                language=c.language_tag,
            )
            for c in result.candidates
        ]
        suggestions_json = json.dumps(
            [s.dict() for s in suggestions_list], ensure_ascii=False
        )

        await self.session.execute(
            """
            INSERT INTO meme_jobs (
                id, user_id, idempotency_key, job_type, template_id,
                user_prompt, prompt_language, style_tone, options_json,
                status, attempt_count, provider_name, model_version,
                is_mock_provider, caption_suggestions, result_asset_id,
                error_code, error_message_safe, estimated_cost_micros,
                created_at, updated_at, started_at, completed_at
            ) VALUES (?, ?, ?, 'ai_caption', NULL, ?, ?, ?, '{}', 'ready', 1, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                user_id,
                str(uuid.uuid4()),
                sanitized_prompt,
                lang,
                tone,
                result.provider_name,
                result.model_name,
                1 if result.is_mock else 0,
                suggestions_json,
                result.estimated_cost_micros,
                now_str,
                now_str,
                now_str,
                now_str,
            ),
        )

        await self.session.execute(
            """
            INSERT INTO ai_provider_usage (
                id, user_id, meme_job_id, operation_type, provider_name,
                model_name, is_mock, input_units, output_units,
                estimated_cost_micros, currency, latency_ms, succeeded, created_at
            ) VALUES (?, ?, ?, 'ai_caption', ?, ?, ?, ?, ?, ?, 'USD', ?, 1, ?)
            """,
            (
                str(uuid.uuid4()),
                user_id,
                job_id,
                result.provider_name,
                result.model_name,
                1 if result.is_mock else 0,
                result.input_tokens,
                result.output_tokens,
                result.estimated_cost_micros,
                latency_ms,
                now_str,
            ),
        )

        remaining = max(0, limit - (used_today + 1))
        return SuggestCaptionsResponse(
            suggestions=suggestions_list,
            sanitized_prompt=sanitized_prompt,
            pii_redactions=pii_redactions,
            provider_name=result.provider_name,
            model_name=result.model_name,
            is_mock_provider=result.is_mock,
            quota_remaining=remaining,
            daily_limit=limit,
        )

    async def _build_job_response(
        self, row_dict: dict[str, Any], *, quota_remaining: Optional[int] = None
    ) -> MemeJobResponse:
        asset_resp: Optional[MemeAssetResponse] = None
        res_asset_id = row_dict.get("result_asset_id")
        if res_asset_id:
            a_rows = await self.session.execute(
                f"SELECT {', '.join(ASSET_COLUMNS)} FROM meme_assets WHERE id = ?",
                (str(res_asset_id),),
            )
            if a_rows:
                asset_resp = self._serialize_asset(_row_to_dict(ASSET_COLUMNS, a_rows[0]))

        return MemeJobResponse(
            id=str(row_dict["id"]),
            job_type=str(row_dict["job_type"]),
            status=str(row_dict["status"]),
            prompt=str(row_dict.get("user_prompt") or ""),
            prompt_language=str(row_dict.get("prompt_language") or "en"),
            style_tone=str(row_dict.get("style_tone") or "sarcastic"),
            attempt_count=int(row_dict.get("attempt_count", 0)),
            provider_name=row_dict.get("provider_name"),
            model_version=row_dict.get("model_version"),
            is_mock_provider=bool(row_dict.get("is_mock_provider")),
            result_asset=asset_resp,
            error_code=row_dict.get("error_code"),
            error_message_safe=row_dict.get("error_message_safe"),
            quota_remaining=quota_remaining,
            created_at=str(row_dict["created_at"]),
            updated_at=str(row_dict["updated_at"]),
            started_at=row_dict.get("started_at"),
            completed_at=row_dict.get("completed_at"),
        )

    async def create_image_job(
        self,
        *,
        user_id: str,
        payload: CreateMemeJobRequest,
        header_idempotency_key: Optional[str] = None,
    ) -> Tuple[MemeJobResponse, bool]:
        """Enqueue an asynchronous AI image generation job with idempotency & quota enforcement.

        Returns `(MemeJobResponse, is_newly_created)`.
        """
        job_type = payload.job_type.strip().lower()
        if job_type not in {"ai_image", "template_render"}:
            raise AppError(
                code="INVALID_JOB_TYPE",
                message="job_type must be 'ai_image' or 'template_render'.",
                status_code=422,
            )

        idem_key = (header_idempotency_key or payload.idempotency_key or "").strip()
        if idem_key:
            existing_rows = await self.session.execute(
                f"SELECT {', '.join(JOB_COLUMNS)} FROM meme_jobs WHERE user_id = ? AND idempotency_key = ?",
                (user_id, idem_key),
            )
            if existing_rows:
                existing_dict = _row_to_dict(JOB_COLUMNS, existing_rows[0])
                return await self._build_job_response(existing_dict), False
        else:
            idem_key = str(uuid.uuid4())

        if job_type == "ai_image" and (self.settings.ai_image_provider or "disabled").strip().lower() == "disabled":
            raise AppError(
                code="AI_PROVIDER_UNAVAILABLE",
                message="AI Image Generation is currently disabled. Template-based meme creation remains available.",
                status_code=503,
            )

        sanitized_prompt, _ = sanitize_and_validate_meme_prompt(
            payload.prompt, max_chars=self.settings.meme_max_prompt_chars
        )
        tone = validate_meme_tone(payload.style_tone)
        lang = validate_bcp47_tag(payload.language)

        await self._check_global_daily_spend_cap()

        # Check concurrent active jobs per user
        active_rows = await self.session.execute(
            """
            SELECT COUNT(1)
            FROM meme_jobs
            WHERE user_id = ?
              AND job_type = 'ai_image'
              AND status IN ('queued', 'generating', 'validating')
            """,
            (user_id,),
        )
        active_count = int(active_rows[0][0]) if active_rows else 0
        if active_count >= self.settings.meme_max_concurrent_jobs:
            raise AppError(
                code="CONCURRENT_JOB_LIMIT_EXCEEDED",
                message="You already have an AI meme generation job in progress. Please wait for it to finish or cancel it first.",
                status_code=429,
            )

        # Check daily AI image quota per user
        used_today = await self._count_user_daily_usage(user_id, "ai_image")
        daily_limit = self.settings.meme_image_daily_limit
        if used_today >= daily_limit:
            raise AppError(
                code="MEME_QUOTA_EXCEEDED",
                message=f"You have reached your daily limit of {daily_limit} AI image generation jobs.",
                status_code=429,
            )

        job_id = str(uuid.uuid4())
        now_str = _now_iso()
        options_json = json.dumps(
            {
                "captions": [c.dict() for c in payload.captions],
                "alt_text": payload.alt_text,
            },
            ensure_ascii=False,
        )

        await self.session.execute(
            """
            INSERT INTO meme_jobs (
                id, user_id, idempotency_key, job_type, template_id,
                user_prompt, prompt_language, style_tone, options_json,
                status, attempt_count, provider_name, model_version,
                is_mock_provider, caption_suggestions, result_asset_id,
                error_code, error_message_safe, estimated_cost_micros,
                created_at, updated_at, started_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 0, NULL, NULL, 0, NULL, NULL, NULL, NULL, 0, ?, ?, NULL, NULL)
            """,
            (
                job_id,
                user_id,
                idem_key,
                job_type,
                payload.template_id,
                sanitized_prompt,
                lang,
                tone,
                options_json,
                now_str,
                now_str,
            ),
        )

        rows = await self.session.execute(
            f"SELECT {', '.join(JOB_COLUMNS)} FROM meme_jobs WHERE id = ?",
            (job_id,),
        )
        remaining = max(0, daily_limit - (used_today + 1))
        return await self._build_job_response(
            _row_to_dict(JOB_COLUMNS, rows[0]), quota_remaining=remaining
        ), True

    async def get_job_status(
        self, *, job_id: str, actor_user: dict[str, Any]
    ) -> MemeJobResponse:
        rows = await self.session.execute(
            f"SELECT {', '.join(JOB_COLUMNS)} FROM meme_jobs WHERE id = ?",
            (job_id,),
        )
        if not rows:
            raise AppError(
                code="JOB_NOT_FOUND",
                message="The requested meme generation job was not found.",
                status_code=404,
            )
        job_dict = _row_to_dict(JOB_COLUMNS, rows[0])
        is_owner = str(job_dict["user_id"]) == str(actor_user["id"])
        is_admin = str(actor_user.get("role", "member")) == "admin"
        if not (is_owner or is_admin):
            raise AppError(
                code="FORBIDDEN_JOB_ACCESS",
                message="You are only permitted to inspect your own meme generation jobs.",
                status_code=403,
            )
        return await self._build_job_response(job_dict)

    async def cancel_job(
        self, *, job_id: str, actor_user: dict[str, Any]
    ) -> MemeJobResponse:
        rows = await self.session.execute(
            f"SELECT {', '.join(JOB_COLUMNS)} FROM meme_jobs WHERE id = ?",
            (job_id,),
        )
        if not rows:
            raise AppError(
                code="JOB_NOT_FOUND",
                message="The requested meme generation job was not found.",
                status_code=404,
            )
        job_dict = _row_to_dict(JOB_COLUMNS, rows[0])
        if str(job_dict["user_id"]) != str(actor_user["id"]):
            raise AppError(
                code="FORBIDDEN_JOB_ACCESS",
                message="You are only permitted to cancel your own meme generation jobs.",
                status_code=403,
            )
        if str(job_dict["status"]) != "queued":
            raise AppError(
                code="JOB_NOT_CANCELLABLE",
                message=f"Job in status '{job_dict['status']}' can no longer be cancelled.",
                status_code=409,
            )

        now_str = _now_iso()
        await self.session.execute(
            """
            UPDATE meme_jobs
            SET status = 'cancelled', updated_at = ?, completed_at = ?
            WHERE id = ? AND status = 'queued'
            """,
            (now_str, now_str, job_id),
        )
        updated = await self.session.execute(
            f"SELECT {', '.join(JOB_COLUMNS)} FROM meme_jobs WHERE id = ?",
            (job_id,),
        )
        return await self._build_job_response(_row_to_dict(JOB_COLUMNS, updated[0]))

    async def get_asset_for_download(
        self, *, asset_id: str, viewer_user: Optional[dict[str, Any]] = None
    ) -> Tuple[MemeAssetResponse, bytes]:
        rows = await self.session.execute(
            f"SELECT {', '.join(ASSET_COLUMNS)} FROM meme_assets WHERE id = ?",
            (asset_id,),
        )
        if not rows:
            raise AppError(
                code="MEME_ASSET_NOT_FOUND",
                message="The requested meme asset was not found.",
                status_code=404,
            )
        asset_dict = _row_to_dict(ASSET_COLUMNS, rows[0])
        if str(asset_dict["safety_status"]) != "approved":
            raise AppError(
                code="MEME_ASSET_RESTRICTED",
                message="This meme asset is not available for download.",
                status_code=403,
            )

        # Unpublished drafts can only be downloaded by their owner
        if not bool(asset_dict.get("is_published")):
            viewer_id = str(viewer_user["id"]) if viewer_user else None
            if viewer_id != str(asset_dict.get("owner_user_id")):
                raise AppError(
                    code="FORBIDDEN_ASSET_ACCESS",
                    message="Unpublished draft meme assets can only be accessed by their creator.",
                    status_code=403,
                )

        raw_bytes = self.storage.read_bytes(str(asset_dict["storage_key"]))
        return self._serialize_asset(asset_dict), raw_bytes

    async def cleanup_expired_unpublished_assets(self) -> int:
        """Delete unpublished draft assets whose `expires_at` timestamp has passed."""
        now_str = _now_iso()
        rows = await self.session.execute(
            """
            SELECT id, storage_key
            FROM meme_assets
            WHERE is_published = 0
              AND expires_at IS NOT NULL
              AND expires_at < ?
            """,
            (now_str,),
        )
        deleted_count = 0
        for asset_id, storage_key in rows:
            self.storage.delete_object(str(storage_key))
            await self.session.execute(
                "DELETE FROM meme_assets WHERE id = ? AND is_published = 0",
                (str(asset_id),),
            )
            deleted_count += 1
        return deleted_count

    async def upload_custom_meme_asset(
        self,
        *,
        user_id: str,
        raw_bytes: bytes,
        declared_mime_type: str,
        alt_text: Optional[str] = None,
        language: str = "en",
    ) -> MemeAssetResponse:
        """Validate, sanitize, and store a multipart-uploaded meme image asset atomically."""
        lang = validate_bcp47_tag(language or "en")
        asset_id = str(uuid.uuid4())
        stored = self.storage.validate_and_store(
            raw_bytes=raw_bytes,
            expected_mime_type=(declared_mime_type or "image/png").strip().lower(),
            storage_prefix="memes",
            asset_id=asset_id,
        )

        resolved_alt = (
            normalize_unicode_nfc(alt_text).strip()[:500]
            if alt_text and alt_text.strip()
            else "Uploaded workplace meme image"
        )
        now_str = _now_iso()
        expires_str = (_now_utc() + timedelta(days=7)).isoformat()

        try:
            await self.session.execute(
                """
                INSERT INTO meme_assets (
                    id, owner_user_id, source_type, template_id, storage_key,
                    mime_type, file_size_bytes, sha256_hash, width, height,
                    captions_json, caption_language, alt_text, safety_status,
                    is_published, expires_at, created_at
                ) VALUES (?, ?, 'remix', NULL, ?, ?, ?, ?, ?, ?, '[]', ?, ?, 'approved', 0, ?, ?)
                """,
                (
                    asset_id,
                    user_id,
                    stored.storage_key,
                    stored.mime_type,
                    stored.file_size_bytes,
                    stored.sha256_hash,
                    stored.width,
                    stored.height,
                    lang,
                    resolved_alt,
                    expires_str,
                    now_str,
                ),
            )
        except Exception:
            # Ensure failed DB writes never leave orphaned files in storage
            self.storage.delete_object(stored.storage_key)
            raise

        rows = await self.session.execute(
            f"SELECT {', '.join(ASSET_COLUMNS)} FROM meme_assets WHERE id = ?",
            (asset_id,),
        )
        return self._serialize_asset(_row_to_dict(ASSET_COLUMNS, rows[0]))

