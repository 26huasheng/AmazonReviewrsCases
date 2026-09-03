from __future__ import annotations

from pathlib import Path

import duckdb

from utils import sql_literal


def write_pair_user_events(
    con: duckdb.DuckDBPyConnection,
    user_product_first: Path,
    product_user_totals: Path,
    destination: Path,
    copy_atomic,
    *,
    min_endpoint_users: int,
) -> None:
    """生成同 leaf 的商品对共同用户事件。

    一行表示：某个用户从 `pair_event_date` 开始同时属于 product_a / product_b。

    为控制 pair 数量，先用完整时期商品用户数做安全预剪枝。完整时期总用户数
    < min_endpoint_users 的商品在任意历史 t0 前都不可能成为合格强边端点，因此
    这个剪枝不会改变任何合法 pre-t0 strong edge。
    """
    if min_endpoint_users <= 0:
        raise ValueError("min_endpoint_users must be positive")

    memberships = sql_literal(str(user_product_first))
    totals = sql_literal(str(product_user_totals))

    copy_atomic(f"""
        WITH eligible_products AS (
            SELECT source_partition, product_id
            FROM read_parquet({totals})
            WHERE n_users_full >= {int(min_endpoint_users)}
        ), eligible_memberships AS (
            SELECT u.*
            FROM read_parquet({memberships}) u
            JOIN eligible_products e
              ON u.source_partition = e.source_partition
             AND u.product_id = e.product_id
            WHERE u.leaf_category IS NOT NULL
              AND trim(u.leaf_category) <> ''
        )
        SELECT a.source_partition,
               a.leaf_category,
               a.product_id AS product_a,
               b.product_id AS product_b,
               a.user_id,
               greatest(a.first_event_date, b.first_event_date)::DATE AS pair_event_date
        FROM eligible_memberships a
        JOIN eligible_memberships b
          ON a.source_partition = b.source_partition
         AND a.leaf_category = b.leaf_category
         AND a.user_id = b.user_id
         AND a.product_id < b.product_id
        ORDER BY a.source_partition, a.leaf_category,
                 a.product_id, b.product_id, pair_event_date, a.user_id
    """, destination)


def write_pair_full_counts(
    con: duckdb.DuckDBPyConnection,
    pair_user_events: Path,
    destination: Path,
    copy_atomic,
) -> None:
    """完整时期每个同 leaf 商品对的共同用户数。"""
    src = sql_literal(str(pair_user_events))
    copy_atomic(f"""
        SELECT source_partition,
               leaf_category,
               product_a,
               product_b,
               count(*)::BIGINT AS shared_users_full
        FROM read_parquet({src})
        GROUP BY source_partition, leaf_category, product_a, product_b
        ORDER BY source_partition, leaf_category, product_a, product_b
    """, destination)
