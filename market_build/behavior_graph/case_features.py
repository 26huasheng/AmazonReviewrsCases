from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

import duckdb

from utils import sql_literal


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}
        self.size: dict[str, int] = {}

    def add(self, value: str) -> None:
        if value not in self.parent:
            self.parent[value] = value
            self.size[value] = 1

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        self.add(left)
        self.add(right)
        a = self.find(left)
        b = self.find(right)
        if a == b:
            return
        if self.size[a] < self.size[b]:
            a, b = b, a
        self.parent[b] = a
        self.size[a] += self.size[b]


def _component_id(case_id: str, leaf: str, members: list[str]) -> str:
    payload = case_id + "\x1f" + leaf + "\x1f" + "\x1f".join(sorted(members))
    return "casegraph_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:20]


def write_case_pair_snapshot(
    con: duckdb.DuckDBPyConnection,
    case_shelf: Path,
    market_products: Path,
    product_user_cumulative: Path,
    pair_cumulative: Path,
    destination: Path,
    copy_atomic,
) -> None:
    """给指定 Case 的 shelf 商品对查询严格 `< t0` 的图统计。

    只生成同 leaf 的 shelf pair。不同 leaf 的商品仍然可以处在同一 Final Market，
    但不会因为共评图建立行为边。
    """
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
        ), pairs AS (
            SELECT a.case_candidate_id,
                   a.source_partition,
                   a.market_id,
                   a.focal_product_id,
                   a.t0,
                   a.leaf_category,
                   a.product_id AS product_a,
                   b.product_id AS product_b
            FROM shelf_leaf a
            JOIN shelf_leaf b
              ON a.case_candidate_id = b.case_candidate_id
             AND a.source_partition = b.source_partition
             AND a.market_id = b.market_id
             AND a.leaf_category = b.leaf_category
             AND a.product_id < b.product_id
            WHERE a.leaf_category IS NOT NULL
        ), with_pair AS (
            SELECT p.*,
                   coalesce(pc.shared_users_cumulative, 0)::BIGINT AS shared_users_pre_t0
            FROM pairs p
            ASOF LEFT JOIN read_parquet({pair_cum}) pc
              ON p.source_partition = pc.source_partition
             AND p.leaf_category = pc.leaf_category
             AND p.product_a = pc.product_a
             AND p.product_b = pc.product_b
             AND pc.event_date < p.t0
        ), with_a AS (
            SELECT p.*,
                   coalesce(c.users_cumulative, 0)::BIGINT AS users_a_pre_t0
            FROM with_pair p
            ASOF LEFT JOIN read_parquet({product_cum}) c
              ON p.source_partition = c.source_partition
             AND p.product_a = c.product_id
             AND c.event_date < p.t0
        ), with_b AS (
            SELECT p.*,
                   coalesce(c.users_cumulative, 0)::BIGINT AS users_b_pre_t0
            FROM with_a p
            ASOF LEFT JOIN read_parquet({product_cum}) c
              ON p.source_partition = c.source_partition
             AND p.product_b = c.product_id
             AND c.event_date < p.t0
        )
        SELECT *,
               shared_users_pre_t0::DOUBLE /
                   nullif(users_a_pre_t0 + users_b_pre_t0 - shared_users_pre_t0, 0)
                   AS jaccard_pre_t0,
               shared_users_pre_t0::DOUBLE /
                   nullif(least(users_a_pre_t0, users_b_pre_t0), 0)
                   AS overlap_min_pre_t0
        FROM with_b
        ORDER BY case_candidate_id, leaf_category, product_a, product_b
    """, destination)


def write_case_strong_edges(
    con: duckdb.DuckDBPyConnection,
    case_pair_snapshot: Path,
    destination: Path,
    copy_atomic,
    *,
    min_endpoint_users: int,
    min_shared_users: int,
) -> None:
    src = sql_literal(str(case_pair_snapshot))
    copy_atomic(f"""
        SELECT *
        FROM read_parquet({src})
        WHERE users_a_pre_t0 >= {int(min_endpoint_users)}
          AND users_b_pre_t0 >= {int(min_endpoint_users)}
          AND shared_users_pre_t0 >= {int(min_shared_users)}
        ORDER BY case_candidate_id, leaf_category, product_a, product_b
    """, destination)


def write_case_component_membership(
    con: duckdb.DuckDBPyConnection,
    case_shelf: Path,
    market_products: Path,
    case_strong_edges: Path,
    product_user_cumulative: Path,
    destination: Path,
    copy_atomic,
    *,
    min_endpoint_users: int,
) -> None:
    """在每个 Case 的当前 shelf 内，对 pre-t0 strong edges 做连通分量。

    component 只使用 t0 时这个 Case shelf 中的商品，因此不会通过已经不在当前
    shelf 的历史商品把两个当前竞品间接连接起来。
    """
    shelf = sql_literal(str(case_shelf))
    products = sql_literal(str(market_products))
    product_cum = sql_literal(str(product_user_cumulative))
    edges = sql_literal(str(case_strong_edges))

    nodes = con.execute(f"""
        WITH shelf_leaf AS (
            SELECT s.case_candidate_id,
                   s.source_partition,
                   s.market_id,
                   s.focal_product_id,
                   s.t0,
                   s.product_id,
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
        ), with_users AS (
            SELECT s.*,
                   coalesce(c.users_cumulative, 0)::BIGINT AS users_pre_t0
            FROM shelf_leaf s
            ASOF LEFT JOIN read_parquet({product_cum}) c
              ON s.source_partition = c.source_partition
             AND s.product_id = c.product_id
             AND c.event_date < s.t0
        )
        SELECT case_candidate_id, source_partition, market_id,
               focal_product_id, t0, product_id, leaf_category, users_pre_t0
        FROM with_users
        ORDER BY case_candidate_id, leaf_category, product_id
    """).fetchall()

    edge_rows = con.execute(f"""
        SELECT case_candidate_id, leaf_category, product_a, product_b
        FROM read_parquet({edges})
        ORDER BY case_candidate_id, leaf_category, product_a, product_b
    """).fetchall()

    uf_by_group: dict[tuple[str, str], _UnionFind] = defaultdict(_UnionFind)
    node_rows_by_group: dict[tuple[str, str], list[tuple]] = defaultdict(list)
    for row in nodes:
        case_id = str(row[0])
        leaf = str(row[6]) if row[6] is not None else ""
        key = (case_id, leaf)
        node_rows_by_group[key].append(row)
        uf_by_group[key].add(str(row[5]))

    for case_id, leaf_category, product_a, product_b in edge_rows:
        key = (str(case_id), str(leaf_category))
        uf_by_group[key].union(str(product_a), str(product_b))

    output: list[tuple] = []
    for (case_id, leaf), rows in sorted(node_rows_by_group.items()):
        uf = uf_by_group[(case_id, leaf)]
        groups: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            groups[uf.find(str(row[5]))].append(str(row[5]))
        group_meta: dict[str, tuple[str | None, int]] = {}
        for root, members in groups.items():
            members = sorted(members)
            if len(members) >= 2:
                group_meta[root] = (_component_id(case_id, leaf, members), len(members))
            else:
                group_meta[root] = (None, 1)

        for row in rows:
            (
                case_value, source_partition, market_id, focal_product_id,
                t0, product_id, leaf_category, users_pre_t0,
            ) = row
            root = uf.find(str(product_id))
            component_id, component_size = group_meta[root]
            if leaf_category is None:
                graph_status = "no_leaf"
            elif int(users_pre_t0) < int(min_endpoint_users):
                graph_status = "insufficient_endpoint_users"
            elif component_id is None:
                graph_status = "isolated"
            else:
                graph_status = "component"
            output.append((
                case_value,
                source_partition,
                market_id,
                focal_product_id,
                t0,
                product_id,
                leaf_category,
                int(users_pre_t0),
                component_id,
                int(component_size),
                graph_status,
            ))

    con.execute("DROP TABLE IF EXISTS behavior_case_components_tmp")
    con.execute("""
        CREATE TEMP TABLE behavior_case_components_tmp (
            case_candidate_id VARCHAR,
            source_partition VARCHAR,
            market_id VARCHAR,
            focal_product_id VARCHAR,
            t0 DATE,
            product_id VARCHAR,
            leaf_category VARCHAR,
            users_pre_t0 BIGINT,
            graph_component_id_pre_t0 VARCHAR,
            graph_component_size_pre_t0 BIGINT,
            graph_status_pre_t0 VARCHAR
        )
    """)
    if output:
        con.executemany(
            "INSERT INTO behavior_case_components_tmp VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            output,
        )
    copy_atomic("""
        SELECT *
        FROM behavior_case_components_tmp
        ORDER BY case_candidate_id, product_id
    """, destination)


def write_case_graph_features(
    con: duckdb.DuckDBPyConnection,
    case_shelf: Path,
    case_pair_snapshot: Path,
    case_strong_edges: Path,
    case_components: Path,
    destination: Path,
    copy_atomic,
) -> None:
    """最终一行一个 Case×shelf product 的 graph relation。"""
    shelf = sql_literal(str(case_shelf))
    pairs = sql_literal(str(case_pair_snapshot))
    strong = sql_literal(str(case_strong_edges))
    components = sql_literal(str(case_components))

    copy_atomic(f"""
        WITH component_with_focal AS (
            SELECT c.*,
                   f.graph_component_id_pre_t0 AS focal_component_id_pre_t0,
                   f.graph_status_pre_t0 AS focal_graph_status_pre_t0,
                   f.users_pre_t0 AS focal_users_pre_t0
            FROM read_parquet({components}) c
            JOIN read_parquet({components}) f
              ON c.case_candidate_id = f.case_candidate_id
             AND f.product_id = f.focal_product_id
        ), focal_pairs AS (
            SELECT p.case_candidate_id,
                   CASE WHEN p.product_a = p.focal_product_id THEN p.product_b ELSE p.product_a END
                       AS product_id,
                   p.shared_users_pre_t0,
                   CASE WHEN p.product_a = p.focal_product_id THEN p.users_a_pre_t0 ELSE p.users_b_pre_t0 END
                       AS focal_users_from_pair,
                   CASE WHEN p.product_a = p.focal_product_id THEN p.users_b_pre_t0 ELSE p.users_a_pre_t0 END
                       AS competitor_users_pre_t0,
                   p.jaccard_pre_t0,
                   p.overlap_min_pre_t0
            FROM read_parquet({pairs}) p
            WHERE p.product_a = p.focal_product_id
               OR p.product_b = p.focal_product_id
        ), direct_edges AS (
            SELECT case_candidate_id,
                   CASE WHEN product_a = focal_product_id THEN product_b ELSE product_a END AS product_id,
                   TRUE AS direct_strong_edge_pre_t0
            FROM read_parquet({strong})
            WHERE product_a = focal_product_id OR product_b = focal_product_id
        )
        SELECT s.case_candidate_id,
               s.source_partition,
               s.market_id,
               s.focal_product_id,
               s.t0,
               s.product_id,
               s.role,
               c.leaf_category,
               CASE
                   WHEN s.product_id = s.focal_product_id THEN c.users_pre_t0
                   ELSE coalesce(fp.focal_users_from_pair, c.focal_users_pre_t0, 0)
               END::BIGINT AS focal_users_pre_t0,
               c.users_pre_t0::BIGINT AS competitor_users_pre_t0,
               CASE WHEN s.product_id = s.focal_product_id THEN c.users_pre_t0
                    ELSE coalesce(fp.shared_users_pre_t0, 0) END::BIGINT
                    AS shared_users_pre_t0,
               CASE WHEN s.product_id = s.focal_product_id THEN 1.0
                    ELSE fp.jaccard_pre_t0 END AS jaccard_pre_t0,
               CASE WHEN s.product_id = s.focal_product_id THEN 1.0
                    ELSE fp.overlap_min_pre_t0 END AS overlap_min_pre_t0,
               CASE WHEN s.product_id = s.focal_product_id THEN TRUE
                    ELSE coalesce(d.direct_strong_edge_pre_t0, FALSE) END
                    AS direct_strong_edge_pre_t0,
               c.graph_component_id_pre_t0,
               c.graph_component_size_pre_t0,
               c.graph_status_pre_t0,
               CASE
                   WHEN s.product_id = s.focal_product_id THEN 'focal'
                   WHEN coalesce(d.direct_strong_edge_pre_t0, FALSE) THEN 'direct_strong_edge'
                   WHEN c.graph_component_id_pre_t0 IS NOT NULL
                    AND c.graph_component_id_pre_t0 = c.focal_component_id_pre_t0
                       THEN 'same_component'
                   WHEN c.graph_status_pre_t0 = 'isolated' THEN 'isolated'
                   ELSE 'same_market_other'
               END AS graph_relation
        FROM read_parquet({shelf}) s
        JOIN component_with_focal c
          ON s.case_candidate_id = c.case_candidate_id
         AND s.product_id = c.product_id
        LEFT JOIN focal_pairs fp
          ON s.case_candidate_id = fp.case_candidate_id
         AND s.product_id = fp.product_id
        LEFT JOIN direct_edges d
          ON s.case_candidate_id = d.case_candidate_id
         AND s.product_id = d.product_id
        ORDER BY s.case_candidate_id,
                 CASE graph_relation
                     WHEN 'focal' THEN 0
                     WHEN 'direct_strong_edge' THEN 1
                     WHEN 'same_component' THEN 2
                     WHEN 'isolated' THEN 3
                     ELSE 4
                 END,
                 s.product_id
    """, destination)
