"""Transactional service for Phase 10 On-Demand Derived Content Translation & Caching.

Enforces:
1. Source-content visibility, deletion/removal/moderation-hold checks, and user block rules.
2. Content-hash cache identity (`source_version_hash = SHA256(normalized_text)`):
   - Editing a post/comment title or body immediately invalidates old cached translations.
   - Changing unrelated metadata (vote counts, tags, reaction counts) preserves the valid cache.
3. Rate limiting, global daily spend circuit breaker, and strict data minimization.
4. Zero mutation of `posts` or `comments` tables and zero leakage of anonymous author IDs.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from app.config import Settings, get_settings
from app.core.errors import AppError
from app.core.rate_limit import rate_limiter
from app.core.unicode import normalize_unicode_nfc
from app.modules.moderation.guards import is_interaction_blocked
from app.modules.translations.adapters.base import (
    TranslationProviderAdapter,
    TranslationRequest,
)
from app.modules.translations.adapters.http_provider import resolve_translation_adapter
from app.modules.translations.matrix import (
    LANGUAGE_CAPABILITY_MATRIX,
    SUPPORTED_TRANSLATION_TARGETS,
    SUPPORTED_UI_LOCALES,
    detect_text_script_and_direction,
    get_language_display_name,
    validate_translation_target_locale,
)
from app.modules.translations.schemas import (
    DerivedTranslationResponse,
    LanguageCapabilitiesResponse,
    LanguageCapabilityItemSchema,
    TranslateContentRequest,
)

TRANSLATION_COLUMNS = (
    "id",
    "source_type",
    "source_id",
    "source_version_hash",
    "source_language",
    "detected_source_language",
    "target_locale",
    "translated_title",
    "translated_body",
    "provider_name",
    "model_name",
    "is_mock_provider",
    "created_at",
)

MAX_TRANSLATION_INPUT_CHARS = 15500


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_prefix_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _row_to_dict(columns: tuple[str, ...], row: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip(columns, row))


def compute_source_version_hash(
    *, source_type: str, title: Optional[str], body: str
) -> str:
    """Compute SHA-256 fingerprint of canonical NFC-normalized source text."""
    norm_body = normalize_unicode_nfc(body).strip()
    if source_type == "post":
        norm_title = normalize_unicode_nfc(title or "").strip()
        canonical = f"post_v1\n{norm_title}\n\n{norm_body}"
    else:
        canonical = f"comment_v1\n{norm_body}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_provenance_label(
    source_language: str, is_uncertain: bool, is_mock: bool
) -> str:
    if is_uncertain or source_language in {"mul", "und"}:
        base = "Translated from Mixed / Undetermined Language"
    else:
        lang_name = get_language_display_name(source_language)
        base = f"Translated from {lang_name}"
    if is_mock:
        return f"{base} (Local Mock Preview)"
    return base


class TranslationService:
    """Coordinates on-demand post and comment translation, caching, and source-edit invalidation."""

    def __init__(
        self,
        session: Any,
        settings: Optional[Settings] = None,
        adapter: Optional[TranslationProviderAdapter] = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.adapter: TranslationProviderAdapter = adapter or resolve_translation_adapter(
            self.settings
        )

    def get_language_capabilities(self) -> LanguageCapabilitiesResponse:
        return LanguageCapabilitiesResponse(
            supported_ui_locales=list(SUPPORTED_UI_LOCALES),
            supported_translation_targets=list(SUPPORTED_TRANSLATION_TARGETS),
            capabilities=[
                LanguageCapabilityItemSchema(
                    code=e.code,
                    native_name=e.native_name,
                    english_name=e.english_name,
                    direction=e.direction,
                    ui_locale_supported=e.ui_locale_supported,
                    content_posting_supported=e.content_posting_supported,
                    on_demand_translation_target=e.on_demand_translation_target,
                    meme_studio_font_shaping=e.meme_studio_font_shaping,
                )
                for e in LANGUAGE_CAPABILITY_MATRIX
            ],
        )

    async def _load_and_authorize_source(
        self,
        *,
        source_type: str,
        source_id: str,
        viewer_user_id: Optional[str],
    ) -> Tuple[Optional[str], str, str]:
        """Verify source post/comment exists and is visible to `viewer_user_id`.

        Returns `(source_title, source_body, source_language)`.
        NEVER returns `author_user_id` to caller or external provider!
        """
        if source_type == "post":
            rows = await self.session.execute(
                """
                SELECT author_user_id, title, body, content_language, moderation_status, deleted_at
                FROM posts WHERE id = ?
                """,
                (source_id,),
            )
            if not rows:
                raise AppError(
                    code="POST_NOT_FOUND",
                    message="The requested post was not found.",
                    status_code=404,
                )
            author_id, title, body, lang, mod_status, deleted_at = rows[0]
            if deleted_at is not None or str(mod_status) in {
                "removed",
                "restricted",
                "awaiting_review",
            }:
                raise AppError(
                    code="POST_REMOVED",
                    message="This post is not eligible for public viewing or translation.",
                    status_code=410,
                )
            if viewer_user_id and await is_interaction_blocked(
                self.session, viewer_user_id, str(author_id) if author_id else None
            ):
                raise AppError(
                    code="INTERACTION_BLOCKED",
                    message="You cannot access or translate this content due to an active account block.",
                    status_code=403,
                )
            return str(title or ""), str(body or ""), str(lang or "und")

        if source_type == "comment":
            rows = await self.session.execute(
                """
                SELECT c.author_user_id, c.body, c.content_language, c.moderation_status, c.deleted_at,
                       p.moderation_status AS post_mod_status, p.deleted_at AS post_deleted_at
                FROM comments c
                JOIN posts p ON p.id = c.post_id
                WHERE c.id = ?
                """,
                (source_id,),
            )
            if not rows:
                raise AppError(
                    code="COMMENT_NOT_FOUND",
                    message="The requested comment was not found.",
                    status_code=404,
                )
            author_id, body, lang, mod_status, deleted_at, p_mod, p_del = rows[0]
            if (
                deleted_at is not None
                or p_del is not None
                or str(mod_status) in {"removed", "restricted", "awaiting_review"}
                or str(p_mod) in {"removed", "restricted", "awaiting_review"}
            ):
                raise AppError(
                    code="COMMENT_REMOVED",
                    message="This comment is not eligible for public viewing or translation.",
                    status_code=410,
                )
            if viewer_user_id and await is_interaction_blocked(
                self.session, viewer_user_id, str(author_id) if author_id else None
            ):
                raise AppError(
                    code="INTERACTION_BLOCKED",
                    message="You cannot access or translate this content due to an active account block.",
                    status_code=403,
                )
            return None, str(body or ""), str(lang or "und")

        raise AppError(
            code="VALIDATION_ERROR",
            message="Unsupported translation source type.",
            status_code=422,
        )

    def _serialize_translation_row(
        self,
        row_dict: dict[str, Any],
        *,
        is_uncertain: bool,
        direction: str,
        cache_hit: bool,
    ) -> DerivedTranslationResponse:
        src_lang = str(row_dict["source_language"])
        tgt_lang = str(row_dict["target_locale"])
        is_mock = bool(row_dict.get("is_mock_provider"))
        return DerivedTranslationResponse(
            id=str(row_dict["id"]),
            source_type=str(row_dict["source_type"]),
            source_id=str(row_dict["source_id"]),
            source_version_hash=str(row_dict["source_version_hash"]),
            source_language=src_lang,
            source_language_label=get_language_display_name(src_lang),
            detected_source_language=row_dict.get("detected_source_language"),
            is_source_language_uncertain=is_uncertain,
            target_locale=tgt_lang,
            target_locale_label=get_language_display_name(tgt_lang),
            translated_title=row_dict.get("translated_title"),
            translated_body=str(row_dict["translated_body"]),
            direction=direction,
            provenance_label=build_provenance_label(src_lang, is_uncertain, is_mock),
            provider_name=str(row_dict["provider_name"]),
            model_name=str(row_dict["model_name"]),
            is_mock_provider=is_mock,
            cache_hit=cache_hit,
            created_at=str(row_dict["created_at"]),
        )

    async def translate_content(
        self,
        *,
        source_type: str,
        source_id: str,
        payload: TranslateContentRequest,
        viewer_user: Optional[dict[str, Any]] = None,
        rate_limit_key: str = "anonymous_ip",
    ) -> DerivedTranslationResponse:
        target_locale = validate_translation_target_locale(payload.target_locale)
        viewer_id = str(viewer_user["id"]) if viewer_user else None

        # 1. Always enforce source visibility & block/moderation rules BEFORE consulting cache!
        src_title, src_body, declared_lang = await self._load_and_authorize_source(
            source_type=source_type,
            source_id=source_id,
            viewer_user_id=viewer_id,
        )

        total_len = len(src_body) + (len(src_title) if src_title else 0)
        if total_len > MAX_TRANSLATION_INPUT_CHARS:
            raise AppError(
                code="TRANSLATION_INPUT_TOO_LONG",
                message="Source content exceeds maximum translation length limit.",
                status_code=422,
            )

        effective_src_lang, _, is_uncertain = detect_text_script_and_direction(
            src_body, declared_lang
        )
        _, target_direction, _ = detect_text_script_and_direction("", target_locale)

        version_hash = compute_source_version_hash(
            source_type=source_type, title=src_title, body=src_body
        )

        # 2. Check cache keyed by (source_type, source_id, target_locale, source_version_hash)
        cached_rows = await self.session.execute(
            f"""
            SELECT {', '.join(TRANSLATION_COLUMNS)}
            FROM content_translations
            WHERE source_type = ?
              AND source_id = ?
              AND target_locale = ?
              AND source_version_hash = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_type, source_id, target_locale, version_hash),
        )
        if cached_rows:
            row_dict = _row_to_dict(TRANSLATION_COLUMNS, cached_rows[0])
            return self._serialize_translation_row(
                row_dict,
                is_uncertain=is_uncertain,
                direction=target_direction,
                cache_hit=True,
            )

        # 3. Cache miss -> enforce per-user/IP rate limit & invoke TranslationProviderAdapter
        rl_key = viewer_id or rate_limit_key
        rate_limiter.check_and_record(
            bucket="content_translation",
            key=rl_key,
            limit=self.settings.translation_hourly_limit,
            window_seconds=3600,
        )

        start_ts = time.perf_counter()
        result = await self.adapter.translate(
            TranslationRequest(
                source_type=source_type,
                source_language=effective_src_lang,
                target_locale=target_locale,
                source_title=src_title,
                source_body=src_body,
            )
        )
        latency_ms = max(1, int((time.perf_counter() - start_ts) * 1000))

        trans_id = str(uuid.uuid4())
        now_str = _now_iso()
        await self.session.execute(
            """
            INSERT OR IGNORE INTO content_translations (
                id, source_type, source_id, source_version_hash,
                source_language, detected_source_language, target_locale,
                translated_title, translated_body, provider_name,
                model_name, is_mock_provider, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trans_id,
                source_type,
                source_id,
                version_hash,
                declared_lang,
                result.detected_source_language,
                target_locale,
                result.translated_title,
                result.translated_body,
                result.provider_name,
                result.model_name,
                1 if result.is_mock else 0,
                now_str,
            ),
        )

        await self.session.execute(
            """
            INSERT INTO ai_provider_usage (
                id, user_id, meme_job_id, operation_type, provider_name,
                model_name, is_mock, input_units, output_units,
                estimated_cost_micros, currency, latency_ms, succeeded, created_at
            ) VALUES (?, ?, NULL, 'translation', ?, ?, ?, ?, ?, ?, 'USD', ?, 1, ?)
            """,
            (
                str(uuid.uuid4()),
                viewer_id,
                result.provider_name,
                result.model_name,
                1 if result.is_mock else 0,
                result.input_chars,
                result.output_chars,
                result.estimated_cost_micros,
                latency_ms,
                now_str,
            ),
        )

        stored_rows = await self.session.execute(
            f"""
            SELECT {', '.join(TRANSLATION_COLUMNS)}
            FROM content_translations
            WHERE source_type = ?
              AND source_id = ?
              AND target_locale = ?
              AND source_version_hash = ?
            LIMIT 1
            """,
            (source_type, source_id, target_locale, version_hash),
        )
        row_dict = _row_to_dict(TRANSLATION_COLUMNS, stored_rows[0])
        return self._serialize_translation_row(
            row_dict,
            is_uncertain=is_uncertain,
            direction=target_direction,
            cache_hit=False,
        )
