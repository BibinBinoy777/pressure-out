"""FastAPI endpoints for Phase 11 Workplace Experiences, Resignation Stories,
Structured Contributions & Privacy-Safe Aggregated Insights (`/api/v1/workplace`).
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import (
    get_optional_authenticated_context,
    get_workplace_service,
    require_authenticated_context,
)
from app.modules.posts.schemas import CursorPostListResponse
from app.modules.workplace.schemas import (
    CreateWorkplaceContributionRequest,
    PrivateContributionResponse,
    UpdateWorkplaceContributionRequest,
    WorkplaceInsightsResponse,
)
from app.modules.workplace.service import WorkplaceService

router = APIRouter(prefix="/workplace", tags=["workplace"])


@router.get("/experiences", response_model=CursorPostListResponse)
async def list_workplace_experiences_endpoint(
    category: Optional[str] = Query(None),
    experience_band: Optional[str] = Query(None),
    industry_category: Optional[str] = Query(None),
    content_language: Optional[str] = Query(None),
    sort: str = Query("latest", description="latest | popular"),
    cursor: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    auth_ctx: Optional[dict[str, Any]] = Depends(get_optional_authenticated_context),
    service: WorkplaceService = Depends(get_workplace_service),
) -> CursorPostListResponse:
    """List public workplace experience posts with category, industry, experience band, and language filters."""
    viewer = auth_ctx["user"] if auth_ctx else None
    return await service.list_workplace_posts(
        experience_kind="workplace_experience",
        category=category,
        experience_band=experience_band,
        industry_category=industry_category,
        content_language=content_language,
        sort=sort,
        cursor=cursor,
        limit=limit,
        viewer_user=viewer,
    )


@router.get("/resignation-stories", response_model=CursorPostListResponse)
async def list_resignation_stories_endpoint(
    resignation_reason: Optional[str] = Query(None),
    experience_band: Optional[str] = Query(None),
    industry_category: Optional[str] = Query(None),
    content_language: Optional[str] = Query(None),
    sort: str = Query("latest", description="latest | popular"),
    cursor: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    auth_ctx: Optional[dict[str, Any]] = Depends(get_optional_authenticated_context),
    service: WorkplaceService = Depends(get_workplace_service),
) -> CursorPostListResponse:
    """List public resignation stories with reason, industry, experience band, and language filters."""
    viewer = auth_ctx["user"] if auth_ctx else None
    return await service.list_workplace_posts(
        experience_kind="resignation_story",
        resignation_reason=resignation_reason,
        experience_band=experience_band,
        industry_category=industry_category,
        content_language=content_language,
        sort=sort,
        cursor=cursor,
        limit=limit,
        viewer_user=viewer,
    )


@router.post(
    "/contributions",
    response_model=PrivateContributionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workplace_contribution_endpoint(
    payload: CreateWorkplaceContributionRequest,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: WorkplaceService = Depends(get_workplace_service),
) -> PrivateContributionResponse:
    """Submit an explicit, consented structured workplace contribution (separate from public posts)."""
    return await service.create_contribution(
        user_id=str(auth_ctx["user"]["id"]),
        payload=payload,
    )


@router.get("/contributions/mine", response_model=Optional[PrivateContributionResponse])
async def get_my_workplace_contribution_endpoint(
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: WorkplaceService = Depends(get_workplace_service),
) -> Optional[PrivateContributionResponse]:
    """Retrieve the authenticated user's own structured workplace contribution."""
    return await service.get_my_contribution(user_id=str(auth_ctx["user"]["id"]))


@router.patch(
    "/contributions/{contribution_id}",
    response_model=PrivateContributionResponse,
)
async def update_workplace_contribution_endpoint(
    contribution_id: str,
    payload: UpdateWorkplaceContributionRequest,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: WorkplaceService = Depends(get_workplace_service),
) -> PrivateContributionResponse:
    """Update fields or withdraw aggregation consent on the user's structured contribution."""
    return await service.update_contribution(
        contribution_id=contribution_id,
        user_id=str(auth_ctx["user"]["id"]),
        payload=payload,
    )


@router.delete("/contributions/{contribution_id}")
async def delete_workplace_contribution_endpoint(
    contribution_id: str,
    auth_ctx: dict[str, Any] = Depends(require_authenticated_context),
    service: WorkplaceService = Depends(get_workplace_service),
) -> dict[str, str]:
    """Permanently delete the user's structured contribution and exclude it from future aggregates."""
    await service.delete_contribution(
        contribution_id=contribution_id,
        user_id=str(auth_ctx["user"]["id"]),
    )
    return {"status": "deleted", "id": contribution_id}


@router.get("/insights", response_model=WorkplaceInsightsResponse)
@router.get("/insights/overview", response_model=WorkplaceInsightsResponse)
async def get_workplace_insights_endpoint(
    request: Request,
    industry_category: Optional[str] = Query(None),
    role_family: Optional[str] = Query(None),
    experience_band: Optional[str] = Query(None),
    company_size_band: Optional[str] = Query(None),
    broad_region: Optional[str] = Query(None),
    work_arrangement: Optional[str] = Query(None),
    auth_ctx: Optional[dict[str, Any]] = Depends(get_optional_authenticated_context),
    service: WorkplaceService = Depends(get_workplace_service),
) -> WorkplaceInsightsResponse:
    """Return k-anonymity protected aggregated workplace insights across up to 2 filter dimensions."""
    rl_key = (
        str(auth_ctx["user"]["id"])
        if auth_ctx
        else (request.client.host if request.client else "127.0.0.1")
    )
    return await service.get_aggregated_insights(
        industry_category=industry_category,
        role_family=role_family,
        experience_band=experience_band,
        company_size_band=company_size_band,
        broad_region=broad_region,
        work_arrangement=work_arrangement,
        rate_limit_key=rl_key,
    )
