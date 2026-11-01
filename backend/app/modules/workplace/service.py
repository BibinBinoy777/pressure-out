"""Service layer for Phase 11 Workplace Experiences, Resignation Stories,
Private Structured Contributions, and the Privacy-Safe k-Anonymity Aggregation Engine.
"""
from __future__ import annotations

import statistics
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config import Settings, get_settings
from app.core.errors import AppError
from app.core.rate_limit import rate_limiter
from app.modules.identity.schemas import validate_bcp47_tag
from app.modules.posts.schemas import CursorPostListResponse, PublicPostResponse
from app.modules.posts.service import (
    POST_COLUMNS,
    PostService,
    _row_to_dict,
    decode_cursor,
    encode_cursor,
)
from app.modules.workplace.schemas import (
    AggregatedRatingMetricCard,
    AggregatedResignationBreakdown,
    CreateWorkplaceContributionRequest,
    PrivateContributionResponse,
    PublicWorkplaceDetailSummary,
    ResignationReasonBucket,
    UpdateWorkplaceContributionRequest,
    VALID_BROAD_REGIONS,
    VALID_COMPANY_SIZE_BANDS,
    VALID_EXPERIENCE_BANDS,
    VALID_EXPERIENCE_CATEGORIES,
    VALID_INDUSTRY_CATEGORIES,
    VALID_RESIGNATION_REASONS,
    VALID_ROLE_FAMILIES,
    VALID_WORK_ARRANGEMENTS,
    WorkplaceInsightsMethodology,
    WorkplaceInsightsResponse,
    _validate_optional_enum,
    _validate_optional_rating,
)

CONTRIBUTION_COLUMNS = (
    "id",
    "user_id",
    "aggregation_consent",
    "industry_category",
    "role_family",
    "experience_band",
    "company_size_band",
    "broad_region",
    "work_arrangement",
    "overall_satisfaction",
    "workload_rating",
    "management_support",
    "work_life_balance",
    "career_growth",
    "workplace_flexibility",
    "compensation_satisfaction",
    "team_culture",
    "employee_autonomy",
    "resignation_reason",
    "created_at",
    "updated_at",
)

RATING_METRICS_SPEC: Tuple[Tuple[str, str, bool], ...] = (
    ("overall_satisfaction", "Overall Workplace Satisfaction", False),
    ("work_life_balance", "Work-Life Balance", False),
    ("management_support", "Management Support", False),
    ("career_growth", "Career Growth Opportunities", False),
    ("workload_rating", "Workload Sustainability", False),
    ("workplace_flexibility", "Workplace Flexibility", False),
    ("team_culture", "Team Culture & Psychological Safety", False),
    ("employee_autonomy", "Employee Autonomy", False),
    ("compensation_satisfaction", "Compensation Satisfaction (Sensitive)", True),
)

