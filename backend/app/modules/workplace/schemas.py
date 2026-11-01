"""Pydantic schemas and controlled taxonomies for Phase 11 Workplace Experiences,
Resignation Stories, Structured Contributions, and Privacy-Safe Aggregated Insights.
"""
from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.errors import AppError
from app.core.unicode import normalize_optional_unicode_nfc

VALID_EXPERIENCE_KINDS: tuple[str, ...] = (
    "workplace_experience",
    "resignation_story",
)

VALID_EXPERIENCE_CATEGORIES: tuple[str, ...] = (
    "workplace_culture",
    "management",
    "career_growth",
    "compensation",
    "work_life_balance",
    "workplace_conflict",
    "remote_work",
    "team_experience",
    "career_change",
    "job_search",
    "resignation",
    "other",
)

VALID_RESIGNATION_REASONS: tuple[str, ...] = (
    "better_opportunity",
    "compensation",
    "management_problems",
    "workplace_culture",
    "workload",
    "work_life_balance",
    "lack_of_growth",
    "role_mismatch",
    "relocation",
    "contract_or_layoff",
    "career_change",
    "entrepreneurship",
    "other",
)

VALID_INDUSTRY_CATEGORIES: tuple[str, ...] = (
    "technology",
    "finance",
    "healthcare",
    "education",
    "manufacturing",
    "retail_hospitality",
    "consulting_services",
    "media_creative",
    "public_sector",
    "other",
)

VALID_ROLE_FAMILIES: tuple[str, ...] = (
    "software_engineering",
    "product_design",
    "data_analytics",
    "operations_support",
    "sales_marketing",
    "hr_people",
    "finance_legal",
    "management_leadership",
    "other",
)

VALID_EXPERIENCE_BANDS: tuple[str, ...] = (
    "fresher_0_1",
    "junior_1_3",
    "mid_3_6",
    "senior_6_10",
    "lead_10_plus",
)

VALID_COMPANY_SIZE_BANDS: tuple[str, ...] = (
    "startup_1_50",
    "midsize_51_500",
    "large_501_5000",
    "enterprise_5000_plus",
)

VALID_BROAD_REGIONS: tuple[str, ...] = (
    "south_asia",
    "north_america",
    "europe",
    "southeast_asia",
    "middle_east_africa",
    "latin_america",
    "oceania",
    "remote_global",
)

VALID_WORK_ARRANGEMENTS: tuple[str, ...] = (
    "remote",
    "hybrid",
    "onsite",
)

VALID_TRANSITION_OUTCOMES: tuple[str, ...] = (
    "accepted_new_role",
    "taking_break",
    "freelance_entrepreneurship",
    "higher_education",
    "searching",
    "stayed_after_counteroffer",
    "other",
)


def _validate_optional_enum(
    value: Optional[str], allowed: tuple[str, ...], field_name: str
) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    cleaned = str(value).strip().lower()
    if cleaned not in allowed:
        raise AppError(
            code="VALIDATION_ERROR",
            message=f"Invalid {field_name} '{value}'. Allowed values: {', '.join(allowed)}.",
            status_code=422,
        )
    return cleaned


def _validate_optional_rating(value: Optional[int], field_name: str) -> Optional[int]:
    if value is None:
        return None
    if not isinstance(value, int) or value < 1 or value > 5:
        raise AppError(
            code="INVALID_RATING_VALUE",
            message=f"{field_name} must be an integer between 1 (Very poor) and 5 (Very good).",
            status_code=422,
        )
    return value


class WorkplaceExperienceDetailInput(BaseModel):
    experience_kind: str = Field(
        "workplace_experience",
        description="workplace_experience | resignation_story",
    )
    experience_category: str = Field(
        "workplace_culture",
        description="One of the 12 controlled workplace experience categories",
    )
    primary_resignation_reason: Optional[str] = None
    secondary_resignation_reason: Optional[str] = None
    experience_band: Optional[str] = None
    industry_category: Optional[str] = None
    transition_outcome: Optional[str] = None
    lesson_learned: Optional[str] = Field(None, max_length=500)

    def validated_dict(self) -> dict[str, Optional[str]]:
        kind = _validate_optional_enum(
            self.experience_kind, VALID_EXPERIENCE_KINDS, "experience_kind"
        ) or "workplace_experience"
        cat = _validate_optional_enum(
            self.experience_category, VALID_EXPERIENCE_CATEGORIES, "experience_category"
        ) or ("resignation" if kind == "resignation_story" else "workplace_culture")
        p_reason = _validate_optional_enum(
            self.primary_resignation_reason,
            VALID_RESIGNATION_REASONS,
            "primary_resignation_reason",
        )
        s_reason = _validate_optional_enum(
            self.secondary_resignation_reason,
            VALID_RESIGNATION_REASONS,
            "secondary_resignation_reason",
        )
        exp_band = _validate_optional_enum(
            self.experience_band, VALID_EXPERIENCE_BANDS, "experience_band"
        )
        ind_cat = _validate_optional_enum(
            self.industry_category, VALID_INDUSTRY_CATEGORIES, "industry_category"
        )
        outcome = _validate_optional_enum(
            self.transition_outcome, VALID_TRANSITION_OUTCOMES, "transition_outcome"
        )
        lesson = normalize_optional_unicode_nfc(self.lesson_learned)
        if lesson:
            lesson = lesson.strip()[:500] or None
        return {
            "experience_kind": kind,
            "experience_category": cat,
            "primary_resignation_reason": p_reason,
            "secondary_resignation_reason": s_reason,
            "experience_band": exp_band,
            "industry_category": ind_cat,
            "transition_outcome": outcome,
            "lesson_learned": lesson,
        }


