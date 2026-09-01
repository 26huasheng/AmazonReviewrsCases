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


def write_market_review_cumulative(
    con: duckdb.DuckDBPyConnection,
    market_product_map: Path,
    rating_daily: Path,
    market_daily_path: Path,
    market_cumulative_path: Path,
    copy_atomic,
) -> None:
    """迁自 v5 focal_features：先 many-to-one 汇总到 Market，再做累计，避免 focal×product 展开。"""
    required = {"source_partition", "product_id", "event_date", "rating_count"}
    missing = required - _columns(con, rating_daily)
    if missing:
        raise ValueError(
            f"rating_daily_summary missing columns: {sorted(missing)}"
        )
    mapping = sql_literal(str(market_product_map))
    daily = sql_literal(str(rating_daily))
    copy_atomic(f"""
        SELECT m.source_partition,
               m.market_id,
               d.event_date,
               sum(d.rating_count)::BIGINT AS day_review_count
        FROM read_parquet({daily}) d
        JOIN read_parquet({mapping}) m
          USING (source_partition, product_id)
        GROUP BY m.source_partition, m.market_id, d.event_date
    """, market_daily_path)

    copy_atomic(f"""
        SELECT source_partition,
               market_id,
               event_date,
               day_review_count,
               sum(day_review_count) OVER (
                   PARTITION BY source_partition, market_id
                   ORDER BY event_date
               )::BIGINT AS cumulative_review_count
        FROM read_parquet({sql_literal(str(market_daily_path))})
    """, market_cumulative_path)


def attach_market_pre_t0_review_count(
    con: duckdb.DuckDBPyConnection,
    candidates_path: Path,
    market_cumulative_path: Path,
    destination: Path,
    copy_atomic,
) -> None:
    candidates = sql_literal(str(candidates_path))
    cumulative = sql_literal(str(market_cumulative_path))
    copy_atomic(f"""
        SELECT c.*,
               coalesce(m.cumulative_review_count, 0)::BIGINT
                   AS market_pre_t0_review_count
        FROM read_parquet({candidates}) c
        ASOF LEFT JOIN read_parquet({cumulative}) m
          ON c.source_partition = m.source_partition
         AND c.market_id = m.market_id
         AND m.event_date < c.t0
    """, destination)
