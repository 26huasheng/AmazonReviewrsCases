from __future__ import annotations

from pathlib import Path

import duckdb

from utils import sql_literal


def write_full_graph_edges(
    con: duckdb.DuckDBPyConnection,
    pair_full_counts: Path,
    product_user_totals: Path,
    destination: Path,
    copy_atomic,
    *,
    min_endpoint_users: int,
    min_shared_users: int,
) -> None:
    """完整时期 strong edges，只用于 Market 内部图审计。"""
    if min_endpoint_users <= 0 or min_shared_users <= 0:
        raise ValueError("graph thresholds must be positive")

    pairs = sql_literal(str(pair_full_counts))
    totals = sql_literal(str(product_user_totals))
    copy_atomic(f"""
        SELECT p.source_partition,
               p.market_id,
               p.market_label,
               p.leaf_category,
               p.product_a,
               p.product_b,
               a.n_users_full AS users_a_full,
               b.n_users_full AS users_b_full,
               p.shared_users_full,
               p.shared_users_full::DOUBLE /
                   nullif(a.n_users_full + b.n_users_full - p.shared_users_full, 0)
                   AS jaccard_full,
               p.shared_users_full::DOUBLE /
                   nullif(least(a.n_users_full, b.n_users_full), 0)
                   AS overlap_min_full
        FROM read_parquet({pairs}) p
        JOIN read_parquet({totals}) a
          ON p.source_partition = a.source_partition
         AND p.market_id = a.market_id
         AND p.product_a = a.product_id
        JOIN read_parquet({totals}) b
          ON p.source_partition = b.source_partition
         AND p.market_id = b.market_id
         AND p.product_b = b.product_id
        WHERE a.n_users_full >= {int(min_endpoint_users)}
          AND b.n_users_full >= {int(min_endpoint_users)}
          AND p.shared_users_full >= {int(min_shared_users)}
        ORDER BY p.source_partition, p.market_id, p.leaf_category,
                 p.product_a, p.product_b
    """, destination)