class PublicWorkplaceDetailSummary(BaseModel):
    """Privacy-safe structured metadata attached to a public workplace or resignation story.

    Never exposes `author_user_id` and explicitly marks `is_self_reported = True`.
    """

    experience_kind: str
    experience_category: str
    primary_resignation_reason: Optional[str] = None
    secondary_resignation_reason: Optional[str] = None
    experience_band: Optional[str] = None
    industry_category: Optional[str] = None
    transition_outcome: Optional[str] = None
    lesson_learned: Optional[str] = None
    is_self_reported: bool = True


class CreateWorkplaceContributionRequest(BaseModel):
    aggregation_consent: bool = Field(
        ...,
        description="Explicit consent to include this structured response in privacy-safe aggregated insights",
    )
    industry_category: Optional[str] = None
    role_family: Optional[str] = None
    experience_band: Optional[str] = None
    company_size_band: Optional[str] = None
    broad_region: Optional[str] = None
    work_arrangement: Optional[str] = None
    overall_satisfaction: Optional[int] = None
    workload_rating: Optional[int] = None
    management_support: Optional[int] = None
    work_life_balance: Optional[int] = None
    career_growth: Optional[int] = None
    workplace_flexibility: Optional[int] = None
    compensation_satisfaction: Optional[int] = None
    team_culture: Optional[int] = None
    employee_autonomy: Optional[int] = None
    resignation_reason: Optional[str] = None


class UpdateWorkplaceContributionRequest(BaseModel):
    aggregation_consent: Optional[bool] = None
    industry_category: Optional[str] = None
    role_family: Optional[str] = None
    experience_band: Optional[str] = None
    company_size_band: Optional[str] = None
    broad_region: Optional[str] = None
    work_arrangement: Optional[str] = None
    overall_satisfaction: Optional[int] = None
    workload_rating: Optional[int] = None
    management_support: Optional[int] = None
    work_life_balance: Optional[int] = None
    career_growth: Optional[int] = None
    workplace_flexibility: Optional[int] = None
    compensation_satisfaction: Optional[int] = None
    team_culture: Optional[int] = None
    employee_autonomy: Optional[int] = None
    resignation_reason: Optional[str] = None


class PrivateContributionResponse(BaseModel):
    """Owner-only view of a user's private structured workplace contribution."""

    id: str
    aggregation_consent: bool
    industry_category: Optional[str] = None
    role_family: Optional[str] = None
    experience_band: Optional[str] = None
    company_size_band: Optional[str] = None
    broad_region: Optional[str] = None
    work_arrangement: Optional[str] = None
    overall_satisfaction: Optional[int] = None
    workload_rating: Optional[int] = None
    management_support: Optional[int] = None
    work_life_balance: Optional[int] = None
    career_growth: Optional[int] = None
    workplace_flexibility: Optional[int] = None
    compensation_satisfaction: Optional[int] = None
    team_culture: Optional[int] = None
    employee_autonomy: Optional[int] = None
    resignation_reason: Optional[str] = None
    is_self_reported: bool = True
    created_at: str
    updated_at: str


class AggregatedRatingMetricCard(BaseModel):
    """Privacy-safe aggregated rating indicator.

    When `insufficient_data == True`, all numerical summaries and sample sizes are `None`.
    """

    metric_key: str
    label: str
    is_sensitive: bool
    minimum_threshold: int
    insufficient_data: bool
    sample_size_band: Optional[str] = None
    average_rating: Optional[float] = None
    median_rating: Optional[float] = None
    rating_distribution_pct: Optional[Dict[str, int]] = None
    status_message: str


class ResignationReasonBucket(BaseModel):
    reason_code: str
    percentage: int


class AggregatedResignationBreakdown(BaseModel):
    minimum_threshold: int
    insufficient_data: bool
    sample_size_band: Optional[str] = None
    buckets: List[ResignationReasonBucket] = Field(default_factory=list)
    suppressed_other_percentage: int = 0
    status_message: str


class WorkplaceInsightsMethodology(BaseModel):
    data_source_note: str
    self_reported_disclaimer: str
    general_min_cohort_threshold: int
    sensitive_min_cohort_threshold: int
    max_simultaneous_filters: int
    free_text_excluded: bool = True
    employer_leaderboard_excluded: bool = True
    last_computed_at: str


class WorkplaceInsightsResponse(BaseModel):
    """Public privacy-protected aggregated workplace insights response.

    Constructed exclusively from aggregated statistical outputs; NEVER contains
    individual rows, user IDs, handles, or exact low sample counts.
    """

    selected_filters: Dict[str, str]
    cohort_eligible_band: Optional[str] = None
    metrics: List[AggregatedRatingMetricCard]
    resignation_reasons: AggregatedResignationBreakdown
    methodology: WorkplaceInsightsMethodology
