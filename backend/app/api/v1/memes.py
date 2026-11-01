"""FastAPI endpoints for Phase 8 AI Meme Studio and Phase 12.1 Multipart Upload (`/api/v1/memes`)."""
from __future__ import annotations

from email.parser import BytesParser
from email.policy import default as default_email_policy
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from app.api.deps import (
    get_meme_studio_service,
    get_optional_authenticated_context,
    require_authenticated_context,
)
from app.core.errors import AppError
from app.modules.memes.schemas import (
    CreateMemeJobRequest,
    MemeAssetResponse,
    MemeJobResponse,
    MemeTemplateListResponse,
    RenderTemplateRequest,
    SuggestCaptionsRequest,
    SuggestCaptionsResponse,
)
from app.modules.memes.service import MemeStudioService

router = APIRouter(prefix="/memes", tags=["memes"])


def _parse_multipart_upload(content_type: str, body: bytes) -> tuple[bytes, str, Optional[str], str]:
    """Parse RFC 7578 multipart/form-data payload into `(file_bytes, file_mime, alt_text, language)`."""
    if not content_type.lower().startswith("multipart/form-data") or "boundary=" not in content_type:
        raise AppError(
            code="INVALID_MULTIPART_UPLOAD",
            message="Expected multipart/form-data request with a valid boundary.",
            status_code=400,
        )
    raw_msg = (
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
        + body
    )
    msg = BytesParser(policy=default_email_policy).parsebytes(raw_msg)
    if not msg.is_multipart():
        raise AppError(
            code="INVALID_MULTIPART_UPLOAD",
            message="Multipart form payload could not be parsed.",
            status_code=400,
        )

    file_bytes: Optional[bytes] = None
    file_mime: str = "image/png"
    alt_text: Optional[str] = None
    language: str = "en"

    for part in msg.iter_parts():
        disp = part.get("Content-Disposition", "")
        name = part.get_param("name", header="content-disposition")
        filename = part.get_filename()
        payload_bytes = part.get_payload(decode=True) or b""
        if filename is not None or name == "file":
            file_bytes = payload_bytes
            file_mime = part.get_content_type() or "image/png"
        elif name == "alt_text":
            alt_text = payload_bytes.decode("utf-8", errors="replace").strip()
        elif name == "language":
            language = payload_bytes.decode("utf-8", errors="replace").strip() or "en"

    if file_bytes is None:
        raise AppError(
            code="MISSING_UPLOAD_FILE",
            message="Multipart upload must include a 'file' part.",
            status_code=422,
        )
    return file_bytes, file_mime, alt_text, language


@router.get("/templates", response_model=MemeTemplateListResponse)
async def list_meme_templates(
    category: Optional[str] = Query(None, description="Filter templates by category"),
    service: MemeStudioService = Depends(get_meme_studio_service),
) -> MemeTemplateListResponse:
    """Return curated, copyright-safe workplace meme templates and text regions."""
    return await service.list_templates(category=category)


@router.get("/templates/{slug}/preview")
async def get_template_preview_image(
    slug: str,
    service: MemeStudioService = Depends(get_meme_studio_service),
) -> Response:
    """Render and return a deterministic PNG preview for a meme template."""
    img_bytes, mime_type = await service.render_template_preview_bytes(slug)
    return Response(
        content=img_bytes,
        media_type=mime_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.post(
    "/upload",
    response_model=MemeAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_meme_image_endpoint(
    request: Request,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: MemeStudioService = Depends(get_meme_studio_service),
) -> MemeAssetResponse:
    """Upload a custom meme image via multipart/form-data (subject to 6 MB envelope & 5 MB image limit)."""
    content_type = request.headers.get("content-type", "")
    raw_body = await request.body()
    file_bytes, file_mime, alt_text, language = _parse_multipart_upload(content_type, raw_body)
    return await service.upload_custom_meme_asset(
        user_id=str(auth_ctx["user"]["id"]),
        raw_bytes=file_bytes,
        declared_mime_type=file_mime,
        alt_text=alt_text,
        language=language,
    )


@router.post(
    "/render",
    response_model=MemeAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/render-template",
    response_model=MemeAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def render_template_meme_endpoint(
    payload: RenderTemplateRequest,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: MemeStudioService = Depends(get_meme_studio_service),
) -> MemeAssetResponse:
    """Synchronously render a workplace meme template with multi-region Unicode text."""
    return await service.render_template_meme(
        user_id=str(auth_ctx["user"]["id"]),
        payload=payload,
    )


@router.post("/captions", response_model=SuggestCaptionsResponse)
@router.post("/captions/suggest", response_model=SuggestCaptionsResponse)
async def suggest_meme_captions_endpoint(
    payload: SuggestCaptionsRequest,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: MemeStudioService = Depends(get_meme_studio_service),
) -> SuggestCaptionsResponse:
    """Generate structured AI workplace caption suggestions with PII stripping and daily quotas."""
    return await service.suggest_captions(
        user_id=str(auth_ctx["user"]["id"]),
        payload=payload,
    )


@router.post(
    "/jobs",
    response_model=MemeJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_meme_generation_job_endpoint(
    payload: CreateMemeJobRequest,
    response: Response,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: MemeStudioService = Depends(get_meme_studio_service),
) -> MemeJobResponse:
    """Create an idempotent asynchronous AI meme image generation job."""
    job_resp, _ = await service.create_image_job(
        user_id=str(auth_ctx["user"]["id"]),
        payload=payload,
        header_idempotency_key=idempotency_key,
    )
    response.status_code = status.HTTP_202_ACCEPTED
    return job_resp


@router.get("/jobs/{job_id}", response_model=MemeJobResponse)
async def get_meme_generation_job_endpoint(
    job_id: str,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: MemeStudioService = Depends(get_meme_studio_service),
) -> MemeJobResponse:
    """Inspect the status of an asynchronous meme generation job (owner/admin only)."""
    return await service.get_job_status(
        job_id=job_id,
        actor_user=auth_ctx["user"],
    )


@router.post("/jobs/{job_id}/cancel", response_model=MemeJobResponse)
async def cancel_meme_generation_job_endpoint(
    job_id: str,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: MemeStudioService = Depends(get_meme_studio_service),
) -> MemeJobResponse:
    """Cancel a queued meme generation job before execution."""
    return await service.cancel_job(
        job_id=job_id,
        actor_user=auth_ctx["user"],
    )


@router.get("/assets/{asset_id}/download")
async def download_meme_asset_endpoint(
    asset_id: str,
    auth_ctx: Optional[dict[str, Any]] = Depends(get_optional_authenticated_context),
    service: MemeStudioService = Depends(get_meme_studio_service),
) -> Response:
    """Download a validated meme image asset with safe content-disposition headers."""
    viewer_user = auth_ctx["user"] if auth_ctx else None
    asset_meta, raw_bytes = await service.get_asset_for_download(
        asset_id=asset_id,
        viewer_user=viewer_user,
    )
    ext = "webp" if asset_meta.mime_type == "image/webp" else ("jpg" if asset_meta.mime_type == "image/jpeg" else "png")
    filename = f"pressure-out-meme-{asset_meta.id[:8]}.{ext}"
    return Response(
        content=raw_bytes,
        media_type=asset_meta.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=3600" if not asset_meta.is_published else "public, max-age=86400",
        },
    )
