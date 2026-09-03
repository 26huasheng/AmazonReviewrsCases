from __future__ import annotations

from pathlib import Path

import duckdb

from utils import sql_literal


def write_case_focal_coreview_features(
    con: duckdb.DuckDBPyConnection,
    case_shelf: Path,
    market_products: Path,
    product_user_cumulative: Path,
    pair_cumulative: Path,
    destination: Path,
    copy_atomic,
    *,
    min_endpoint_users: int,
    min_shared_users: int,
) -> None:
    """只计算 focal -> competitor 的严格 pre-t0 共评关系。

    正式 Case 选择不再对整个 shelf 做连通分量，也不尝试分裂 Final Market。
    一个 competitor 是否属于强共评竞品，只由 focal 与它自身的 pre-t0 关系决定。
    """
    if min_endpoint_users <= 0 or min_shared_users <= 0:
        raise ValueError("behavior graph thresholds must be positive")

    shelf = sql_literal(str(case_shelf))
    products = sql_literal(str(market_products))
    product_cum = sql_literal(str(product_user_cumulative))
    pair_cum = sql_literal(str(pair_cumulative))

    copy_atomic(f"""
        WITH shelf_leaf AS (
            SELECT s.case_candidate_id,
                   s.source_partition,
                   s.market_id,
                   s.focal_product_id,
                   s.t0,
                   s.product_id,
                   s.role,
                   CASE
                       WHEN p.category_path IS NULL OR list_count(p.category_path) = 0
                       THEN NULL::VARCHAR
                       ELSE CAST(list_extract(p.category_path, list_count(p.category_path)) AS VARCHAR)
                   END AS leaf_category
            FROM read_parquet({shelf}) s
            JOIN read_parquet({products}) p
              ON s.source_partition = p.source_partition
             AND s.market_id = p.market_id
             AND s.product_id = p.product_id
        ), focal AS (
            SELECT case_candidate_id,
                   source_partition,
                   market_id,
                   focal_product_id,
                   t0,
                   product_id AS focal_id,
                   leaf_category AS focal_leaf
            FROM shelf_leaf
            WHERE role = 'focal'
        ), competitors AS (
            SELECT c.case_candidate_id,
                   c.source_partition,
                   c.market_id,
                   c.focal_product_id,
                   c.t0,
                   c.product_id,
                   f.focal_id,
                   f.focal_leaf,
                   c.leaf_category AS competitor_leaf,
                   CASE WHEN f.focal_id < c.product_id THEN f.focal_id ELSE c.product_id END
                       AS product_a,
                   CASE WHEN f.focal_id < c.product_id THEN c.product_id ELSE f.focal_id END
                       AS product_b
            FROM shelf_leaf c
            JOIN focal f
              ON c.case_candidate_id = f.case_candidate_id
            WHERE c.role = 'competitor'
        ), pairable AS (
            SELECT *
            FROM competitors
            WHERE focal_leaf IS NOT NULL
              AND competitor_leaf IS NOT NULL
              AND focal_leaf = competitor_leaf
        ), pair_stats AS (
            SELECT p.case_candidate_id,
                   p.product_id,
                   coalesce(pc.shared_users_cumulative, 0)::BIGINT AS shared_users_pre_t0
            FROM pairable p
            ASOF LEFT JOIN read_parquet({pair_cum}) pc
              ON p.source_partition = pc.source_partition
             AND p.market_id = pc.market_id
             AND p.focal_leaf = pc.leaf_category
             AND p.product_a = pc.product_a
             AND p.product_b = pc.product_b
             AND pc.event_date < p.t0
        ), with_focal_users AS (
            SELECT c.*,
                   coalesce(u.users_cumulative, 0)::BIGINT AS focal_users_pre_t0
            FROM competitors c
            ASOF LEFT JOIN read_parquet({product_cum}) u
              ON c.source_partition = u.source_partition
             AND c.focal_id = u.product_id
             AND u.event_date < c.t0
        ), with_competitor_users AS (
            SELECT c.*,
                   coalesce(u.users_cumulative, 0)::BIGINT AS competitor_users_pre_t0
            FROM with_focal_users c
            ASOF LEFT JOIN read_parquet({product_cum}) u
              ON c.source_partition = u.source_partition
             AND c.product_id = u.product_id
             AND u.event_date < c.t0
        )
        SELECT c.case_candidate_id,
               c.source_partition,
               c.market_id,
               c.focal_product_id,
               c.t0,
               c.product_id,
               c.focal_leaf,
               c.competitor_leaf,
               (c.focal_leaf IS NOT NULL
                AND c.focal_leaf = c.competitor_leaf) AS same_leaf,
               c.focal_users_pre_t0,
               c.competitor_users_pre_t0,
               coalesce(p.shared_users_pre_t0, 0)::BIGINT AS shared_users_pre_t0,
               (
                   c.focal_leaf IS NOT NULL
                   AND c.focal_leaf = c.competitor_leaf
                   AND c.focal_users_pre_t0 >= {int(min_endpoint_users)}
                   AND c.competitor_users_pre_t0 >= {int(min_endpoint_users)}
                   AND coalesce(p.shared_users_pre_t0, 0) >= {int(min_shared_users)}
               ) AS strong_coreview_pre_t0
        FROM with_competitor_users c
        LEFT JOIN pair_stats p
          ON c.case_candidate_id = p.case_candidate_id
         AND c.product_id = p.product_id
        ORDER BY c.case_candidate_id, c.product_id
    """, destination)


