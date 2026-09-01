from __future__ import annotations

from pathlib import Path

import duckdb

from utils import sql_literal


def write_case_future_market_events(
    con: duckdb.DuckDBPyConnection,
    cases: Path,
    case_users: Path,
    case_shelf: Path,
    canonical_user_events: Path,
    destination: Path,
    copy_atomic,
) -> None:
    """保留 Case 用户在 evaluation window 内命中 shelf 的全部真实事件。"""
    c = sql_literal(str(cases))
    u = sql_literal(str(case_users))
    s = sql_literal(str(case_shelf))
    e = sql_literal(str(canonical_user_events))
    copy_atomic(f"""
        SELECT c.case_candidate_id,
               c.market_id,
               c.source_partition,
               c.t0,
               c.evaluation_start,
               c.evaluation_end_exclusive,
               u.user_id,
               s.product_id,
               s.role AS product_role,
               e.event_timestamp,
               e.event_date,
               e.rating,
               e.verified_purchase
        FROM read_parquet({u}) u
        JOIN read_parquet({c}) c USING(case_candidate_id)
        JOIN read_parquet({e}) e
          ON u.user_id=e.user_id
         AND c.source_partition=e.source_partition
         AND e.event_timestamp >= CAST(c.evaluation_start AS TIMESTAMP)
         AND e.event_timestamp < CAST(c.evaluation_end_exclusive AS TIMESTAMP)
        JOIN read_parquet({s}) s
          ON c.case_candidate_id=s.case_candidate_id
         AND e.product_id=s.product_id
        ORDER BY c.case_candidate_id, u.user_id, e.event_timestamp, e.product_id
    """, destination)


def write_review_activity_truth(
    con: duckdb.DuckDBPyConnection,
    cases: Path,
    case_shelf: Path,
    rating_daily: Path,
    destination: Path,
    copy_atomic,
) -> None:
    """辅助商品级真值：对完整 shelf 的未来评论量做份额与排名。

    这一张不依赖 Case 用户采样，迁自 v5 market_ranking_truth 的核心聚合思想。
    """
    c = sql_literal(str(cases))
    s = sql_literal(str(case_shelf))
    d = sql_literal(str(rating_daily))
    copy_atomic(f"""
        WITH products AS (
            SELECT DISTINCT c.case_candidate_id,
                   c.source_partition,
                   c.evaluation_start,
                   c.evaluation_end_exclusive,
                   s.product_id,
                   s.role
            FROM read_parquet({c}) c
            JOIN read_parquet({s}) s USING(case_candidate_id)
        ), totals AS (
            SELECT p.case_candidate_id, p.product_id, p.role,
                   coalesce(sum(d.rating_count), 0)::BIGINT AS review_activity_count
            FROM products p
            LEFT JOIN read_parquet({d}) d
              ON p.source_partition=d.source_partition
             AND p.product_id=d.product_id
             AND d.event_date >= p.evaluation_start
             AND d.event_date < p.evaluation_end_exclusive
            GROUP BY p.case_candidate_id, p.product_id, p.role
        ), ranked AS (
            SELECT *,
                   row_number() OVER (
                       PARTITION BY case_candidate_id
                       ORDER BY review_activity_count DESC, product_id
                   )::BIGINT AS review_activity_rank,
                   sum(review_activity_count) OVER (
                       PARTITION BY case_candidate_id
                   )::BIGINT AS case_total
            FROM totals
        )
        SELECT case_candidate_id, product_id, role,
               review_activity_count,
               CASE WHEN case_total > 0
                    THEN review_activity_count::DOUBLE / case_total
                    ELSE 0.0 END AS review_activity_share,
               review_activity_rank
        FROM ranked
        ORDER BY case_candidate_id, review_activity_rank, product_id
    """, destination)
