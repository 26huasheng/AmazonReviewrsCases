from __future__ import annotations

from pathlib import Path

import duckdb

from utils import sql_literal


def _columns(con: duckdb.DuckDBPyConnection, path: Path) -> set[str]:
    return {
        str(row[0])
        for row in con.execute(
            "DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]
        ).fetchall()
    }


def write_product_rating_cumulative(
    con: duckdb.DuckDBPyConnection,
    rating_daily: Path,
    destination: Path,
    copy_atomic,
) -> None:
    """一次性建立商品逐日累计评论量/评分和，后续所有 Case 用 ASOF 查询。"""
    columns = _columns(con, rating_daily)
    required = {"source_partition", "product_id", "event_date", "rating_count"}
    missing = required - columns
    if missing:
        raise ValueError(
            f"rating_daily_summary missing columns: {sorted(missing)}"
        )
    rating_sum_expr = (
        "sum(rating_sum)::DOUBLE" if "rating_sum" in columns
        else "NULL::DOUBLE"
    )
    daily = sql_literal(str(rating_daily))
    copy_atomic(f"""
        WITH daily AS (
            SELECT source_partition,
                   product_id,
                   event_date,
                   sum(rating_count)::BIGINT AS rating_count,
                   {rating_sum_expr} AS rating_sum
            FROM read_parquet({daily})
            GROUP BY source_partition, product_id, event_date
        )
        SELECT source_partition,
               product_id,
               event_date,
               sum(rating_count) OVER (
                   PARTITION BY source_partition, product_id
                   ORDER BY event_date
               )::BIGINT AS cumulative_rating_count,
               sum(rating_sum) OVER (
                   PARTITION BY source_partition, product_id
                   ORDER BY event_date
               )::DOUBLE AS cumulative_rating_sum
        FROM daily
    """, destination)


def write_shelf_members(
    con: duckdb.DuckDBPyConnection,
    cases_path: Path,
    timeline_path: Path,
    destination: Path,
    copy_atomic,
) -> None:
    """给明确传入的 Case 集合构造 t0 货架，不对全部候选 Case 自动展开。"""
    case_columns = _columns(con, cases_path)
    required = {
        "case_candidate_id",
        "source_partition",
        "discovery_version",
        "market_id",
        "market_label",
        "focal_product_id",
        "t0",
    }
    missing = required - case_columns
    if missing:
        raise ValueError(f"cases table missing columns: {sorted(missing)}")

    cases = sql_literal(str(cases_path))
    timeline = sql_literal(str(timeline_path))
    copy_atomic(f"""
        WITH focal AS (
            SELECT c.case_candidate_id,
                   c.source_partition,
                   c.discovery_version,
                   c.market_id,
                   c.market_label,
                   c.focal_product_id,
                   c.t0,
                   t.product_id,
                   t.product_title,
                   'focal'::VARCHAR AS role,
                   t.first_rating_date,
                   t.last_rating_date,
                   t.metadata_snapshot_price
            FROM read_parquet({cases}) c
            JOIN read_parquet({timeline}) t
              ON c.source_partition = t.source_partition
             AND c.market_id = t.market_id
             AND c.focal_product_id = t.product_id
        ), competitors AS (
            SELECT c.case_candidate_id,
                   c.source_partition,
                   c.discovery_version,
                   c.market_id,
                   c.market_label,
                   c.focal_product_id,
                   c.t0,
                   t.product_id,
                   t.product_title,
                   'competitor'::VARCHAR AS role,
                   t.first_rating_date,
                   t.last_rating_date,
                   t.metadata_snapshot_price
            FROM read_parquet({cases}) c
            JOIN read_parquet({timeline}) t
              ON c.source_partition = t.source_partition
             AND c.market_id = t.market_id
            WHERE t.product_id <> c.focal_product_id
              AND t.first_rating_date < c.t0
              AND t.last_rating_date >= c.t0
        )
        SELECT * FROM focal
        UNION ALL
        SELECT * FROM competitors
    """, destination)


def attach_shelf_features(
    con: duckdb.DuckDBPyConnection,
    members_path: Path,
    cumulative_path: Path,
    destination: Path,
    copy_atomic,
    *,
    recent_window_days: int,
) -> None:
    if recent_window_days <= 0:
        raise ValueError("recent_window_days must be positive")
    members = sql_literal(str(members_path))
    cumulative = sql_literal(str(cumulative_path))
    copy_atomic(f"""
        WITH pre_t0 AS (
            SELECT s.*,
                   coalesce(c.cumulative_rating_count, 0)::BIGINT
                       AS pre_t0_review_count,
                   c.cumulative_rating_sum AS pre_t0_rating_sum
            FROM read_parquet({members}) s
            ASOF LEFT JOIN read_parquet({cumulative}) c
              ON s.source_partition = c.source_partition
             AND s.product_id = c.product_id
             AND c.event_date < s.t0
        ), before_recent_window AS (
            SELECT p.*,
                   coalesce(c.cumulative_rating_count, 0)::BIGINT
                       AS review_count_before_recent_window
            FROM pre_t0 p
            ASOF LEFT JOIN read_parquet({cumulative}) c
              ON p.source_partition = c.source_partition
             AND p.product_id = c.product_id
             AND c.event_date < CAST(
                 p.t0 - INTERVAL {int(recent_window_days)} DAY AS DATE
             )
        )
        SELECT case_candidate_id,
               source_partition,
               discovery_version,
               market_id,
               market_label,
               focal_product_id,
               t0,
               product_id,
               product_title,
               role,
               first_rating_date AS first_review_date,
               last_rating_date AS last_review_date,
               pre_t0_review_count,
               CASE
                   WHEN pre_t0_review_count > 0
                    AND pre_t0_rating_sum IS NOT NULL
                   THEN pre_t0_rating_sum / pre_t0_review_count
               END AS pre_t0_rating_mean,
               {int(recent_window_days)}::BIGINT AS recent_window_days,
               (pre_t0_review_count - review_count_before_recent_window)::BIGINT
                   AS pre_t0_recent_review_count,
               NULL::DOUBLE AS price_at_t0,
               NULL::VARCHAR AS price_source,
               metadata_snapshot_price
        FROM before_recent_window
    """, destination)
