from __future__ import annotations

from pathlib import Path

import duckdb

from utils import sql_literal


def write_case_user_features(
    con: duckdb.DuckDBPyConnection,
    cases: Path,
    market_population: Path,
    user_history: Path,
    user_category_history: Path,
    user_market_history: Path,
    destination: Path,
    copy_atomic,
) -> None:
    """给每个 Case×Market-user 计算只依赖 t0 以前数据的用户特征。"""
    c = sql_literal(str(cases))
    mp = sql_literal(str(market_population))
    gh = sql_literal(str(user_history))
    ch = sql_literal(str(user_category_history))
    mh = sql_literal(str(user_market_history))

    copy_atomic(f"""
        WITH base AS (
            SELECT c.case_candidate_id,
                   c.market_id,
                   c.source_partition,
                   c.t0,
                   p.user_id,
                   p.population_source,
                   p.sampling_rank AS market_population_rank
            FROM read_parquet({c}) c
            JOIN read_parquet({mp}) p
              ON c.market_id=p.market_id
        ), with_global AS (
            SELECT b.*,
                   coalesce(g.cumulative_event_count, 0)::BIGINT AS history_event_count,
                   coalesce(g.cumulative_product_count, 0)::BIGINT AS history_product_count,
                   g.event_date AS last_event_date
            FROM base b
            ASOF LEFT JOIN read_parquet({gh}) g
              ON b.user_id=g.user_id
             AND g.event_date < b.t0
        ), with_category AS (
            SELECT b.*,
                   coalesce(g.cumulative_event_count, 0)::BIGINT AS category_history_event_count,
                   coalesce(g.cumulative_product_count, 0)::BIGINT AS category_history_product_count
            FROM with_global b
            ASOF LEFT JOIN read_parquet({ch}) g
              ON b.source_partition=g.source_partition
             AND b.user_id=g.user_id
             AND g.event_date < b.t0
        ), with_market AS (
            SELECT b.*,
                   coalesce(g.cumulative_event_count, 0)::BIGINT AS market_history_event_count,
                   coalesce(g.cumulative_product_count, 0)::BIGINT AS market_history_product_count
            FROM with_category b
            ASOF LEFT JOIN read_parquet({mh}) g
              ON b.market_id=g.market_id
             AND b.user_id=g.user_id
             AND g.event_date < b.t0
        )
        SELECT *,
               CASE WHEN last_event_date IS NULL THEN NULL
                    ELSE date_diff('day', last_event_date, t0)::BIGINT END
                   AS days_since_last_event,
               CASE
                   WHEN market_history_product_count > 0 THEN 'market_history'
                   WHEN category_history_product_count > 0 THEN 'category_only'
                   ELSE 'outside_category'
               END AS relation_stratum
        FROM with_market
        ORDER BY case_candidate_id, user_id
    """, destination)
