"""Phase 11 Workplace Experiences, Resignation Stories & Privacy-Safe Insight Contributions.

Revision ID: 0010_phase11_workplace
Revises: 0009_phase10_translations
Create Date: 2026-10-30
"""
from __future__ import annotations

from typing import Any

revision = "0010_phase11_workplace"
down_revision = "0009_phase10_translations"
branch_labels = None
depends_on = None


def upgrade(conn: Any) -> None:
    """Create `workplace_experience_details` and `workplace_insight_contributions` tables."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workplace_experience_details (
            post_id VARCHAR(36) PRIMARY KEY REFERENCES posts(id) ON DELETE CASCADE,
            experience_kind VARCHAR(24) NOT NULL DEFAULT 'workplace_experience'
                CHECK (experience_kind IN ('workplace_experience', 'resignation_story')),
            experience_category VARCHAR(32) NOT NULL DEFAULT 'workplace_culture'
                CHECK (experience_category IN (
                    'workplace_culture', 'management', 'career_growth', 'compensation',
                    'work_life_balance', 'workplace_conflict', 'remote_work',
                    'team_experience', 'career_change', 'job_search', 'resignation', 'other'
                )),
            primary_resignation_reason VARCHAR(32)
                CHECK (primary_resignation_reason IS NULL OR primary_resignation_reason IN (
                    'better_opportunity', 'compensation', 'management_problems',
                    'workplace_culture', 'workload', 'work_life_balance',
                    'lack_of_growth', 'role_mismatch', 'relocation',
                    'contract_or_layoff', 'career_change', 'entrepreneurship', 'other'
                )),
            secondary_resignation_reason VARCHAR(32)
                CHECK (secondary_resignation_reason IS NULL OR secondary_resignation_reason IN (
                    'better_opportunity', 'compensation', 'management_problems',
                    'workplace_culture', 'workload', 'work_life_balance',
                    'lack_of_growth', 'role_mismatch', 'relocation',
                    'contract_or_layoff', 'career_change', 'entrepreneurship', 'other'
                )),
            experience_band VARCHAR(24)
                CHECK (experience_band IS NULL OR experience_band IN (
                    'fresher_0_1', 'junior_1_3', 'mid_3_6', 'senior_6_10', 'lead_10_plus'
                )),
            industry_category VARCHAR(48),
            transition_outcome VARCHAR(48),
            lesson_learned VARCHAR(500),
            created_at VARCHAR(40) NOT NULL,
            updated_at VARCHAR(40) NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wx_details_kind_cat
        ON workplace_experience_details(experience_kind, experience_category, created_at DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wx_details_resign_reason
        ON workplace_experience_details(primary_resignation_reason, created_at DESC)
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workplace_insight_contributions (
            id VARCHAR(36) PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            aggregation_consent INTEGER NOT NULL DEFAULT 1
                CHECK (aggregation_consent IN (0, 1)),
            industry_category VARCHAR(48),
            role_family VARCHAR(48),
            experience_band VARCHAR(24)
                CHECK (experience_band IS NULL OR experience_band IN (
                    'fresher_0_1', 'junior_1_3', 'mid_3_6', 'senior_6_10', 'lead_10_plus'
                )),
            company_size_band VARCHAR(24)
                CHECK (company_size_band IS NULL OR company_size_band IN (
                    'startup_1_50', 'midsize_51_500', 'large_501_5000', 'enterprise_5000_plus'
                )),
            broad_region VARCHAR(32)
                CHECK (broad_region IS NULL OR broad_region IN (
                    'south_asia', 'north_america', 'europe', 'southeast_asia',
                    'middle_east_africa', 'latin_america', 'oceania', 'remote_global'
                )),
            work_arrangement VARCHAR(24)
                CHECK (work_arrangement IS NULL OR work_arrangement IN (
                    'remote', 'hybrid', 'onsite'
                )),
            overall_satisfaction INTEGER
                CHECK (overall_satisfaction IS NULL OR overall_satisfaction BETWEEN 1 AND 5),
            workload_rating INTEGER
                CHECK (workload_rating IS NULL OR workload_rating BETWEEN 1 AND 5),
            management_support INTEGER
                CHECK (management_support IS NULL OR management_support BETWEEN 1 AND 5),
            work_life_balance INTEGER
                CHECK (work_life_balance IS NULL OR work_life_balance BETWEEN 1 AND 5),
            career_growth INTEGER
                CHECK (career_growth IS NULL OR career_growth BETWEEN 1 AND 5),
            workplace_flexibility INTEGER
                CHECK (workplace_flexibility IS NULL OR workplace_flexibility BETWEEN 1 AND 5),
            compensation_satisfaction INTEGER
                CHECK (compensation_satisfaction IS NULL OR compensation_satisfaction BETWEEN 1 AND 5),
            team_culture INTEGER
                CHECK (team_culture IS NULL OR team_culture BETWEEN 1 AND 5),
            employee_autonomy INTEGER
                CHECK (employee_autonomy IS NULL OR employee_autonomy BETWEEN 1 AND 5),
            resignation_reason VARCHAR(32)
                CHECK (resignation_reason IS NULL OR resignation_reason IN (
                    'better_opportunity', 'compensation', 'management_problems',
                    'workplace_culture', 'workload', 'work_life_balance',
                    'lack_of_growth', 'role_mismatch', 'relocation',
                    'contract_or_layoff', 'career_change', 'entrepreneurship', 'other'
                )),
            created_at VARCHAR(40) NOT NULL,
            updated_at VARCHAR(40) NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wx_contrib_consent_dims
        ON workplace_insight_contributions(
            aggregation_consent, industry_category, role_family, experience_band, work_arrangement
        )
        """
    )


def downgrade(conn: Any) -> None:
    """Drop Phase 11 tables in reverse dependency order."""
    conn.execute("DROP TABLE IF EXISTS workplace_insight_contributions")
    conn.execute("DROP TABLE IF EXISTS workplace_experience_details")
