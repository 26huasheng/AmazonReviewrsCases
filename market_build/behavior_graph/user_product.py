from __future__ import annotations

from pathlib import Path

import duckdb

from utils import sql_literal


def write_user_product_first(
    con: duckdb.DuckDBPyConnection,
    canonical_user_events: Path,
    market_products: Path,
    destination: Path,
    copy_atomic,
) -> None:
    """压成 user×product 第一次观测时间，并挂上 Final Market / leaf 信息。

    同一用户对同一商品多次评分或评论，在图里只算一个 membership。
    `market_products` 是 Final Market 的长期商品 universe，因此图只围绕已经
    进入 benchmark Market 体系的商品构造。
    """
    events = sql_literal(str(canonical_user_events))
    products = sql_literal(str(market_products))

    copy_atomic(f"""
        WITH product_map AS (
            SELECT source_partition,
                   market_id,
                   market_label,
                   product_id,
                   CASE
                       WHEN category_path IS NULL OR list_count(category_path) = 0
                       THEN NULL::VARCHAR
                       ELSE CAST(list_extract(category_path, list_count(category_path)) AS VARCHAR)
                   END AS leaf_category
            FROM read_parquet({products})
        )
        SELECT e.source_partition,
               e.user_id,
               e.product_id,
               p.market_id,
               p.market_label,
               p.leaf_category,
               min(e.event_date)::DATE AS first_event_date
        FROM read_parquet({events}) e
        JOIN product_map p
          ON e.source_partition = p.source_partition
         AND e.product_id = p.product_id
        WHERE e.event_date IS NOT NULL
        GROUP BY e.source_partition, e.user_id, e.product_id,
                 p.market_id, p.market_label, p.leaf_category
        ORDER BY e.source_partition, e.user_id, first_event_date, e.product_id
    """, destination)


def write_product_user_totals(
    con: duckdb.DuckDBPyConnection,
    user_product_first: Path,
    destination: Path,
    copy_atomic,
) -> None:
    """完整观测期每个商品的不同用户数。

    这个表主要用于 full-period audit，同时可以做安全预剪枝：如果一个商品
    完整时期总用户数都小于强边端点阈值，它在任何历史 t0 前也不可能达到阈值。
    """
    src = sql_literal(str(user_product_first))
    copy_atomic(f"""
        SELECT source_partition,
               product_id,
               any_value(market_id) AS market_id,
               any_value(market_label) AS market_label,
               any_value(leaf_category) AS leaf_category,
               count(*)::BIGINT AS n_users_full
        FROM read_parquet({src})
        GROUP BY source_partition, product_id
        ORDER BY source_partition, product_id
    """, destination)
