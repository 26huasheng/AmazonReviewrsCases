from __future__ import annotations

from pathlib import Path

import duckdb

from utils import sql_literal


def write_graph_market_overlap(
    con: duckdb.DuckDBPyConnection,
    full_graph_components: Path,
    market_products: Path,
    destination: Path,
    copy_atomic,
) -> None:
    """把 full-period graph component 映射回 Final Market。

    这张表用于回答：一个行为 component 主要落在哪个语义 Market、一个语义 Market
    是否被拆成多个明显行为 component。它只做审计，不影响历史 Case。
    """
    graph = sql_literal(str(full_graph_components))
    products = sql_literal(str(market_products))
    copy_atomic(f"""
        WITH joined AS (
            SELECT g.source_partition,
                   g.leaf_category,
                   g.product_id,
                   g.graph_component_id,
                   g.component_size,
                   g.graph_status,
                   p.market_id,
                   p.market_label
            FROM read_parquet({graph}) g
            JOIN read_parquet({products}) p
              ON g.source_partition = p.source_partition
             AND g.product_id = p.product_id
        ), market_sizes AS (
            SELECT source_partition, market_id, count(*)::BIGINT AS market_product_count
            FROM read_parquet({products})
            GROUP BY source_partition, market_id
        ), component_market AS (
            SELECT source_partition,
                   leaf_category,
                   graph_component_id,
                   any_value(component_size)::BIGINT AS component_size,
                   market_id,
                   any_value(market_label) AS market_label,
                   count(*)::BIGINT AS overlap_products
            FROM joined
            WHERE graph_status = 'component'
            GROUP BY source_partition, leaf_category,
                     graph_component_id, market_id
        )
        SELECT c.source_partition,
               c.leaf_category,
               c.graph_component_id,
               c.component_size,
               c.market_id,
               c.market_label,
               m.market_product_count,
               c.overlap_products,
               c.overlap_products::DOUBLE / nullif(c.component_size, 0)
                   AS component_share_in_market,
               c.overlap_products::DOUBLE / nullif(m.market_product_count, 0)
                   AS market_share_in_component
        FROM component_market c
        JOIN market_sizes m
          ON c.source_partition = m.source_partition
         AND c.market_id = m.market_id
        ORDER BY c.source_partition, c.leaf_category,
                 c.graph_component_id, c.overlap_products DESC, c.market_id
    """, destination)


def write_market_graph_summary(
    con: duckdb.DuckDBPyConnection,
    full_graph_components: Path,
    market_products: Path,
    destination: Path,
    copy_atomic,
) -> None:
    """一行一个 Final Market 的行为图审计摘要。"""
    graph = sql_literal(str(full_graph_components))
    products = sql_literal(str(market_products))
    copy_atomic(f"""
        WITH joined AS (
            SELECT p.source_partition,
                   p.market_id,
                   p.market_label,
                   p.product_id,
                   g.graph_component_id,
                   g.graph_status
            FROM read_parquet({products}) p
            LEFT JOIN read_parquet({graph}) g
              ON p.source_partition = g.source_partition
             AND p.product_id = g.product_id
        )
        SELECT source_partition,
               market_id,
               any_value(market_label) AS market_label,
               count(*)::BIGINT AS n_market_products,
               count(*) FILTER (graph_status IS NOT NULL)::BIGINT AS n_graph_eligible_products,
               count(*) FILTER (graph_status = 'component')::BIGINT AS n_component_products,
               count(*) FILTER (graph_status = 'isolated')::BIGINT AS n_isolated_products,
               count(DISTINCT graph_component_id) FILTER (
                   graph_component_id IS NOT NULL
               )::BIGINT AS n_behavior_components
        FROM joined
        GROUP BY source_partition, market_id
        ORDER BY source_partition, market_id
    """, destination)
