from __future__ import annotations

from pathlib import Path

import duckdb

from utils import sql_literal


def write_user_history_indexes(
    con: duckdb.DuckDBPyConnection,
    canonical_events: Path,
    market_products: Path,
    global_destination: Path,
    category_destination: Path,
    market_destination: Path,
    copy_atomic,
) -> None:
    """一次性建立用户全局 / 大类 / Market 历史累计索引。

    distinct product 数按“用户第一次碰到某商品的日期”累计，因此不会把重复评分
    误当成多个历史商品。
    """
    events = sql_literal(str(canonical_events))
    products = sql_literal(str(market_products))

    copy_atomic(f"""
        WITH e AS (
            SELECT user_id, event_date, count(*)::BIGINT AS day_events
            FROM read_parquet({events})
            GROUP BY user_id, event_date
        ), first_product AS (
            SELECT user_id, source_partition, product_id,
                   min(event_date) AS first_product_date
            FROM read_parquet({events})
            GROUP BY user_id, source_partition, product_id
        ), p AS (
            SELECT user_id, first_product_date AS event_date,
                   count(*)::BIGINT AS day_new_products
            FROM first_product
            GROUP BY user_id, first_product_date
        ), dates AS (
            SELECT user_id, event_date FROM e
            UNION
            SELECT user_id, event_date FROM p
        ), d AS (
            SELECT dates.user_id, dates.event_date,
                   coalesce(e.day_events, 0)::BIGINT AS day_events,
                   coalesce(p.day_new_products, 0)::BIGINT AS day_new_products
            FROM dates
            LEFT JOIN e USING(user_id, event_date)
            LEFT JOIN p USING(user_id, event_date)
        )
        SELECT user_id, event_date,
               sum(day_events) OVER (
                   PARTITION BY user_id ORDER BY event_date
               )::BIGINT AS cumulative_event_count,
               sum(day_new_products) OVER (
                   PARTITION BY user_id ORDER BY event_date
               )::BIGINT AS cumulative_product_count
        FROM d
        ORDER BY user_id, event_date
    """, global_destination)

    copy_atomic(f"""
        WITH e AS (
            SELECT source_partition, user_id, event_date,
                   count(*)::BIGINT AS day_events
            FROM read_parquet({events})
            GROUP BY source_partition, user_id, event_date
        ), first_product AS (
            SELECT source_partition, user_id, product_id,
                   min(event_date) AS first_product_date
            FROM read_parquet({events})
            GROUP BY source_partition, user_id, product_id
        ), p AS (
            SELECT source_partition, user_id, first_product_date AS event_date,
                   count(*)::BIGINT AS day_new_products
            FROM first_product
            GROUP BY source_partition, user_id, first_product_date
        ), dates AS (
            SELECT source_partition, user_id, event_date FROM e
            UNION
            SELECT source_partition, user_id, event_date FROM p
        ), d AS (
            SELECT dates.source_partition, dates.user_id, dates.event_date,
                   coalesce(e.day_events, 0)::BIGINT AS day_events,
                   coalesce(p.day_new_products, 0)::BIGINT AS day_new_products
            FROM dates
            LEFT JOIN e USING(source_partition, user_id, event_date)
            LEFT JOIN p USING(source_partition, user_id, event_date)
        )
        SELECT source_partition, user_id, event_date,
               sum(day_events) OVER (
                   PARTITION BY source_partition, user_id ORDER BY event_date
               )::BIGINT AS cumulative_event_count,
               sum(day_new_products) OVER (
                   PARTITION BY source_partition, user_id ORDER BY event_date
               )::BIGINT AS cumulative_product_count
        FROM d
        ORDER BY source_partition, user_id, event_date
    """, category_destination)

    copy_atomic(f"""
        WITH mapped AS (
            SELECT p.market_id, e.user_id, e.product_id, e.event_date
            FROM read_parquet({events}) e
            JOIN read_parquet({products}) p
              ON e.source_partition=p.source_partition
             AND e.product_id=p.product_id
        ), e AS (
            SELECT market_id, user_id, event_date,
                   count(*)::BIGINT AS day_events
            FROM mapped
            GROUP BY market_id, user_id, event_date
        ), first_product AS (
            SELECT market_id, user_id, product_id,
                   min(event_date) AS first_product_date
            FROM mapped
            GROUP BY market_id, user_id, product_id
        ), p AS (
            SELECT market_id, user_id, first_product_date AS event_date,
                   count(*)::BIGINT AS day_new_products
            FROM first_product
            GROUP BY market_id, user_id, first_product_date
        ), dates AS (
            SELECT market_id, user_id, event_date FROM e
            UNION
            SELECT market_id, user_id, event_date FROM p
        ), d AS (
            SELECT dates.market_id, dates.user_id, dates.event_date,
                   coalesce(e.day_events, 0)::BIGINT AS day_events,
                   coalesce(p.day_new_products, 0)::BIGINT AS day_new_products
            FROM dates
            LEFT JOIN e USING(market_id, user_id, event_date)
            LEFT JOIN p USING(market_id, user_id, event_date)
        )
        SELECT market_id, user_id, event_date,
               sum(day_events) OVER (
                   PARTITION BY market_id, user_id ORDER BY event_date
               )::BIGINT AS cumulative_event_count,
               sum(day_new_products) OVER (
                   PARTITION BY market_id, user_id ORDER BY event_date
               )::BIGINT AS cumulative_product_count
        FROM d
        ORDER BY market_id, user_id, event_date
    """, market_destination)
