from __future__ import annotations

from pathlib import Path

import duckdb

from .config import POST90_DAYS
from utils import sql_literal


REQUIRED_DAILY_COLUMNS = {
    "source_partition",
    "product_id",
    "event_date",
    "rating_count",
}

REQUIRED_PRODUCT_TIME_COLUMNS = {
    "source_partition",
    "product_id",
    "entry_date",
    "first_rating_date",
    "last_rating_date",
    "total_rating_count",
    "post90_rating_count",
}


def _columns(con: duckdb.DuckDBPyConnection, path: Path) -> set[str]:
    return {
        str(row[0])
        for row in con.execute(
            "DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]
        ).fetchall()
    }


def validate_product_time_summary(
    con: duckdb.DuckDBPyConnection,
    path: Path,
) -> None:
    missing = REQUIRED_PRODUCT_TIME_COLUMNS - _columns(con, path)
    if missing:
        raise ValueError(
            f"product_time_summary missing columns: {sorted(missing)}"
        )

    duplicates = con.execute("""
        SELECT source_partition, product_id, count(*)
        FROM read_parquet(?)
        GROUP BY source_partition, product_id
        HAVING count(*) > 1
        ORDER BY source_partition, product_id
        LIMIT 10
    """, [str(path)]).fetchall()
    if duplicates:
        raise ValueError(
            f"duplicate product_time_summary rows: {duplicates}"
        )

    mismatched_entry = con.execute("""
        SELECT source_partition, product_id, entry_date, first_rating_date
        FROM read_parquet(?)
        WHERE entry_date IS DISTINCT FROM first_rating_date
        ORDER BY source_partition, product_id
        LIMIT 10
    """, [str(path)]).fetchall()
    if mismatched_entry:
        raise ValueError(
            "product_time_summary entry_date must equal first_rating_date; "
            f"examples: {mismatched_entry}"
        )


def write_product_time_summary_from_daily(
    con: duckdb.DuckDBPyConnection,
    rating_daily: Path,
    destination: Path,
    copy_atomic,
) -> None:
    """从已有逐日评分汇总直接生成一行一个商品的首评/末评时间表。

    逻辑迁自 v5 data_prep/product_time_summary.py。这里直接读取已经合并好的
    rating_daily_summary.parquet，不再要求 bucket 级中间文件。
    """
    missing = REQUIRED_DAILY_COLUMNS - _columns(con, rating_daily)
    if missing:
        raise ValueError(
            f"rating_daily_summary missing columns: {sorted(missing)}"
        )
    daily = sql_literal(str(rating_daily))
    copy_atomic(f"""
        WITH daily AS (
            SELECT source_partition,
                   product_id,
                   event_date,
                   sum(rating_count)::BIGINT AS rating_count
            FROM read_parquet({daily})
            GROUP BY source_partition, product_id, event_date
        ), bounds AS (
            SELECT source_partition,
                   product_id,
                   min(event_date) AS first_rating_date,
                   max(event_date) AS last_rating_date
            FROM daily
            GROUP BY source_partition, product_id
        )
        SELECT d.source_partition,
               d.product_id,
               b.first_rating_date AS entry_date,
               b.first_rating_date,
               b.last_rating_date,
               sum(d.rating_count)::BIGINT AS total_rating_count,
               sum(d.rating_count) FILTER (
                   d.event_date >= b.first_rating_date
                   AND d.event_date < b.first_rating_date + INTERVAL {POST90_DAYS} DAY
               )::BIGINT AS post90_rating_count
        FROM daily d
        JOIN bounds b USING (source_partition, product_id)
        GROUP BY d.source_partition, d.product_id,
                 b.first_rating_date, b.last_rating_date
    """, destination)
