from __future__ import annotations

from pathlib import Path

import duckdb

from utils import sql_literal


def write_product_user_cumulative(
    con: duckdb.DuckDBPyConnection,
    user_product_first: Path,
    destination: Path,
    copy_atomic,
) -> None:
    """商品不同用户数随时间的累计表，给历史 Case 查询端点用户数。"""
    src = sql_literal(str(user_product_first))
    copy_atomic(f"""
        WITH daily AS (
            SELECT source_partition,
                   product_id,
                   first_event_date AS event_date,
                   count(*)::BIGINT AS new_users
            FROM read_parquet({src})
            GROUP BY source_partition, product_id, first_event_date
        )
        SELECT source_partition,
               product_id,
               event_date,
               new_users,
               sum(new_users) OVER (
                   PARTITION BY source_partition, product_id
                   ORDER BY event_date
                   ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
               )::BIGINT AS users_cumulative
        FROM daily
        ORDER BY source_partition, product_id, event_date
    """, destination)


def write_pair_cumulative(
    con: duckdb.DuckDBPyConnection,
    pair_user_events: Path,
    destination: Path,
    copy_atomic,
) -> None:
    """商品对共同用户数随时间的累计表。

    `event_date` 当天新增的共同用户在当天结束后进入累计值。历史 Case 查询时统一
    使用 `event_date < t0`，保证 t0 当天行为不会进入 pre-t0 特征。
    """
    src = sql_literal(str(pair_user_events))
    copy_atomic(f"""
        WITH daily AS (
            SELECT source_partition,
                   leaf_category,
                   product_a,
                   product_b,
                   pair_event_date AS event_date,
                   count(*)::BIGINT AS new_shared_users
            FROM read_parquet({src})
            GROUP BY source_partition, leaf_category,
                     product_a, product_b, pair_event_date
        )
        SELECT source_partition,
               leaf_category,
               product_a,
               product_b,
               event_date,
               new_shared_users,
               sum(new_shared_users) OVER (
                   PARTITION BY source_partition, leaf_category,
                                product_a, product_b
                   ORDER BY event_date
                   ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
               )::BIGINT AS shared_users_cumulative
        FROM daily
        ORDER BY source_partition, leaf_category,
                 product_a, product_b, event_date
    """, destination)