def write_selected_case_shelf(
    con: duckdb.DuckDBPyConnection,
    case_shelf: Path,
    focal_coreview_features: Path,
    destination: Path,
    copy_atomic,
    *,
    max_competitors: int,
) -> None:
    """把完整 t0 shelf 截到最多 K 个 competitor。

    固定策略：
    - competitor 数 <= K：全部保留；
    - competitor 数 > K：强共评 competitor 优先；
    - 强共评内部按 shared_users_pre_t0 降序；
    - 强共评不足 K 时，其余名额按 pre_t0_recent_review_count、
      pre_t0_review_count 依次补齐。

    focal 永远保留，所以最终每个 Case 最多 1 + K 个商品。
    """
    if max_competitors <= 0:
        raise ValueError("max_competitors must be positive")

    shelf = sql_literal(str(case_shelf))
    graph = sql_literal(str(focal_coreview_features))

    copy_atomic(f"""
        WITH competitor_counts AS (
            SELECT case_candidate_id,
                   count(*) FILTER (WHERE role = 'competitor')::BIGINT
                       AS competitor_pool_size
            FROM read_parquet({shelf})
            GROUP BY case_candidate_id
        ), competitor_rows AS (
            SELECT s.*,
                   c.competitor_pool_size,
                   {int(max_competitors)}::BIGINT AS competitor_cap,
                   (c.competitor_pool_size > {int(max_competitors)}) AS selection_triggered,
                   coalesce(g.same_leaf, FALSE) AS same_leaf,
                   coalesce(g.focal_users_pre_t0, 0)::BIGINT AS focal_users_pre_t0,
                   coalesce(g.competitor_users_pre_t0, 0)::BIGINT AS competitor_users_pre_t0,
                   coalesce(g.shared_users_pre_t0, 0)::BIGINT AS shared_users_pre_t0,
                   coalesce(g.strong_coreview_pre_t0, FALSE) AS strong_coreview_pre_t0
            FROM read_parquet({shelf}) s
            JOIN competitor_counts c USING (case_candidate_id)
            LEFT JOIN read_parquet({graph}) g
              ON s.case_candidate_id = g.case_candidate_id
             AND s.product_id = g.product_id
            WHERE s.role = 'competitor'
        ), ranked AS (
            SELECT *,
                   row_number() OVER (
                       PARTITION BY case_candidate_id
                       ORDER BY
                           strong_coreview_pre_t0 DESC,
                           CASE WHEN strong_coreview_pre_t0
                                THEN shared_users_pre_t0 END DESC NULLS LAST,
                           pre_t0_recent_review_count DESC NULLS LAST,
                           pre_t0_review_count DESC NULLS LAST,
                           product_id ASC
                   )::BIGINT AS selection_rank
            FROM competitor_rows
        ), selected_competitors AS (
            SELECT *,
                   CASE
                       WHEN NOT selection_triggered THEN 'within_cap'
                       WHEN strong_coreview_pre_t0 THEN 'strong_coreview'
                       ELSE 'activity_fill'
                   END AS selection_reason
            FROM ranked
            WHERE NOT selection_triggered
               OR selection_rank <= {int(max_competitors)}
        ), focal_rows AS (
            SELECT s.*,
                   c.competitor_pool_size,
                   {int(max_competitors)}::BIGINT AS competitor_cap,
                   (c.competitor_pool_size > {int(max_competitors)}) AS selection_triggered,
                   TRUE AS same_leaf,
                   NULL::BIGINT AS focal_users_pre_t0,
                   NULL::BIGINT AS competitor_users_pre_t0,
                   NULL::BIGINT AS shared_users_pre_t0,
                   FALSE AS strong_coreview_pre_t0,
                   0::BIGINT AS selection_rank,
                   'focal'::VARCHAR AS selection_reason
            FROM read_parquet({shelf}) s
            JOIN competitor_counts c USING (case_candidate_id)
            WHERE s.role = 'focal'
        )
        SELECT * FROM focal_rows
        UNION ALL BY NAME
        SELECT * FROM selected_competitors
        ORDER BY case_candidate_id, selection_rank, product_id
    """, destination)
