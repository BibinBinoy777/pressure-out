"""Background worker for asynchronous Phase 8 AI Meme Studio image jobs.

Responsibilities:
- Claim `queued` jobs atomically (`queued -> generating -> validating -> ready | failed`)
- Enforce bounded retries (`max_retries = settings.meme_job_max_retries`, default 1 retry / 2 attempts total)
- Never retry non-retryable validation or safety errors
- Render optional caption overlays onto generated images via `TemplateRenderer`
- Validate and store image bytes via `StorageAdapter`
- Record provider cost and latency in `ai_provider_usage`
- Create an in-app `meme_job_ready` notification for the job owner
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.config import Settings, get_settings
from app.core.errors import AppError
from app.core.unicode import normalize_unicode_nfc
from app.modules.memes.adapters.base import ImageGenRequest, ImageProviderAdapter
from app.modules.memes.adapters.http_provider import resolve_image_adapter
from app.modules.memes.service import JOB_COLUMNS, _row_to_dict
from app.modules.memes.storage import LocalFilesystemStorageAdapter, StorageAdapter, create_storage_adapter
from app.modules.memes.template_renderer import (
    RenderCaptionInput,
    TemplateRenderer,
    TextRegionSpec,
)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now_utc().isoformat()


DEFAULT_AI_IMAGE_REGIONS = (
    TextRegionSpec(
        region_id="top",
        label="Top Caption",
        x=40,
        y=28,
        width=720,
        height=160,
        align="center",
        max_chars=160,
        default_font_size=34,
        min_font_size=18,
    ),
    TextRegionSpec(
        region_id="bottom",
        label="Bottom Caption",
        x=40,
        y=612,
        width=720,
        height=160,
        align="center",
        max_chars=160,
        default_font_size=34,
        min_font_size=18,
    ),
)


class MemeJobWorker:
    """Processes queued AI meme generation jobs safely and deterministically."""

    def __init__(
        self,
        session: Any,
        settings: Optional[Settings] = None,
        storage: Optional[StorageAdapter] = None,
        image_adapter: Optional[ImageProviderAdapter] = None,
        renderer: Optional[TemplateRenderer] = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.storage: StorageAdapter = storage or create_storage_adapter(self.settings)
        self.image_adapter: ImageProviderAdapter = image_adapter or resolve_image_adapter(
            self.settings
        )
        self.renderer = renderer or TemplateRenderer()

    async def claim_next_queued_job(self) -> Optional[dict[str, Any]]:
        """Atomically claim the oldest `queued` job and transition it to `generating`."""
        rows = await self.session.execute(
            f"""
            SELECT {', '.join(JOB_COLUMNS)}
            FROM meme_jobs
            WHERE status = 'queued'
            ORDER BY created_at ASC
            LIMIT 1
            """
        )
        if not rows:
            return None
        job = _row_to_dict(JOB_COLUMNS, rows[0])
        job_id = str(job["id"])
        now_str = _now_iso()
        new_attempt = int(job.get("attempt_count", 0)) + 1

        await self.session.execute(
            """
            UPDATE meme_jobs
            SET status = 'generating',
                attempt_count = ?,
                started_at = COALESCE(started_at, ?),
                updated_at = ?
            WHERE id = ? AND status = 'queued'
            """,
            (new_attempt, now_str, now_str, job_id),
        )
        verify_rows = await self.session.execute(
            f"SELECT {', '.join(JOB_COLUMNS)} FROM meme_jobs WHERE id = ?",
            (job_id,),
        )
        if not verify_rows:
            return None
        claimed = _row_to_dict(JOB_COLUMNS, verify_rows[0])
        if str(claimed["status"]) != "generating":
            return None
        return claimed

    async def process_single_job(self, job_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Claim and execute a single queued job (or specific `job_id` if queued)."""
        if job_id:
            rows = await self.session.execute(
                f"SELECT {', '.join(JOB_COLUMNS)} FROM meme_jobs WHERE id = ? AND status = 'queued'",
                (job_id,),
            )
            if not rows:
                return None
            job = _row_to_dict(JOB_COLUMNS, rows[0])
            now_str = _now_iso()
            new_attempt = int(job.get("attempt_count", 0)) + 1
            await self.session.execute(
                """
                UPDATE meme_jobs
                SET status = 'generating',
                    attempt_count = ?,
                    started_at = COALESCE(started_at, ?),
                    updated_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (new_attempt, now_str, now_str, job_id),
            )
            refreshed = await self.session.execute(
                f"SELECT {', '.join(JOB_COLUMNS)} FROM meme_jobs WHERE id = ?",
                (job_id,),
            )
            claimed = _row_to_dict(JOB_COLUMNS, refreshed[0])
        else:
            claimed = await self.claim_next_queued_job()
            if claimed is None:
                return None

        target_id = str(claimed["id"])
        user_id = str(claimed["user_id"])
        attempt_count = int(claimed["attempt_count"])
        max_attempts = 1 + max(0, int(self.settings.meme_job_max_retries))

        start_ts = time.perf_counter()
        try:
            gen_res = await self.image_adapter.generate_image(
                ImageGenRequest(
                    job_id=target_id,
                    sanitized_prompt=str(claimed.get("user_prompt") or ""),
                    style_tone=str(claimed.get("style_tone") or "sarcastic"),
                    language_tag=str(claimed.get("prompt_language") or "en"),
                    width=800,
                    height=800,
                )
            )
            latency_ms = max(1, int((time.perf_counter() - start_ts) * 1000))

            # Transition to `validating`
            await self.session.execute(
                "UPDATE meme_jobs SET status = 'validating', updated_at = ? WHERE id = ?",
                (_now_iso(), target_id),
            )

            options = json.loads(str(claimed.get("options_json") or "{}"))
            raw_captions = options.get("captions") or []
            non_empty_caps = [
                RenderCaptionInput(
                    region_id=str(c.get("region_id", "top")),
                    text=str(c.get("text", "")),
                    align=c.get("align"),
                )
                for c in raw_captions
                if str(c.get("text", "")).strip()
            ]

            final_bytes = gen_res.image_bytes
            final_mime = gen_res.mime_type
            if non_empty_caps:
                rendered_overlay = self.renderer.render_meme(
                    template_slug="ai-generated",
                    width=800,
                    height=800,
                    regions=DEFAULT_AI_IMAGE_REGIONS,
                    captions=non_empty_caps,
                    language_tag=str(claimed.get("prompt_language") or "en"),
                    output_format="PNG",
                    base_image_bytes=gen_res.image_bytes,
                )
                final_bytes = rendered_overlay.image_bytes
                final_mime = rendered_overlay.mime_type

            asset_id = str(uuid.uuid4())
            stored = self.storage.validate_and_store(
                raw_bytes=final_bytes,
                expected_mime_type=final_mime,
                storage_prefix="memes",
                asset_id=asset_id,
            )

            alt_text = str(options.get("alt_text") or "").strip()
            if not alt_text:
                alt_text = f"AI workplace meme ({claimed.get('style_tone')}): {claimed.get('user_prompt')}"[:500]
            else:
                alt_text = normalize_unicode_nfc(alt_text)[:500]

            now_str = _now_iso()
            expires_str = (_now_utc() + timedelta(days=7)).isoformat()
            await self.session.execute(
                """
                INSERT INTO meme_assets (
                    id, owner_user_id, source_type, template_id, storage_key,
                    mime_type, file_size_bytes, sha256_hash, width, height,
                    captions_json, caption_language, alt_text, safety_status,
                    is_published, expires_at, created_at
                ) VALUES (?, ?, 'ai_generated', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'approved', 0, ?, ?)
                """,
                (
                    asset_id,
                    user_id,
                    claimed.get("template_id"),
                    stored.storage_key,
                    stored.mime_type,
                    stored.file_size_bytes,
                    stored.sha256_hash,
                    stored.width,
                    stored.height,
                    json.dumps(raw_captions, ensure_ascii=False),
                    str(claimed.get("prompt_language") or "en"),
                    alt_text,
                    expires_str,
                    now_str,
                ),
            )

            await self.session.execute(
                """
                INSERT INTO ai_provider_usage (
                    id, user_id, meme_job_id, operation_type, provider_name,
                    model_name, is_mock, input_units, output_units,
                    estimated_cost_micros, currency, latency_ms, succeeded, created_at
                ) VALUES (?, ?, ?, 'ai_image', ?, ?, ?, 1, 1, ?, 'USD', ?, 1, ?)
                """,
                (
                    str(uuid.uuid4()),
                    user_id,
                    target_id,
                    gen_res.provider_name,
                    gen_res.model_name,
                    1 if gen_res.is_mock else 0,
                    gen_res.estimated_cost_micros,
                    latency_ms,
                    now_str,
                ),
            )

            await self.session.execute(
                """
                UPDATE meme_jobs
                SET status = 'ready',
                    provider_name = ?,
                    model_version = ?,
                    is_mock_provider = ?,
                    result_asset_id = ?,
                    estimated_cost_micros = ?,
                    error_code = NULL,
                    error_message_safe = NULL,
                    updated_at = ?,
                    completed_at = ?
                WHERE id = ?
                """,
                (
                    gen_res.provider_name,
                    gen_res.model_name,
                    1 if gen_res.is_mock else 0,
                    asset_id,
                    gen_res.estimated_cost_micros,
                    now_str,
                    now_str,
                    target_id,
                ),
            )

            # Notify the job creator via in-app notification
            await self.session.execute(
                """
                INSERT INTO notifications (
                    id, recipient_user_id, notification_type, reference_type,
                    reference_id, title, body_preview, is_read, created_at
                ) VALUES (?, ?, 'meme_job_ready', 'meme_job', ?, ?, ?, 0, ?)
                """,
                (
                    str(uuid.uuid4()),
                    user_id,
                    target_id,
                    "Your AI workplace meme is ready!",
                    str(claimed.get("user_prompt") or "")[:120],
                    now_str,
                ),
            )
        except Exception as exc:
            latency_ms = max(1, int((time.perf_counter() - start_ts) * 1000))
            now_str = _now_iso()
            if isinstance(exc, AppError):
                err_code = exc.code
                err_msg = exc.message[:250]
                is_retryable = exc.status_code in {502, 503, 504} and err_code != "AI_PROVIDER_UNAVAILABLE"
            else:
                err_code = "PROVIDER_EXECUTION_ERROR"
                err_msg = "Temporary error while generating the meme image."
                is_retryable = True

            await self.session.execute(
                """
                INSERT INTO ai_provider_usage (
                    id, user_id, meme_job_id, operation_type, provider_name,
                    model_name, is_mock, input_units, output_units,
                    estimated_cost_micros, currency, latency_ms, succeeded, created_at
                ) VALUES (?, ?, ?, 'ai_image', 'error', 'error', 1, 1, 0, 0, 'USD', ?, 0, ?)
                """,
                (str(uuid.uuid4()), user_id, target_id, latency_ms, now_str),
            )

            if is_retryable and attempt_count < max_attempts:
                await self.session.execute(
                    """
                    UPDATE meme_jobs
                    SET status = 'queued',
                        error_code = ?,
                        error_message_safe = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (err_code, err_msg, now_str, target_id),
                )
            else:
                await self.session.execute(
                    """
                    UPDATE meme_jobs
                    SET status = 'failed',
                        error_code = ?,
                        error_message_safe = ?,
                        updated_at = ?,
                        completed_at = ?
                    WHERE id = ?
                    """,
                    (err_code, err_msg, now_str, now_str, target_id),
                )

        final_rows = await self.session.execute(
            f"SELECT {', '.join(JOB_COLUMNS)} FROM meme_jobs WHERE id = ?",
            (target_id,),
        )
        return _row_to_dict(JOB_COLUMNS, final_rows[0]) if final_rows else None

    async def recover_stale_generating_jobs(self) -> int:
        """Recover jobs left in 'generating' or 'validating' after an unexpected worker restart.

        Jobs within retry bounds (`attempt_count <= meme_job_max_retries`) are returned to `queued`;
        jobs that already exhausted retries are marked `failed` (`WORKER_INTERRUPTED`).
        """
        rows = await self.session.execute(
            """
            SELECT id, attempt_count
            FROM meme_jobs
            WHERE status IN ('generating', 'validating')
            """
        )
        if not rows:
            return 0
        max_attempts = 1 + max(0, int(self.settings.meme_job_max_retries))
        now_str = _now_iso()
        recovered = 0
        for job_id, attempts in rows:
            if int(attempts) < max_attempts:
                await self.session.execute(
                    """
                    UPDATE meme_jobs
                    SET status = 'queued',
                        error_code = 'WORKER_RESTART_REQUEUED',
                        error_message_safe = 'Job re-queued after worker restart.',
                        updated_at = ?
                    WHERE id = ? AND status IN ('generating', 'validating')
                    """,
                    (now_str, str(job_id)),
                )
            else:
                await self.session.execute(
                    """
                    UPDATE meme_jobs
                    SET status = 'failed',
                        error_code = 'WORKER_INTERRUPTED',
                        error_message_safe = 'Job interrupted during worker restart after maximum retries.',
                        updated_at = ?,
                        completed_at = ?
                    WHERE id = ? AND status IN ('generating', 'validating')
                    """,
                    (now_str, now_str, str(job_id)),
                )
            recovered += 1
        return recovered