MAX_SIMULTANEOUS_FILTERS = 2


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def format_coarse_sample_band(count: int, min_threshold: int) -> str:
    """Round sample size down to coarse bands of 5 so single-user changes cannot be differenced."""
    if count < min_threshold:
        return "Insufficient data"
    floored = (count // 5) * 5
    return f"{max(min_threshold, floored)}+"


class WorkplaceService:
    """Manages workplace experience feeds, resignation stories, private contributions, and k-anonymity insights."""

    def __init__(self, session: Any, settings: Optional[Settings] = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    async def list_workplace_posts(
        self,
        *,
        experience_kind: str = "workplace_experience",
        category: Optional[str] = None,
        resignation_reason: Optional[str] = None,
        experience_band: Optional[str] = None,
        industry_category: Optional[str] = None,
        content_language: Optional[str] = None,
        sort: str = "latest",
        cursor: Optional[str] = None,
        limit: int = 20,
        viewer_user: Optional[dict[str, Any]] = None,
    ) -> CursorPostListResponse:
        """List published workplace experiences or resignation stories using the canonical `posts` table."""
        viewer_id = str(viewer_user["id"]) if viewer_user else None
        safe_limit = max(1, min(limit, 50))

        clauses = ["p.moderation_status = 'published'", "p.deleted_at IS NULL"]
        params: List[Any] = []

        if experience_kind == "resignation_story":
            clauses.append(
                "(wx.experience_kind = 'resignation_story' OR p.community_slug = 'resignation-stories')"
            )
        else:
            clauses.append(
                "(wx.post_id IS NOT NULL OR p.post_type = 'workplace_experience')"
            )

        if category:
            val_cat = _validate_optional_enum(
                category, VALID_EXPERIENCE_CATEGORIES, "category"
            )
            clauses.append("wx.experience_category = ?")
            params.append(val_cat)

        if resignation_reason:
            val_reason = _validate_optional_enum(
                resignation_reason, VALID_RESIGNATION_REASONS, "resignation_reason"
            )
            clauses.append(
                "(wx.primary_resignation_reason = ? OR wx.secondary_resignation_reason = ?)"
            )
            params.extend([val_reason, val_reason])

        if experience_band:
            val_band = _validate_optional_enum(
                experience_band, VALID_EXPERIENCE_BANDS, "experience_band"
            )
            clauses.append("wx.experience_band = ?")
            params.append(val_band)

        if industry_category:
            val_ind = _validate_optional_enum(
                industry_category, VALID_INDUSTRY_CATEGORIES, "industry_category"
            )
            clauses.append("wx.industry_category = ?")
            params.append(val_ind)

        if content_language:
            clauses.append("p.content_language = ?")
            params.append(validate_bcp47_tag(content_language))

        if viewer_id:
            clauses.append(
                """
                (
                    p.author_user_id IS NULL
                    OR NOT EXISTS (
                        SELECT 1 FROM user_blocks ub
                        WHERE (ub.blocker_user_id = ? AND ub.blocked_user_id = p.author_user_id)
                           OR (ub.blocker_user_id = p.author_user_id AND ub.blocked_user_id = ? AND ub.block_mode = 'block')
                    )
                )
                """
            )
            params.extend([viewer_id, viewer_id])

        if cursor:
            c_time, c_id = decode_cursor(cursor)
            clauses.append("(p.created_at < ? OR (p.created_at = ? AND p.id < ?))")
            params.extend([c_time, c_time, c_id])

        order_sql = (
            "p.hot_rank_score DESC, p.created_at DESC, p.id DESC"
            if sort.strip().lower() == "popular"
            else "p.created_at DESC, p.id DESC"
        )
        col_list = ", ".join(f"p.{c}" for c in POST_COLUMNS)
        where_sql = " AND ".join(clauses)

        rows = await self.session.execute(
            f"""
            SELECT {col_list}
            FROM posts p
            LEFT JOIN workplace_experience_details wx ON wx.post_id = p.id
            WHERE {where_sql}
            ORDER BY {order_sql}
            LIMIT ?
            """,
            tuple(params + [safe_limit + 1]),
        )

        has_more = len(rows) > safe_limit
        sliced = rows[:safe_limit]

        post_service = PostService(self.session)
        items: List[PublicPostResponse] = []
        for r in sliced:
            post_dict = _row_to_dict(POST_COLUMNS, r)
            items.append(
                await post_service._build_public_post_response(
                    post_dict, viewer_user_id=viewer_id
                )
            )

        next_cur: Optional[str] = None
        if has_more and items:
            last = items[-1]
            next_cur = encode_cursor(last.created_at, last.id)

        return CursorPostListResponse(
            items=items,
            next_cursor=next_cur,
            has_more=has_more,
        )

    def _serialize_private_contribution(
        self, row_dict: dict[str, Any]
    ) -> PrivateContributionResponse:
        return PrivateContributionResponse(
            id=str(row_dict["id"]),
            aggregation_consent=bool(row_dict["aggregation_consent"]),
            industry_category=row_dict.get("industry_category"),
            role_family=row_dict.get("role_family"),
            experience_band=row_dict.get("experience_band"),
            company_size_band=row_dict.get("company_size_band"),
            broad_region=row_dict.get("broad_region"),
            work_arrangement=row_dict.get("work_arrangement"),
            overall_satisfaction=row_dict.get("overall_satisfaction"),
            workload_rating=row_dict.get("workload_rating"),
            management_support=row_dict.get("management_support"),
            work_life_balance=row_dict.get("work_life_balance"),
            career_growth=row_dict.get("career_growth"),
            workplace_flexibility=row_dict.get("workplace_flexibility"),
            compensation_satisfaction=row_dict.get("compensation_satisfaction"),
            team_culture=row_dict.get("team_culture"),
            employee_autonomy=row_dict.get("employee_autonomy"),
            resignation_reason=row_dict.get("resignation_reason"),
            is_self_reported=True,
            created_at=str(row_dict["created_at"]),
            updated_at=str(row_dict["updated_at"]),
        )

    async def create_contribution(
        self,
        *,
        user_id: str,
        payload: CreateWorkplaceContributionRequest,
    ) -> PrivateContributionResponse:
        """Create an explicit structured workplace contribution (max 1 active record per user)."""
        if not payload.aggregation_consent:
            raise AppError(
                code="CONSENT_REQUIRED",
                message="Explicit aggregation consent is required to submit a structured workplace contribution.",
                status_code=422,
            )

        existing = await self.session.execute(
            "SELECT id FROM workplace_insight_contributions WHERE user_id = ?",
            (user_id,),
        )
        if existing:
            raise AppError(
                code="CONTRIBUTION_ALREADY_EXISTS",
                message="You already have an active structured workplace contribution. You can update or delete it at any time.",
                status_code=409,
            )

        ind = _validate_optional_enum(
            payload.industry_category, VALID_INDUSTRY_CATEGORIES, "industry_category"
        )
        role_fam = _validate_optional_enum(
            payload.role_family, VALID_ROLE_FAMILIES, "role_family"
        )
        exp_band = _validate_optional_enum(
            payload.experience_band, VALID_EXPERIENCE_BANDS, "experience_band"
        )
        comp_size = _validate_optional_enum(
            payload.company_size_band, VALID_COMPANY_SIZE_BANDS, "company_size_band"
        )
        region = _validate_optional_enum(
            payload.broad_region, VALID_BROAD_REGIONS, "broad_region"
        )
        work_arr = _validate_optional_enum(
            payload.work_arrangement, VALID_WORK_ARRANGEMENTS, "work_arrangement"
        )
        resign_reason = _validate_optional_enum(
            payload.resignation_reason, VALID_RESIGNATION_REASONS, "resignation_reason"
        )

        ratings = {
            "overall_satisfaction": _validate_optional_rating(
                payload.overall_satisfaction, "overall_satisfaction"
            ),
            "workload_rating": _validate_optional_rating(
                payload.workload_rating, "workload_rating"
            ),
            "management_support": _validate_optional_rating(
                payload.management_support, "management_support"
            ),
            "work_life_balance": _validate_optional_rating(
                payload.work_life_balance, "work_life_balance"
            ),
            "career_growth": _validate_optional_rating(
                payload.career_growth, "career_growth"
            ),
            "workplace_flexibility": _validate_optional_rating(
                payload.workplace_flexibility, "workplace_flexibility"
            ),
            "compensation_satisfaction": _validate_optional_rating(
                payload.compensation_satisfaction, "compensation_satisfaction"
            ),
            "team_culture": _validate_optional_rating(
                payload.team_culture, "team_culture"
            ),
            "employee_autonomy": _validate_optional_rating(
                payload.employee_autonomy, "employee_autonomy"
            ),
        }

        if all(v is None for v in ratings.values()) and resign_reason is None:
            raise AppError(
                code="EMPTY_CONTRIBUTION",
                message="Please provide at least one workplace rating or structured resignation reason.",
                status_code=422,
            )

        contrib_id = str(uuid.uuid4())
        now_str = _now_iso()
        await self.session.execute(
            """
            INSERT INTO workplace_insight_contributions (
                id, user_id, aggregation_consent, industry_category, role_family,
                experience_band, company_size_band, broad_region, work_arrangement,
                overall_satisfaction, workload_rating, management_support,
                work_life_balance, career_growth, workplace_flexibility,
                compensation_satisfaction, team_culture, employee_autonomy,
                resignation_reason, created_at, updated_at
            ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                contrib_id,
                user_id,
                ind,
                role_fam,
                exp_band,
                comp_size,
                region,
                work_arr,
                ratings["overall_satisfaction"],
                ratings["workload_rating"],
                ratings["management_support"],
                ratings["work_life_balance"],
                ratings["career_growth"],
                ratings["workplace_flexibility"],
                ratings["compensation_satisfaction"],
                ratings["team_culture"],
                ratings["employee_autonomy"],
                resign_reason,
                now_str,
                now_str,
            ),
        )

        rows = await self.session.execute(
            f"SELECT {', '.join(CONTRIBUTION_COLUMNS)} FROM workplace_insight_contributions WHERE id = ?",
            (contrib_id,),
        )
        return self._serialize_private_contribution(
            _row_to_dict(CONTRIBUTION_COLUMNS, rows[0])
        )

    async def get_my_contribution(
        self, *, user_id: str
    ) -> Optional[PrivateContributionResponse]:
        rows = await self.session.execute(
            f"SELECT {', '.join(CONTRIBUTION_COLUMNS)} FROM workplace_insight_contributions WHERE user_id = ?",
            (user_id,),
        )
        if not rows:
            return None
        return self._serialize_private_contribution(
            _row_to_dict(CONTRIBUTION_COLUMNS, rows[0])
        )

    async def update_contribution(
        self,
        *,
        contribution_id: str,
        user_id: str,
        payload: UpdateWorkplaceContributionRequest,
    ) -> PrivateContributionResponse:
        rows = await self.session.execute(
            f"SELECT {', '.join(CONTRIBUTION_COLUMNS)} FROM workplace_insight_contributions WHERE id = ?",
            (contribution_id,),
        )
        if not rows:
            raise AppError(
                code="CONTRIBUTION_NOT_FOUND",
                message="The specified workplace contribution was not found.",
                status_code=404,
            )
        curr = _row_to_dict(CONTRIBUTION_COLUMNS, rows[0])
        if str(curr["user_id"]) != user_id:
            raise AppError(
                code="FORBIDDEN_NOT_OWNER",
                message="You are only permitted to view or modify your own structured workplace contribution.",
                status_code=403,
            )

        new_consent = (
            1
            if (
                payload.aggregation_consent
                if payload.aggregation_consent is not None
                else bool(curr["aggregation_consent"])
            )
            else 0
        )
        ind = (
            _validate_optional_enum(
                payload.industry_category, VALID_INDUSTRY_CATEGORIES, "industry_category"
            )
            if payload.industry_category is not None
            else curr.get("industry_category")
        )
        role_fam = (
            _validate_optional_enum(
                payload.role_family, VALID_ROLE_FAMILIES, "role_family"
            )
            if payload.role_family is not None
            else curr.get("role_family")
        )
        exp_band = (
            _validate_optional_enum(
                payload.experience_band, VALID_EXPERIENCE_BANDS, "experience_band"
            )
            if payload.experience_band is not None
            else curr.get("experience_band")
        )
        comp_size = (
            _validate_optional_enum(
                payload.company_size_band, VALID_COMPANY_SIZE_BANDS, "company_size_band"
            )
            if payload.company_size_band is not None
            else curr.get("company_size_band")
        )
        region = (
            _validate_optional_enum(
                payload.broad_region, VALID_BROAD_REGIONS, "broad_region"
            )
            if payload.broad_region is not None
            else curr.get("broad_region")
        )
        work_arr = (
            _validate_optional_enum(
                payload.work_arrangement, VALID_WORK_ARRANGEMENTS, "work_arrangement"
            )
            if payload.work_arrangement is not None
            else curr.get("work_arrangement")
        )
        resign_reason = (
            _validate_optional_enum(
                payload.resignation_reason, VALID_RESIGNATION_REASONS, "resignation_reason"
            )
            if payload.resignation_reason is not None
            else curr.get("resignation_reason")
        )

        rating_cols = (
            "overall_satisfaction",
            "workload_rating",
            "management_support",
            "work_life_balance",
            "career_growth",
            "workplace_flexibility",
            "compensation_satisfaction",
            "team_culture",
            "employee_autonomy",
        )
        updated_ratings: Dict[str, Optional[int]] = {}
        for col in rating_cols:
            incoming = getattr(payload, col)
            if incoming is not None:
                updated_ratings[col] = _validate_optional_rating(incoming, col)
            else:
                updated_ratings[col] = curr.get(col)

        now_str = _now_iso()
        await self.session.execute(
            """
            UPDATE workplace_insight_contributions
            SET aggregation_consent = ?,
                industry_category = ?,
                role_family = ?,
                experience_band = ?,
                company_size_band = ?,
                broad_region = ?,
                work_arrangement = ?,
                overall_satisfaction = ?,
                workload_rating = ?,
                management_support = ?,
                work_life_balance = ?,
                career_growth = ?,
                workplace_flexibility = ?,
                compensation_satisfaction = ?,
                team_culture = ?,
                employee_autonomy = ?,
                resignation_reason = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                new_consent,
                ind,
                role_fam,
                exp_band,
                comp_size,
                region,
                work_arr,
                updated_ratings["overall_satisfaction"],
                updated_ratings["workload_rating"],
                updated_ratings["management_support"],
                updated_ratings["work_life_balance"],
                updated_ratings["career_growth"],
                updated_ratings["workplace_flexibility"],
                updated_ratings["compensation_satisfaction"],
                updated_ratings["team_culture"],
                updated_ratings["employee_autonomy"],
                resign_reason,
                now_str,
                contribution_id,
            ),
        )

        refreshed = await self.session.execute(
            f"SELECT {', '.join(CONTRIBUTION_COLUMNS)} FROM workplace_insight_contributions WHERE id = ?",
            (contribution_id,),
        )
        return self._serialize_private_contribution(
            _row_to_dict(CONTRIBUTION_COLUMNS, refreshed[0])
        )

    async def delete_contribution(
        self, *, contribution_id: str, user_id: str
    ) -> None:
        rows = await self.session.execute(
            "SELECT id, user_id FROM workplace_insight_contributions WHERE id = ?",
            (contribution_id,),
        )
        if not rows:
            raise AppError(
                code="CONTRIBUTION_NOT_FOUND",
                message="The specified workplace contribution was not found.",
                status_code=404,
            )
        if str(rows[0][1]) != user_id:
            raise AppError(
                code="FORBIDDEN_NOT_OWNER",
                message="You are only permitted to delete your own structured workplace contribution.",
                status_code=403,
            )
        await self.session.execute(
            "DELETE FROM workplace_insight_contributions WHERE id = ?",
            (contribution_id,),
        )

    async def get_aggregated_insights(
        self,
        *,
        industry_category: Optional[str] = None,
        role_family: Optional[str] = None,
        experience_band: Optional[str] = None,
        company_size_band: Optional[str] = None,
        broad_region: Optional[str] = None,
        work_arrangement: Optional[str] = None,
        rate_limit_key: str = "insights_viewer",
    ) -> WorkplaceInsightsResponse:
        """Compute k-anonymity protected workplace insights purely from consented structured contributions."""
        rate_limiter.check_and_record(
            bucket="workplace_insights_query",
            key=rate_limit_key,
            limit=30,
            window_seconds=60,
        )

        selected_filters: Dict[str, str] = {}
        clauses = ["aggregation_consent = 1"]
        params: List[Any] = []

        filter_specs = (
            ("industry_category", industry_category, VALID_INDUSTRY_CATEGORIES),
            ("role_family", role_family, VALID_ROLE_FAMILIES),
            ("experience_band", experience_band, VALID_EXPERIENCE_BANDS),
            ("company_size_band", company_size_band, VALID_COMPANY_SIZE_BANDS),
            ("broad_region", broad_region, VALID_BROAD_REGIONS),
            ("work_arrangement", work_arrangement, VALID_WORK_ARRANGEMENTS),
        )
        for col_name, raw_val, allowed in filter_specs:
            val = _validate_optional_enum(raw_val, allowed, col_name)
            if val is not None:
                selected_filters[col_name] = val
                clauses.append(f"{col_name} = ?")
                params.append(val)

        if len(selected_filters) > MAX_SIMULTANEOUS_FILTERS:
            raise AppError(
                code="TOO_MANY_INSIGHT_FILTERS",
                message=f"To protect contributor privacy and prevent cohort narrowing, at most {MAX_SIMULTANEOUS_FILTERS} filter dimensions may be combined at once.",
                status_code=422,
            )

        where_sql = " AND ".join(clauses)
        rows = await self.session.execute(
            f"""
            SELECT {', '.join(CONTRIBUTION_COLUMNS)}
            FROM workplace_insight_contributions
            WHERE {where_sql}
            """,
            tuple(params),
        )

        # Deduplicate by user_id defensively even though UNIQUE(user_id) is enforced at DB level
        by_user: Dict[str, dict[str, Any]] = {}
        for r in rows:
            d = _row_to_dict(CONTRIBUTION_COLUMNS, r)
            by_user[str(d["user_id"])] = d

        consented_records = list(by_user.values())
        general_min = self.settings.insights_min_cohort_size
        sensitive_min = self.settings.insights_sensitive_min_cohort_size
        min_bucket = self.settings.insights_min_category_bucket_count

        total_distinct = len(consented_records)
        cohort_band = (
            format_coarse_sample_band(total_distinct, general_min)
            if total_distinct >= general_min
            else None
        )

        metric_cards: List[AggregatedRatingMetricCard] = []
        for col_key, label, is_sens in RATING_METRICS_SPEC:
            req_min = sensitive_min if is_sens else general_min
            vals = [
                int(rec[col_key])
                for rec in consented_records
                if rec.get(col_key) is not None
            ]
            n_val = len(vals)
            if n_val < req_min:
                metric_cards.append(
                    AggregatedRatingMetricCard(
                        metric_key=col_key,
                        label=label,
                        is_sensitive=is_sens,
                        minimum_threshold=req_min,
                        insufficient_data=True,
                        sample_size_band=None,
                        average_rating=None,
                        median_rating=None,
                        rating_distribution_pct=None,
                        status_message="Not enough contributions yet to display a privacy-protected result for this group.",
                    )
                )
            else:
                avg_r = round(sum(vals) / n_val, 1)
                med_r = round(float(statistics.median(vals)), 1)
                dist_pct: Dict[str, int] = {}
                for score_int in range(1, 6):
                    cnt = sum(1 for v in vals if v == score_int)
                    dist_pct[str(score_int)] = round((cnt / n_val) * 100)
                metric_cards.append(
                    AggregatedRatingMetricCard(
                        metric_key=col_key,
                        label=label,
                        is_sensitive=is_sens,
                        minimum_threshold=req_min,
                        insufficient_data=False,
                        sample_size_band=format_coarse_sample_band(n_val, req_min),
                        average_rating=avg_r,
                        median_rating=med_r,
                        rating_distribution_pct=dist_pct,
                        status_message="Privacy threshold satisfied.",
                    )
                )

        # Categorical resignation reasons breakdown (sensitive threshold >= 20 + complementary suppression)
        resign_vals = [
            str(rec["resignation_reason"])
            for rec in consented_records
            if rec.get("resignation_reason")
        ]
        n_resign = len(resign_vals)
        if n_resign < sensitive_min:
            resign_breakdown = AggregatedResignationBreakdown(
                minimum_threshold=sensitive_min,
                insufficient_data=True,
                sample_size_band=None,
                buckets=[],
                suppressed_other_percentage=0,
                status_message="Not enough contributions yet to display a privacy-protected resignation breakdown for this group.",
            )
        else:
            counts_by_reason: Dict[str, int] = {}
            for rv in resign_vals:
                counts_by_reason[rv] = counts_by_reason.get(rv, 0) + 1

            sorted_reasons = sorted(
                counts_by_reason.items(), key=lambda kv: (-kv[1], kv[0])
            )
            visible_pairs = [(r, c) for r, c in sorted_reasons if c >= min_bucket]
            suppressed_pairs = [(r, c) for r, c in sorted_reasons if c < min_bucket]

            # Complementary suppression: if only 1 small bucket was suppressed (or total suppressed count < min_bucket),
            # also suppress the smallest visible bucket so differencing cannot isolate a single contributor!
            suppressed_total = sum(c for _, c in suppressed_pairs)
            if 0 < suppressed_total < min_bucket and visible_pairs:
                smallest_vis = visible_pairs.pop()
                suppressed_pairs.append(smallest_vis)
                suppressed_total += smallest_vis[1]

            buckets = [
                ResignationReasonBucket(
                    reason_code=r,
                    percentage=round((c / n_resign) * 100),
                )
                for r, c in visible_pairs
            ]
            supp_pct = round((suppressed_total / n_resign) * 100) if suppressed_total > 0 else 0
            resign_breakdown = AggregatedResignationBreakdown(
                minimum_threshold=sensitive_min,
                insufficient_data=False,
                sample_size_band=format_coarse_sample_band(n_resign, sensitive_min),
                buckets=buckets,
                suppressed_other_percentage=supp_pct,
                status_message="Privacy threshold and complementary bucket suppression satisfied.",
            )

        return WorkplaceInsightsResponse(
            selected_filters=selected_filters,
            cohort_eligible_band=cohort_band,
            metrics=metric_cards,
            resignation_reasons=resign_breakdown,
            methodology=WorkplaceInsightsMethodology(
                data_source_note="Derived exclusively from voluntary, explicitly consented structured contributions.",
                self_reported_disclaimer="All contributions are self-reported by community members, unverified, and not statistically representative of an entire industry, employer, or country.",
                general_min_cohort_threshold=general_min,
                sensitive_min_cohort_threshold=sensitive_min,
                max_simultaneous_filters=MAX_SIMULTANEOUS_FILTERS,
                free_text_excluded=True,
                employer_leaderboard_excluded=True,
                last_computed_at=_now_iso(),
            ),
        )
