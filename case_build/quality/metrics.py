from __future__ import annotations

from pathlib import Path

import duckdb

from utils import sql_literal


def write_quality_metrics(
    con: duckdb.DuckDBPyConnection,
    cases: Path,
    case_shelf: Path,
    case_users: Path,
    choice_truth: Path,
    population_truth: Path,
    market_truth: Path,
    destination: Path,
    copy_atomic,
    *,
    review_activity_truth: Path | None = None,
) -> None:
    c = sql_literal(str(cases))
    s = sql_literal(str(case_shelf))
    u = sql_literal(str(case_users))
    g1 = sql_literal(str(choice_truth))
    g2 = sql_literal(str(population_truth))
    mt = sql_literal(str(market_truth))

    review_cte = ""
    review_join = ""
    review_select = (
        "NULL::BIGINT AS focal_review_activity_count, "
        "NULL::BIGINT AS focal_review_activity_rank"
    )
    if review_activity_truth is not None:
        rt = sql_literal(str(review_activity_truth))
        review_cte = f""",
        focal_review AS (
            SELECT case_candidate_id,
                   review_activity_count AS focal_review_activity_count,
                   review_activity_rank AS focal_review_activity_rank
            FROM read_parquet({rt})
            WHERE role='focal'
        )
        """
        review_join = "LEFT JOIN focal_review fr USING(case_candidate_id)"
        review_select = (
            "fr.focal_review_activity_count, fr.focal_review_activity_rank"
        )

    copy_atomic(f"""
        WITH shelf AS (
            SELECT case_candidate_id,
                   count(*)::BIGINT AS shelf_product_count,
                   count(*) FILTER (role='competitor')::BIGINT AS competitor_count,
                   count(*) FILTER (role='focal')::BIGINT AS focal_rows,
                   min(pre_t0_review_count) FILTER (role='focal')::BIGINT
                       AS focal_pre_t0_review_count,
                   min(pre_t0_recent_review_count) FILTER (role='focal')::BIGINT
                       AS focal_recent_review_count
            FROM read_parquet({s})
            GROUP BY case_candidate_id
        ), users AS (
            SELECT case_candidate_id,
                   count(*)::BIGINT AS selected_user_count
            FROM read_parquet({u})
            GROUP BY case_candidate_id
        ), gt1 AS (
            SELECT case_candidate_id,
                   count(*)::BIGINT AS gt1_user_count
            FROM read_parquet({g1})
            GROUP BY case_candidate_id
        ), gt2 AS (
            SELECT case_candidate_id,
                   count(*)::BIGINT AS gt2_user_count,
                   count(*) FILTER (outcome_product_id IS NOT NULL)::BIGINT
                       AS market_positive_user_count,
                   count(*) FILTER (outcome_product_id IS NULL)::BIGINT AS none_user_count
            FROM read_parquet({g2})
            GROUP BY case_candidate_id
        ), focal_market AS (
            SELECT m.case_candidate_id,
                   m.demand_count AS focal_demand_count,
                   m.demand_share AS focal_demand_share,
                   m.rank AS focal_demand_rank
            FROM read_parquet({mt}) m
            JOIN read_parquet({c}) c USING(case_candidate_id)
            WHERE m.product_id=c.focal_product_id
        )
        {review_cte}
        SELECT c.*,
               coalesce(s.shelf_product_count, 0)::BIGINT AS shelf_product_count,
               coalesce(s.competitor_count, 0)::BIGINT AS competitor_count,
               coalesce(s.focal_rows, 0)::BIGINT AS focal_rows,
               s.focal_pre_t0_review_count,
               s.focal_recent_review_count,
               coalesce(u.selected_user_count, 0)::BIGINT AS selected_user_count,
               coalesce(g1.gt1_user_count, 0)::BIGINT AS gt1_user_count,
               coalesce(g2.gt2_user_count, 0)::BIGINT AS gt2_user_count,
               coalesce(g2.market_positive_user_count, 0)::BIGINT
                   AS market_positive_user_count,
               coalesce(g2.none_user_count, 0)::BIGINT AS none_user_count,
               CASE WHEN coalesce(g2.gt2_user_count,0)>0
                    THEN coalesce(g2.none_user_count,0)::DOUBLE/g2.gt2_user_count
                    ELSE NULL END AS none_rate,
               (coalesce(u.selected_user_count,0)=coalesce(g2.gt2_user_count,0))
                   AS gt2_coverage_complete,
               fm.focal_demand_count,
               fm.focal_demand_share,
               fm.focal_demand_rank,
               {review_select}
        FROM read_parquet({c}) c
        LEFT JOIN shelf s USING(case_candidate_id)
        LEFT JOIN users u USING(case_candidate_id)
        LEFT JOIN gt1 USING(case_candidate_id)
        LEFT JOIN gt2 USING(case_candidate_id)
        LEFT JOIN focal_market fm USING(case_candidate_id)
        {review_join}
        ORDER BY c.market_id, c.t0, c.case_candidate_id
    """, destination)
